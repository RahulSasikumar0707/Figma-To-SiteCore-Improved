import Anthropic from '@anthropic-ai/sdk';
import { log } from '../utils/log.js';

export function makeClient(apiKey) {
  return new Anthropic({ apiKey, maxRetries: 0 });
}

/** Known-good current model ids, most capable first (per Anthropic Models API). */
const FALLBACK_MODELS = ['claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-5', 'claude-haiku-4-5'];

/**
 * Validates the configured model against the Models API; if it doesn't exist
 * on this API key (e.g. a retired/deprecated id in .env), falls back to the
 * most capable available model instead of failing every request.
 * Returns { id, outputCap } — outputCap is the model's max output tokens
 * (null when the lookup couldn't run), so callers can clamp LLM_MAX_TOKENS.
 */
export async function resolveModel(client, preferred) {
  const candidates = [preferred, ...FALLBACK_MODELS.filter((m) => m !== preferred)];
  for (const id of candidates) {
    try {
      const m = await client.models.retrieve(id);
      if (id !== preferred) {
        log.warn(`Model "${preferred}" is not available on this API key — using "${id}" instead.`);
      }
      return { id, outputCap: Number.isFinite(m?.max_tokens) ? m.max_tokens : null };
    } catch (err) {
      if (err?.status === 404) continue;
      // Non-404 (auth, network, overload): don't block startup on validation —
      // return the candidate being checked (never an id an earlier iteration
      // already proved missing with a 404) and let the real call surface it.
      return { id, outputCap: null };
    }
  }
  return { id: preferred, outputCap: null };
}

/**
 * Single logical completion with retry/backoff on transient failures
 * (429/5xx/overload) and automatic continuation when the response is cut off
 * at max_tokens: the partial assistant turn is replayed verbatim (thinking
 * blocks included — the API requires them unmodified on Fable 5) followed by
 * a user turn asking the model to resume from the exact cut-off point.
 * Prefilling the assistant turn is not an option — last-assistant-turn
 * prefill returns 400 on Fable 5 / Opus 4.6+ / Sonnet 4.6+.
 * `messages` may contain image blocks (used by the reviewer for visual diffing).
 * Note: no temperature/top_p — sampling params are rejected (400) on
 * Fable 5 / Opus 4.7+ / Sonnet 5.
 */
export async function complete({ client, model, system, messages, maxTokens = 8000, maxContinuations = 3, continuationHint = '' }) {
  const convo = [...messages];
  const usage = { input_tokens: 0, output_tokens: 0 };
  let text = '';
  let stopReason;
  let truncated = false;
  for (let round = 0; ; round++) {
    let res;
    try {
      res = await requestWithRetry({ client, model, system, messages: convo, maxTokens });
    } catch (err) {
      // A failed continuation must not discard the output already received —
      // return the accumulated text flagged as truncated instead of crashing
      // the run (the parser drops the cut file; refine() keeps the previous
      // complete version via its merge).
      if (round > 0) {
        log.warn(`Continuation request failed (${err?.status || err?.constructor?.name || err}) — returning the partial output as truncated.`);
        break;
      }
      throw err;
    }
    let roundText = res.content
      .filter((b) => b.type === 'text')
      .map((b) => b.text)
      .join('');
    if (round > 0) roundText = stitchContinuation(text, roundText);
    text += roundText;
    usage.input_tokens += res.usage?.input_tokens ?? 0;
    usage.output_tokens += res.usage?.output_tokens ?? 0;
    stopReason = res.stop_reason;
    // `truncated` tracks whether the accumulated output is known-incomplete:
    // a max_tokens cut sets it, and only a round that finishes normally
    // clears it. An abnormal stop (refusal, model_context_window_exceeded, …)
    // in a continuation round must NOT launder an earlier cut, or the
    // parser's drop-incomplete-file guard is silently disabled.
    if (stopReason === 'max_tokens') truncated = true;
    else if (stopReason === 'end_turn' || stopReason === 'stop_sequence') truncated = false;
    if (stopReason !== 'max_tokens') {
      if (stopReason === 'refusal') log.warn('LLM declined the request (stop_reason "refusal") — output is unusable.');
      break;
    }
    if (round >= maxContinuations || !roundText) {
      log.warn(`LLM response still truncated at max_tokens after ${round} continuation(s) — output may be incomplete.`);
      break;
    }
    log.warn(`LLM response hit max_tokens — continuing from the cut-off (${round + 1}/${maxContinuations})…`);
    convo.push(
      { role: 'assistant', content: res.content },
      { role: 'user', content: continuePrompt(text, continuationHint) },
    );
  }
  return { text, usage, stopReason, truncated };
}

function continuePrompt(text, hint) {
  return [
    `Your previous message was interrupted by the output token limit — it is incomplete, and there is always more to emit (at minimum whatever closing delimiter your format requires). It ends with:\n${text.slice(-300)}`,
    'Resume from EXACTLY that cut-off point, mid-line if necessary. Your message must start with the next character of the content itself — no preamble, no code fences, and no repetition of anything already emitted. Never conclude the response was already complete.',
    hint,
  ].filter(Boolean).join('\n\n');
}

/**
 * Normalizes a continuation round before splicing it onto the accumulated
 * text, so prompt slop cannot corrupt the stitched output in ways the
 * downstream parser can't detect.
 */
function stitchContinuation(prior, next) {
  // Strip an accidental code fence wrapping (or opening) the continuation.
  const fenced = next.match(/^```[a-z]*\n([\s\S]*?)\n?```\s*$/);
  if (fenced) {
    log.warn('Continuation arrived wrapped in a code fence — stripping it.');
    next = fenced[1];
  } else if (/^```[a-z]*\n/.test(next)) {
    log.warn('Continuation opened with a code fence line — stripping it.');
    next = next.replace(/^```[a-z]*\n/, '');
  }
  // A continuation that starts with a delimiter must land at the start of a
  // line — the parser's regexes are line-anchored, and a mid-line
  // "===FILE: ...===" would silently swallow that whole file into the
  // previous one.
  if (/^===(FILE:|END===)/.test(next) && prior && !prior.endsWith('\n')) next = '\n' + next;
  return next;
}

async function requestWithRetry({ client, model, system, messages, maxTokens }) {
  const maxAttempts = 4;
  let lastErr;
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      // Streaming: required by the SDK for large max_tokens (>10-minute guard),
      // and keeps long generations from tripping HTTP idle timeouts.
      const stream = client.messages.stream({
        model,
        max_tokens: maxTokens,
        system,
        messages,
      });
      return await stream.finalMessage();
    } catch (err) {
      lastErr = err;
      const status = err?.status ?? 0;
      const retriable = status === 429 || status === 529 || status >= 500 || err instanceof Anthropic.APIConnectionError;
      if (!retriable || attempt === maxAttempts) throw err;
      const wait = Math.min(30000, 2000 * 2 ** (attempt - 1));
      log.warn(`Anthropic API ${status || err.constructor.name}; retrying in ${wait / 1000}s (attempt ${attempt}/${maxAttempts})`);
      await new Promise((r) => setTimeout(r, wait));
    }
  }
  throw lastErr;
}

export function imageBlock(buffer, mediaType = 'image/png') {
  return {
    type: 'image',
    source: { type: 'base64', media_type: mediaType, data: buffer.toString('base64') },
  };
}

/**
 * Extract the first parseable JSON object from an LLM response that may wrap
 * it in prose and/or code fences. Every fenced block is tried (json-labelled
 * fences first), then the raw text — the response often contains other fenced
 * code (css/html) before the verdict JSON.
 */
export function parseJsonLoose(text) {
  const fences = [...text.matchAll(/```(json)?[^\S\n]*\n?([\s\S]*?)```/g)]
    .sort((a, b) => (b[1] ? 1 : 0) - (a[1] ? 1 : 0))
    .map((m) => m[2]);
  const candidates = [...fences, text];

  let emptyFallback = null;
  for (const candidate of candidates) {
    // Scan every balanced top-level {...} in the candidate — CSS like `.x{}`
    // parses as valid (empty) JSON and must not shadow the real object.
    for (const objText of balancedObjects(candidate)) {
      try {
        const parsed = JSON.parse(objText);
        if (parsed && typeof parsed === 'object' && Object.keys(parsed).length) return parsed;
        if (parsed && typeof parsed === 'object') emptyFallback = emptyFallback ?? parsed;
      } catch {
        // not valid JSON — keep scanning
      }
    }
  }
  if (emptyFallback) return emptyFallback;
  throw new Error('No JSON object found in LLM response');
}

/** Yields each balanced top-level {...} substring of the text, in order. */
function* balancedObjects(text) {
  let i = 0;
  while (i < text.length) {
    const start = text.indexOf('{', i);
    if (start === -1) return;
    let depth = 0;
    let inStr = false;
    let esc = false;
    let end = -1;
    for (let j = start; j < text.length; j++) {
      const ch = text[j];
      if (esc) { esc = false; continue; }
      if (ch === '\\') { esc = inStr; continue; }
      if (ch === '"') inStr = !inStr;
      if (inStr) continue;
      if (ch === '{') depth++;
      if (ch === '}') {
        depth--;
        if (depth === 0) { end = j; break; }
      }
    }
    if (end === -1) return; // unbalanced tail
    yield text.slice(start, end + 1);
    i = end + 1;
  }
}
