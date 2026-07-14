import React from 'react';

const PHASE_LABELS = {
  queued: 'Queued',
  figma: 'Reading Figma design',
  sitecore: 'Reading Sitecore page',
  llm: 'AI comparison',
  done: 'Done',
  error: 'Failed',
  patched: 'Patched',
  published: 'Published',
};

export default function ProgressLog({ progress, running }) {
  return (
    <section className="progress-log">
      {running && <div className="spinner" aria-label="working" />}
      <ul>
        {progress.map((p, i) => (
          <li key={i} className={p.phase === 'error' ? 'err' : ''}>
            <span className="phase">{PHASE_LABELS[p.phase] || p.phase}</span>
            <span className="msg">{p.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
