/**
 * Sitecore HTTP utilities — modelled on the Sitecore-mcp reference app.
 *
 * Auth: domain-aware HTTP Basic, driven by ITEM_SERVICE_* env vars.
 * All calls return a structured { status, ok, url, data } JSON string so
 * every MCP tool response is uniform and self-describing.
 *
 * Environment variables:
 *   ITEM_SERVICE_SERVER_URL   Base URL, e.g. https://sitecore.example.com/sitecore
 *   ITEM_SERVICE_USERNAME     Sitecore username
 *   ITEM_SERVICE_PASSWORD     Sitecore password
 *   ITEM_SERVICE_DOMAIN       Optional Sitecore domain prefix (e.g. "sitecore")
 */

// ── Config ────────────────────────────────────────────────────────────────────

export function getConfig() {
  const baseUrl = process.env.ITEM_SERVICE_SERVER_URL;
  const username = process.env.ITEM_SERVICE_USERNAME;
  const password = process.env.ITEM_SERVICE_PASSWORD;
  const domain = process.env.ITEM_SERVICE_DOMAIN;

  if (!baseUrl || !username || !password) {
    throw new Error(
      'Missing required env vars. Set ITEM_SERVICE_SERVER_URL, ITEM_SERVICE_USERNAME and ITEM_SERVICE_PASSWORD.'
    );
  }

  return { baseUrl, username, password, domain };
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export function buildAuthHeader(config) {
  const user = config.domain ? `${config.domain}\\${config.username}` : config.username;
  const token = Buffer.from(`${user}:${config.password}`).toString('base64');
  return `Basic ${token}`;
}

// ── URL builder ───────────────────────────────────────────────────────────────

export function buildUrl(baseUrl, path, query) {
  let base = baseUrl.replace(/\/$/, '');
  const rel = path.replace(/^\//, '');
  // Avoid ".../sitecore/sitecore/api/..." when both the configured base URL
  // and the endpoint path carry the /sitecore prefix.
  if (/\/sitecore$/i.test(base) && /^sitecore\//i.test(rel)) {
    base = base.replace(/\/sitecore$/i, '');
  }
  const url = new URL(`${base}/${rel}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

// ── Cookie session (SSC auth) ─────────────────────────────────────────────────
// Hardened Sitecore instances often disable HTTP Basic on the ItemService and
// only accept the cookie session issued by /sitecore/api/ssc/auth/login.
// Cookies are cached per base/user and refreshed on expiry or 401/403.

let cookieCache = { jar: null, at: 0, key: '' };
const COOKIE_TTL_MS = 15 * 60 * 1000;

async function loginCookies(config, force = false) {
  const key = `${config.baseUrl}|${config.username}`;
  if (!force && cookieCache.key === key && cookieCache.jar && Date.now() - cookieCache.at < COOKIE_TTL_MS) {
    return cookieCache.jar;
  }
  try {
    const url = buildUrl(config.baseUrl, '/sitecore/api/ssc/auth/login');
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        domain: config.domain || 'sitecore',
        username: config.username,
        password: config.password,
      }),
    });
    const cookies = (res.headers.getSetCookie?.() ?? []).map((c) => c.split(';')[0]);
    const jar = cookies.join('; ');
    if (res.ok && jar) {
      cookieCache = { jar, at: Date.now(), key };
      return jar;
    }
  } catch {
    /* endpoint unavailable — Basic auth alone will have to do */
  }
  cookieCache = { jar: null, at: Date.now(), key };
  return null;
}

// ── Path encoding ─────────────────────────────────────────────────────────────

/**
 * Encode a Sitecore item path segment-by-segment so that path separators are
 * preserved while special characters inside each segment are encoded.
 * e.g. "/sitecore/content/My Site" → "/sitecore/content/My%20Site"
 */
export function encodeSitecoreItem(item) {
  return item
    .split('/')
    .map((segment) => encodeURIComponent(segment))
    .join('/');
}

// ── HTTP dispatcher (JSON) ────────────────────────────────────────────────────

/**
 * Call a Sitecore endpoint and return a structured JSON string:
 * { status, ok, url, data }
 *
 * @param {{ method: string, path: string, query?: object, body?: unknown, headers?: object }} args
 * @returns {Promise<string>}
 */
export async function callSitecore({ method, path, query, body, headers }) {
  const config = getConfig();
  const url = buildUrl(config.baseUrl, path, query);

  const doFetch = async (cookieJar) =>
    fetch(url, {
      method,
      headers: {
        Authorization: buildAuthHeader(config),
        ...(cookieJar ? { Cookie: cookieJar } : {}),
        Accept: 'application/json',
        'Content-Type': 'application/json',
        ...(headers ?? {}),
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

  let response = await doFetch(await loginCookies(config));
  // Stale/rejected session → force one re-login and retry.
  if (response.status === 401 || response.status === 403) {
    const fresh = await loginCookies(config, true);
    if (fresh) response = await doFetch(fresh);
  }

  const text = await response.text();
  let parsed;
  try {
    parsed = text ? JSON.parse(text) : null;
  } catch {
    parsed = text;
  }

  return JSON.stringify({ status: response.status, ok: response.ok, url, data: parsed }, null, 2);
}

// ── HTTP dispatcher (binary) ──────────────────────────────────────────────────

/**
 * Call a Sitecore endpoint that returns binary data.
 * On success returns { status, ok, url, contentType, size, dataBase64 }.
 * On failure returns { status, ok, url, contentType, data } with error text.
 *
 * @param {{ method: string, path: string, query?: object, body?: Buffer, headers?: object }} args
 * @returns {Promise<string>}
 */
export async function callSitecoreBinary({ method, path, query, body, headers }) {
  const config = getConfig();
  const url = buildUrl(config.baseUrl, path, query);

  const doFetch = async (cookieJar) =>
    fetch(url, {
      method,
      headers: {
        Authorization: buildAuthHeader(config),
        ...(cookieJar ? { Cookie: cookieJar } : {}),
        Accept: '*/*',
        ...(headers ?? {}),
      },
      body: body ? new Uint8Array(body) : undefined,
    });

  let response = await doFetch(await loginCookies(config));
  if (response.status === 401 || response.status === 403) {
    const fresh = await loginCookies(config, true);
    if (fresh) response = await doFetch(fresh);
  }

  const contentType = response.headers.get('content-type') ?? 'application/octet-stream';

  if (!response.ok) {
    const errorText = await response.text();
    return JSON.stringify({ status: response.status, ok: false, url, contentType, data: errorText }, null, 2);
  }

  const bytes = Buffer.from(await response.arrayBuffer());
  return JSON.stringify(
    { status: response.status, ok: true, url, contentType, size: bytes.length, dataBase64: bytes.toString('base64') },
    null,
    2
  );
}
