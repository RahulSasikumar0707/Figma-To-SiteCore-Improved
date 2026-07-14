import React, { useState } from 'react';
import { applyPatch, publish } from '../api.js';

export default function PatchPanel({ sessionId, differences, selected }) {
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [published, setPublished] = useState(false);

  const selectedIds = [...selected];
  const selectedCount = selectedIds.length;

  async function run(dryRun) {
    setBusy(true);
    setError(null);
    setResults(null);
    setPublished(false);
    try {
      const { results: r } = await applyPatch(sessionId, selectedIds, dryRun);
      setResults({ dryRun, list: r });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function doPublish() {
    setBusy(true);
    setError(null);
    try {
      await publish(sessionId);
      setPublished(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const patchedOk = results && !results.dryRun && results.list.some((r) => r.ok);

  return (
    <section className="patch-panel">
      <h2>Patch Sitecore</h2>
      <p>
        {selectedCount
          ? `${selectedCount} difference(s) selected. Only the selected fields are updated — everything else on the page is untouched.`
          : 'Select the differences you want to push into Sitecore using the checkboxes above.'}
      </p>
      <div className="actions">
        <button className="ghost" disabled={!selectedCount || busy} onClick={() => run(true)}>
          Preview (dry run)
        </button>
        <button className="primary" disabled={!selectedCount || busy} onClick={() => run(false)}>
          {busy ? 'Working…' : `Patch ${selectedCount || ''} item(s) in Sitecore`}
        </button>
        {patchedOk && (
          <button className="ghost" disabled={busy || published} onClick={doPublish}>
            {published ? '✔ Publish triggered' : 'Publish page to web'}
          </button>
        )}
      </div>

      {error && <div className="banner error">⚠ {error}</div>}

      {results && (
        <table className="patch-results">
          <thead>
            <tr>
              <th>Status</th>
              <th>Item</th>
              <th>Field</th>
              <th>{results.dryRun ? 'Value that would be written' : 'Written value'}</th>
            </tr>
          </thead>
          <tbody>
            {results.list.map((r, i) => {
              const diff = differences.find((d) => d.id === r.diffId);
              return (
                <tr key={i} className={r.ok ? 'ok' : r.skipped ? 'skip' : 'fail'}>
                  <td>{r.ok ? (results.dryRun ? '☑ would patch' : '✔ patched') : r.skipped ? '✋ manual' : '✖ failed'}</td>
                  <td>
                    <code>{(r.itemPath || diff?.sitecoreItemPath || '—').split('/').slice(-2).join('/')}</code>
                  </td>
                  <td>
                    <code>{r.field || diff?.sitecoreField || '—'}</code>
                  </td>
                  <td className="value">{r.appliedValue ? (r.appliedValue.length > 200 ? `${r.appliedValue.slice(0, 200)}…` : r.appliedValue) : r.error || '—'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
