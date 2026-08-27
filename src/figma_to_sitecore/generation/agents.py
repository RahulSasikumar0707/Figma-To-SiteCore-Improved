from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from pydantic import SecretStr

from figma_to_sitecore.domain.models import GenerationContext, ImagePayload, ReviewVerdict
from figma_to_sitecore.generation.parsers import parse_generated_files, parse_json_loose
from figma_to_sitecore.generation.prompts import (
    GENERATOR_SYSTEM_PROMPT,
    REVIEWER_SYSTEM_PROMPT,
    generator_context,
)
from figma_to_sitecore.utils.files import write_file
from figma_to_sitecore.utils.logging import log

EXPECTED_FILES = ["index.html", "css/styles.css", "js/script.js", "component-map.json"]

# Claude 4.6 and later reject an assistant message as the final turn, so a
# truncated response is resumed by asking for the remainder in a user turn.
CONTINUATION_INSTRUCTION = (
    "Your previous message stopped at the output token limit, mid-stream. Continue from the exact "
    "character where it stopped. Do not repeat any text already sent, do not restart a file, do not "
    "re-open a ===FILE: …=== header that is already open, and do not add commentary. Finish with "
    "===END=== once every required file is complete."
)

_ADAPTIVE_THINKING_MODELS = re.compile(
    r"(fable|mythos|opus-5|opus-4-[678]|sonnet-5|sonnet-4-6)", re.I
)
# ``xhigh`` arrived with Opus 4.7; earlier adaptive-thinking models only accept
# low/medium/high/max and reject it outright.
_XHIGH_EFFORT_MODELS = re.compile(r"(fable|mythos|opus-5|opus-4-[78]|sonnet-5)", re.I)

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


class ModelRefusalError(RuntimeError):
    """The safety classifier declined the request instead of answering."""


@dataclass(slots=True)
class Completion:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None


def supports_adaptive_thinking(model: str) -> bool:
    return bool(_ADAPTIVE_THINKING_MODELS.search(model))


def resolve_effort(model: str, effort: str | None) -> str | None:
    """Clamp the configured effort to what the target model actually accepts."""
    if not effort or not supports_adaptive_thinking(model):
        return None
    normalized = effort.strip().lower()
    if normalized not in EFFORT_LEVELS:
        log.warning("Unknown reasoning effort %r; falling back to the model default", effort)
        return None
    if normalized == "xhigh" and not _XHIGH_EFFORT_MODELS.search(model):
        return "high"
    return normalized


def create_anthropic_model(
    *,
    api_key: str,
    model: str,
    max_tokens: int,
    reasoning_effort: str | None = None,
) -> BaseChatModel:
    """Create the provider adapter at the infrastructure boundary."""
    from langchain_anthropic import ChatAnthropic

    options: dict[str, Any] = {}
    if supports_adaptive_thinking(model):
        # Thinking is always on for these models; requesting it explicitly keeps
        # behaviour identical across the family. Summaries are left off so the
        # output budget is spent on the deliverable files.
        options["thinking"] = {"type": "adaptive"}
        effort = resolve_effort(model, reasoning_effort)
        if effort:
            options["output_config"] = {"effort": effort}
    return ChatAnthropic(
        api_key=SecretStr(api_key),
        model_name=model,
        max_tokens_to_sample=max_tokens,
        max_retries=3,
        timeout=1800,
        # Large page generations can take longer than the non-streaming HTTP
        # read timeout before response headers arrive. Streaming keeps the
        # connection active while LangChain still aggregates one AIMessage, and
        # it is required at all for the 128K output ceiling.
        streaming=True,
        stop=None,
        **options,
    )


def image_block(image: ImagePayload) -> dict[str, str]:
    """LangChain standard base64 image content block."""
    return {
        "type": "image",
        "base64": base64.b64encode(image.data).decode("ascii"),
        "mime_type": image.media_type,
    }


def message_text(message: BaseMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") in {"text", "output_text"}:
            parts.append(str(block.get("text", "")))
    return "".join(parts)


def _stop_reason(message: BaseMessage) -> str | None:
    return message.response_metadata.get("stop_reason") or message.response_metadata.get("finish_reason")


def _refusal_detail(message: BaseMessage) -> str:
    details = message.response_metadata.get("stop_details") or {}
    if not isinstance(details, dict):
        return "no detail supplied"
    category = details.get("category") or "unspecified"
    explanation = details.get("explanation") or "no explanation supplied"
    return f"category {category}: {explanation}"


def _usage(message: BaseMessage) -> tuple[int, int]:
    usage = getattr(message, "usage_metadata", None) or message.response_metadata.get("usage") or {}
    return int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0))


async def complete(
    model: BaseChatModel,
    *,
    system: str,
    messages: list[BaseMessage],
    max_continuations: int = 4,
) -> Completion:
    """Invoke the model, resuming through the output-token ceiling when needed.

    The resumption turn is a *user* message. Continuing by re-sending the partial
    answer as a trailing assistant message (prefill) is rejected with HTTP 400 by
    every Claude model from 4.6 onward, which previously aborted the whole
    refinement loop the first time a page exceeded the output budget.
    """
    conversation = list(messages)
    accumulated = ""
    input_tokens = 0
    output_tokens = 0
    reason: str | None = None
    for round_number in range(max_continuations + 1):
        response = await model.ainvoke([SystemMessage(content=system), *conversation])
        chunk = message_text(response)
        used_input, used_output = _usage(response)
        input_tokens += used_input
        output_tokens += used_output
        reason = _stop_reason(response)
        if reason == "refusal":
            raise ModelRefusalError(f"The model declined this request ({_refusal_detail(response)}).")
        # Append verbatim: the model was told to continue from the exact character
        # it stopped at, so trimming here can glue a ===FILE:=== header onto the
        # previous line and make the ^-anchored parser drop that file silently.
        accumulated += chunk
        if reason not in {"max_tokens", "length"}:
            break
        if round_number >= max_continuations:
            log.warning("Output still truncated after %s continuation(s)", max_continuations)
            break
        log.warning(
            "Model output reached its token limit; requesting continuation %s/%s",
            round_number + 1,
            max_continuations,
        )
        conversation = [
            *conversation,
            AIMessage(content=chunk),
            HumanMessage(content=CONTINUATION_INSTRUCTION),
        ]
    return Completion(accumulated, input_tokens, output_tokens, reason)


class GeneratorAgent:
    def __init__(self, model: BaseChatModel, raw_output_dir: Path | None = None) -> None:
        self._model = model
        self._raw_output_dir = raw_output_dir or Path.cwd()

    async def generate(
        self,
        context: GenerationContext,
        design_references: list[tuple[str, ImagePayload]] | None = None,
    ) -> dict[str, str]:
        log.info(
            "Generator agent: producing EDS + Bootstrap code%s",
            f" grounded on {len(design_references)} Figma design screenshot(s)"
            if design_references
            else "",
        )
        # The Figma design renders are the visual ground truth the browser render
        # is later compared against, so the first candidate is generated against
        # them rather than discovering the visuals only at review time.
        content: list[str | dict[Any, Any]] = []
        if design_references:
            content.append(
                {
                    "type": "text",
                    "text": (
                        "VISUAL GROUND TRUTH — rendered Figma design. A browser render of your "
                        "output is compared against these screenshots pixel by pixel; reproduce "
                        "them exactly at each labelled width, using the numeric spec below for "
                        "exact values."
                    ),
                }
            )
            for label, image in design_references:
                content.extend([{"type": "text", "text": label}, image_block(image)])
        content.append({"type": "text", "text": generator_context(context)})
        user_message = HumanMessage(content=content)
        result = await complete(
            self._model,
            system=GENERATOR_SYSTEM_PROMPT,
            messages=[user_message],
        )
        log.info("Generator tokens: %s input, %s output", result.input_tokens, result.output_tokens)
        files = {
            name: content
            for name, content in parse_generated_files(
                result.text,
                truncated=result.stop_reason in {"max_tokens", "length"},
            ).items()
            if name in EXPECTED_FILES
        }
        all_text = result.text
        # Everything the model has produced so far, replayed as its own turn on
        # each retry so a later file (e.g. component-map.json) is always written
        # with the already-delivered markup and styles in view.
        delivered_text = result.text

        for round_number in range(1, 4):
            missing = [name for name in EXPECTED_FILES if name not in files]
            if not missing:
                break
            log.warning("Generator omitted %s; requesting continuation %s/3", ", ".join(missing), round_number)
            history: list[BaseMessage] = [user_message]
            if delivered_text.strip():
                history.append(AIMessage(content=delivered_text.strip()))
            history.append(
                HumanMessage(
                    content=f"Output only the missing files ({', '.join(missing)}) in exact ===FILE: name=== blocks, then ===END===. Do not repeat delivered files."
                )
            )
            result = await complete(self._model, system=GENERATOR_SYSTEM_PROMPT, messages=history)
            all_text += f"\n\n--- continuation {round_number} ---\n{result.text}"
            delivered_text += f"\n{result.text}"
            files.update(
                {
                    name: content
                    for name, content in parse_generated_files(
                        result.text,
                        truncated=result.stop_reason in {"max_tokens", "length"},
                    ).items()
                    if name in EXPECTED_FILES
                }
            )
        self._assert_files(files, all_text, result.stop_reason, "generator")
        return files

    async def refine(
        self,
        context: GenerationContext,
        files: dict[str, str],
        review: ReviewVerdict,
        pixel_mismatch: float | None,
        reference_image: ImagePayload | None,
        render_image: ImagePayload | None,
        diff_image: ImagePayload | None,
        visual_diagnostics: dict[str, Any] | None = None,
        responsive_diagnostics: list[dict[str, Any]] | None = None,
        stagnation_count: int = 0,
        geometry_diagnostics: dict[str, Any] | None = None,
        geometry_headline: str | None = None,
    ) -> dict[str, str]:
        log.info("Generator agent: applying %s review fixes", len(review.issues))
        file_dump = "\n".join(f"===FILE: {name}===\n{content}" for name, content in files.items())
        mismatch = f"; pixel mismatch {pixel_mismatch:.2f}%" if pixel_mismatch is not None else ""
        asset_summary = [
            {key: asset.get(key) for key in ("id", "name", "file", "w", "h")}
            for asset in context.asset_manifest
        ]
        sections = [
            f"The independent reviewer scored this conversion {review.score}/100{mismatch}.",
        ]
        if geometry_headline:
            sections.append(f"# DOMINANT LAYOUT ERROR\n{geometry_headline}")
        sections.extend(
            [
                f"# REVIEWER ISSUES\n{json.dumps([issue.model_dump() for issue in review.issues], indent=1)}",
                f"# CURRENT FILES\n{file_dump}",
                f"# DESIGN SPEC\n{context.spec_json}",
                f"# ASSETS\n{json.dumps(asset_summary, indent=1)}",
            ]
        )
        if geometry_diagnostics:
            sections.append(
                "# MEASURED GEOMETRY vs FIGMA (CSS pixels, from the live DOM)\n"
                "heightErrorPx is the element's own defect. offsetErrorPx[1] is mostly inherited from "
                "earlier sections. driftIntroducedPx is the new vertical error that appeared between "
                "the previous section and this one — fix those first, largest magnitude first.\n"
                f"{json.dumps(geometry_diagnostics, indent=1)}"
            )
        sections.extend(
            [
                f"# OBJECTIVE PIXEL DIAGNOSTICS\n{json.dumps(visual_diagnostics or {}, indent=1)}",
                f"# RESPONSIVE AUDIT\n{json.dumps(responsive_diagnostics or [], indent=1)}",
                (
                    "# CONVERGENCE STRATEGY\n"
                    "Correct total page height and section offsets before local decoration: while the "
                    "page height is wrong every later section is displaced and the image diff is "
                    "meaningless. Work down driftIntroducedPx in descending magnitude, then "
                    "heightErrorPx, then typography, then colour and decoration. Preserve regions "
                    "already at zero mismatch. "
                    f"The optimizer has seen {stagnation_count} consecutive non-improving candidate(s); "
                    "make a focused causal correction instead of broad restyling."
                ),
                "Fix every issue without regression. Return all four files complete in exact "
                "===FILE: ...=== blocks, with no prose.",
            ]
        )
        prompt = "\n\n".join(sections)
        content: list[str | dict[Any, Any]] = []
        for label, image in (
            ("TARGET — Figma design:", reference_image),
            ("CURRENT — browser render:", render_image),
            ("DIFF — highlighted mismatch:", diff_image),
        ):
            if image:
                content.extend([{"type": "text", "text": label}, image_block(image)])
        content.append({"type": "text", "text": prompt})
        result = await complete(
            self._model,
            system=GENERATOR_SYSTEM_PROMPT,
            messages=[HumanMessage(content=content)],
        )
        updated = {
            name: content
            for name, content in parse_generated_files(
                result.text,
                truncated=result.stop_reason in {"max_tokens", "length"},
            ).items()
            if name in EXPECTED_FILES
        }
        merged = {**files, **updated}
        self._assert_files(merged, result.text, result.stop_reason, "refine")
        return merged

    def _assert_files(
        self,
        files: dict[str, str],
        raw_text: str,
        stop_reason: str | None,
        label: str,
    ) -> None:
        missing = [name for name in ("index.html", "css/styles.css") if not files.get(name)]
        if not missing:
            return
        dump = self._raw_output_dir / f"llm-raw-{label}.txt"
        write_file(dump, f"stop_reason: {stop_reason}\nchars: {len(raw_text)}\n\n{raw_text}")
        preview = re.sub(r"\s+", " ", raw_text[:300]).strip()
        raise RuntimeError(
            f"Generator omitted {', '.join(missing)}; received {', '.join(files) or 'no files'}. "
            f"Raw response: {dump}. Starts with: {preview!r}"
        )


class ReviewerAgent:
    def __init__(self, model: BaseChatModel) -> None:
        self._model = model
        self._structured_model = model.with_structured_output(ReviewVerdict, include_raw=True)

    async def review(
        self,
        context: GenerationContext,
        files: dict[str, str],
        reference_image: ImagePayload | None,
        render_image: ImagePayload | None,
        diff_image: ImagePayload | None,
        pixel_mismatch: float | None,
        visual_diagnostics: dict[str, Any] | None = None,
        responsive_diagnostics: list[dict[str, Any]] | None = None,
        geometry_diagnostics: dict[str, Any] | None = None,
        contract_report: str | None = None,
    ) -> ReviewVerdict:
        log.info("Reviewer agent: auditing output against Figma")
        content: list[str | dict[Any, Any]] = []
        for label, image in (
            ("GROUND TRUTH — Figma design:", reference_image),
            ("GENERATED PAGE — current browser render:", render_image),
            ("PIXEL DIFF — highlighted mismatches:", diff_image),
        ):
            if image:
                content.extend([{"type": "text", "text": label}, image_block(image)])
        file_dump = "\n".join(f"===FILE: {name}===\n{value}" for name, value in files.items())
        assets = [{key: item.get(key) for key in ("name", "file", "w", "h")} for item in context.asset_manifest]
        mismatch = f"\nAutomated pixel mismatch: {pixel_mismatch:.2f}%" if pixel_mismatch is not None else ""
        text = (
            f"# DESIGN SPEC\n{context.spec_json_small}\n\n"
            f"# DESIGN COPY DECK (authoritative wording)\n{context.text_inventory_json}\n\n"
            f"# DESIGN TOKENS\n{context.tokens_css}\n\n"
            f"# ASSETS\n{json.dumps(assets)}\n\n"
            f"# GENERATED FILES\n{file_dump}{mismatch}\n\nReturn the validated review verdict."
            f"\n\n# OBJECTIVE PIXEL DIAGNOSTICS\n{json.dumps(visual_diagnostics or {}, indent=1)}"
            f"\n\n# MEASURED GEOMETRY vs FIGMA\n{json.dumps(geometry_diagnostics or {}, indent=1)}"
            f"\n\n# RESPONSIVE AUDIT\n{json.dumps(responsive_diagnostics or [], indent=1)}"
        )
        if contract_report:
            text += (
                "\n\n# AUTOMATED CONTRACT CHECKS (already verified mechanically; "
                "do not re-report as your own findings, but do not score as passing while any remain)\n"
                f"{contract_report}"
            )
        content.append({"type": "text", "text": text})
        messages = [SystemMessage(content=REVIEWER_SYSTEM_PROMPT), HumanMessage(content=content)]
        try:
            result = await self._structured_model.ainvoke(messages)
            parsed = result.get("parsed") if isinstance(result, dict) else result
            if isinstance(parsed, ReviewVerdict):
                verdict = parsed
            elif parsed:
                verdict = ReviewVerdict.model_validate(parsed)
            else:
                raw = result.get("raw") if isinstance(result, dict) else None
                if raw is None:
                    raise ValueError("Structured reviewer returned neither parsed nor raw output")
                verdict = ReviewVerdict.model_validate(parse_json_loose(message_text(raw)))
        except Exception as exc:
            log.warning("Structured review failed (%s); using JSON fallback", exc)
            raw = await self._model.ainvoke(messages)
            if _stop_reason(raw) == "refusal":
                raise ModelRefusalError(
                    f"The reviewer declined this request ({_refusal_detail(raw)})."
                ) from exc
            if _stop_reason(raw) in {"max_tokens", "length"}:
                # Thinking tokens share the reviewer's ceiling, and the verdict has
                # no resume path, so name the cause instead of a JSON parse error.
                raise RuntimeError(
                    "The reviewer hit its output token limit before returning a verdict. "
                    "Raise LLM_REVIEWER_MAX_TOKENS or lower LLM_REASONING_EFFORT."
                ) from exc
            verdict = ReviewVerdict.model_validate(parse_json_loose(message_text(raw)))
        log.info("Review score %.1f/100 (%s issues)", verdict.score, len(verdict.issues))
        return verdict
