import Anthropic from '@anthropic-ai/sdk';
import { log } from '../utils/log.js';

export function makeClient(apiKey) {
  return new Anthropic({ apiKey, maxRetries: 0 });
}

/** Known-good current model ids, most capable first (per Anthropic Models API). */
const FALLBACK_MODELS = ['claude-fable-5', 'claude-opus-4-8', 'claude-sonnet-5', 'claude-opus-4-7'];

/**
 * Validates the configured model against the Models API; if it doesn't exist
 * on this API key (e.g. a retired/deprecated id in .env), falls back to the
 * most capable available model instead of failing every request.
 */
export async function resolveModel(client, preferred) {
  const candidates = [preferred, ...FALLBACK_MODELS.filter((m) => m !== preferred)];
  for (const id of candidates) {
    try {
      await client.models.retrieve(id);
      if (id !== preferred) {
        log.warn(`Model "${preferred}" is not available on this API key — using "${id}" instead.`);
      }
      return id;
    } catch (err) {
      if (err?.status === 404) continue;
      // Non-404 (auth, network): don't block startup on validation; let the real call surface it.
      return preferred;
    }
  }
  return preferred;
}

/**
 * Single completion with retry/backoff on transient failures (429/5xx/overload).
 * `messages` may contain image blocks (used by the reviewer for visual diffing).
 * When the response stops at max_tokens, the generation is automatically
 * continued (assistant-prefill) and the parts are stitched together, so large
 * multi-file outputs are never silently truncated.
 * Note: no temperature/top_p — sampling params are rejected (400) on
 * Fable 5 / Opus 4.7+ / Sonnet 5.
 */
export async function complete({ client, model, system, messages, maxTokens = 8000, maxContinuations = 4 }) {
  const usage = { input_tokens: 0, output_tokens: 0 };
  let acc = '';
  let stopReason = null;

  for (let round = 0; round <= maxContinuations; round++) {
    // Prefill continuation: resend the conversation with the partial output as
    // the final assistant message; the model resumes exactly where it stopped.
    // (The API rejects prefill with trailing whitespace, so trim and keep the
    // accumulator consistent with what the model actually sees.)
    if (acc) acc = acc.replace(/\s+$/, '');
    const msgs = acc ? [...messages, { role: 'assistant', content: acc }] : messages;

    const res = await callWithRetry({ client, model, system, messages: msgs, maxTokens });
    acc += res.content
      .filter((b) => b.type === 'text')
      .map((b) => b.text)
      .join('');
    usage.input_tokens += res.usage?.input_tokens ?? 0;
    usage.output_tokens += res.usage?.output_tokens ?? 0;
    stopReason = res.stop_reason;

    if (stopReason !== 'max_tokens') break;
    if (round < maxContinuations) {
      log.warn(`LLM response hit the max_tokens limit — continuing generation (${round + 1}/${maxContinuations})…`);
    } else {
      log.warn('LLM response hit the max_tokens limit and the continuation budget is exhausted — output may be truncated.');
    }
  }
  return { text: acc, usage, stopReason };
}

async function callWithRetry({ client, model, system, messages, maxTokens }) {
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
