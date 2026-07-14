async function json(res) {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

export async function startCompare(figmaUrl, sitecoreUrl) {
  const res = await fetch('/api/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ figmaUrl, sitecoreUrl }),
  });
  return json(res);
}

export async function getCompare(sessionId) {
  return json(await fetch(`/api/compare/${sessionId}`));
}

export function imageUrl(sessionId, which) {
  return `/api/compare/${sessionId}/image/${which}`;
}

export async function applyPatch(sessionId, diffIds, dryRun = false) {
  const res = await fetch(`/api/compare/${sessionId}/patch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ diffIds, dryRun }),
  });
  return json(res);
}

export async function publish(sessionId) {
  const res = await fetch(`/api/compare/${sessionId}/publish`, { method: 'POST' });
  return json(res);
}
