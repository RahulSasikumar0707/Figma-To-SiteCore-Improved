import React, { useState } from 'react';

export default function UrlForm({ onSubmit, busy }) {
  const [figmaUrl, setFigmaUrl] = useState('');
  const [sitecoreUrl, setSitecoreUrl] = useState('');

  function submit(e) {
    e.preventDefault();
    if (!figmaUrl.trim() || !sitecoreUrl.trim() || busy) return;
    onSubmit(figmaUrl.trim(), sitecoreUrl.trim());
  }

  return (
    <form className="url-form" onSubmit={submit}>
      <label>
        <span>Figma design URL</span>
        <input
          type="url"
          placeholder="https://www.figma.com/design/<fileKey>/<name>?node-id=68569-2790"
          value={figmaUrl}
          onChange={(e) => setFigmaUrl(e.target.value)}
          disabled={busy}
          required
        />
        <small>Select the frame in Figma → right-click → Copy link to selection (must contain node-id).</small>
      </label>
      <label>
        <span>Sitecore page URL</span>
        <input
          type="url"
          placeholder="https://<cm-host>/sitecore/content/<Site>/Home/<Page>"
          value={sitecoreUrl}
          onChange={(e) => setSitecoreUrl(e.target.value)}
          disabled={busy}
          required
        />
        <small>Content-path form, e.g. https://affinitycmpd103.gilead.com/sitecore/content/EDS/…/Home/LivdelziApril7-1</small>
      </label>
      <button type="submit" disabled={busy}>
        {busy ? 'Comparing…' : 'Compare'}
      </button>
    </form>
  );
}
