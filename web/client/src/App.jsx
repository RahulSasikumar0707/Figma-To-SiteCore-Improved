import React, { useEffect, useRef, useState } from 'react';
import UrlForm from './components/UrlForm.jsx';
import ProgressLog from './components/ProgressLog.jsx';
import ScreenshotPair from './components/ScreenshotPair.jsx';
import DiffTable from './components/DiffTable.jsx';
import PatchPanel from './components/PatchPanel.jsx';
import { startCompare, getCompare } from './api.js';

export default function App() {
  const [sessionId, setSessionId] = useState(null);
  const [phase, setPhase] = useState('idle');
  const [progress, setProgress] = useState([]);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(new Set());
  const pollRef = useRef(null);

  const running = ['queued', 'figma', 'sitecore', 'llm'].includes(phase);

  useEffect(() => {
    if (!sessionId || !running) return undefined;
    pollRef.current = setInterval(async () => {
      try {
        const state = await getCompare(sessionId);
        setPhase(state.phase);
        setProgress(state.progress || []);
        if (state.error) setError(state.error);
        if (state.result) {
          setResult(state.result);
          // Pre-select the patchable diffs — the common case is "fix all".
          setSelected(new Set(state.result.differences.filter((d) => d.patchable).map((d) => d.id)));
        }
      } catch (err) {
        setError(err.message);
        setPhase('error');
      }
    }, 1500);
    return () => clearInterval(pollRef.current);
  }, [sessionId, running]);

  async function onCompare(figmaUrl, sitecoreUrl) {
    setError(null);
    setResult(null);
    setSelected(new Set());
    setProgress([]);
    try {
      const { sessionId: id } = await startCompare(figmaUrl, sitecoreUrl);
      setSessionId(id);
      setPhase('queued');
    } catch (err) {
      setError(err.message);
      setPhase('error');
    }
  }

  function toggle(id) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll(patchableIds, check) {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of patchableIds) check ? next.add(id) : next.delete(id);
      return next;
    });
  }

  return (
    <div className="app">
      <header>
        <h1>Figma ↔ Sitecore Comparison</h1>
        <p className="subtitle">
          Paste a Figma frame link and a Sitecore page URL. Claude compares the design against the
          live page, lists missing / extra / mismatched content, and patches the fields you select —
          without touching anything else on the page.
        </p>
      </header>

      <UrlForm onSubmit={onCompare} busy={running} />

      {error && <div className="banner error">⚠ {error}</div>}

      {(running || progress.length > 0) && <ProgressLog progress={progress} running={running} />}

      {result && (
        <>
          <section className="score-card">
            <div className={`score ${result.matchScore >= 90 ? 'good' : result.matchScore >= 70 ? 'ok' : 'bad'}`}>
              {result.matchScore}
              <span>/100</span>
            </div>
            <div className="score-text">
              <h2>Content parity</h2>
              <p>{result.summary}</p>
              <p className="meta">
                {result.sitecore.items} Sitecore item(s) scanned · model {result.model} ·{' '}
                <a href={result.sitecore.pageUrl} target="_blank" rel="noreferrer">open page</a>
              </p>
            </div>
          </section>

          <ScreenshotPair sessionId={sessionId} figma={result.figma} sitecore={result.sitecore} />

          <DiffTable
            differences={result.differences}
            selected={selected}
            onToggle={toggle}
            onToggleAll={toggleAll}
          />

          <PatchPanel
            sessionId={sessionId}
            differences={result.differences}
            selected={selected}
          />
        </>
      )}
    </div>
  );
}
