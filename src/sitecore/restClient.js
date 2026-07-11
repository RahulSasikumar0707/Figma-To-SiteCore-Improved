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
  const base = baseUrl.replace(/\/$/, '');
  const rel = path.replace(/^\//, '');
  const url = new URL(`${base}/${rel}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
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

  const response = await fetch(url, {
    method,
    headers: {
      Authorization: buildAuthHeader(config),
      Accept: 'application/json',
      'Content-Type': 'application/json',
      ...(headers ?? {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

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

  const response = await fetch(url, {
    method,
    headers: {
      Authorization: buildAuthHeader(config),
      Accept: '*/*',
      ...(headers ?? {}),
    },
    body: body ? new Uint8Array(body) : undefined,
  });

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
