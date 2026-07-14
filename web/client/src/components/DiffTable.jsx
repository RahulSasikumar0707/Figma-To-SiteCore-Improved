import React from 'react';

const TYPE_META = {
  missing: { label: 'Missing in Sitecore', cls: 'missing' },
  extra: { label: 'Extra in Sitecore', cls: 'extra' },
  mismatch: { label: 'Mismatch', cls: 'mismatch' },
  visual: { label: 'Visual', cls: 'visual' },
};

function Value({ v }) {
  if (v == null || v === '') return <em className="none">—</em>;
  const s = String(v);
  return <span title={s}>{s.length > 160 ? `${s.slice(0, 160)}…` : s}</span>;
}

export default function DiffTable({ differences, selected, onToggle, onToggleAll }) {
  if (!differences.length) {
    return <section className="banner good">✔ No differences found — the Sitecore page matches the design.</section>;
  }

  const patchableIds = differences.filter((d) => d.patchable).map((d) => d.id);
  const allChecked = patchableIds.length > 0 && patchableIds.every((id) => selected.has(id));

  return (
    <section className="diff-table">
      <h2>
        Differences <span className="count">{differences.length}</span>
      </h2>
      <table>
        <thead>
          <tr>
            <th className="check">
              <input
                type="checkbox"
                checked={allChecked}
                disabled={!patchableIds.length}
                onChange={(e) => onToggleAll(patchableIds, e.target.checked)}
                title="Select all patchable"
              />
            </th>
            <th>Type</th>
            <th>Section</th>
            <th>Description</th>
            <th>Figma (design)</th>
            <th>Sitecore (page)</th>
            <th>Patch target</th>
          </tr>
        </thead>
        <tbody>
          {differences.map((d) => {
            const meta = TYPE_META[d.type] || TYPE_META.mismatch;
            return (
              <tr key={d.id} className={selected.has(d.id) ? 'selected' : ''}>
                <td className="check">
                  {d.patchable ? (
                    <input type="checkbox" checked={selected.has(d.id)} onChange={() => onToggle(d.id)} />
                  ) : (
                    <span className="not-patchable" title={d.patchNote || 'Requires manual authoring'}>
                      ✋
                    </span>
                  )}
                </td>
                <td>
                  <span className={`pill ${meta.cls}`}>{meta.label}</span>
                  <span className={`severity ${d.severity}`}>{d.severity}</span>
                </td>
                <td>{d.section}</td>
                <td className="desc">{d.description}</td>
                <td className="value figma">
                  <Value v={d.figmaValue} />
                </td>
                <td className="value sitecore">
                  <Value v={d.sitecoreValue} />
                </td>
                <td className="target">
                  {d.patchable ? (
                    <>
                      <code>{d.sitecoreItemPath?.split('/').slice(-2).join('/')}</code>
                      <code className="field">{d.sitecoreField}</code>
                    </>
                  ) : (
                    <em className="none">{d.patchNote ? 'manual' : '—'}</em>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="hint">
        ✋ = not automatically patchable (needs a new component/rendering — author it in Sitecore, then re-compare).
      </p>
    </section>
  );
}
