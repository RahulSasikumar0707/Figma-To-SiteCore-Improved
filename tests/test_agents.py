from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage

from figma_to_sitecore.domain.models import GenerationContext, ImagePayload
from figma_to_sitecore.generation.agents import (
    GeneratorAgent,
    ModelRefusalError,
    complete,
    create_anthropic_model,
    resolve_effort,
)


def test_anthropic_model_streams_long_generations() -> None:
    model = create_anthropic_model(
        api_key="test-key",
        model="claude-sonnet-4-6",
        max_tokens=64_000,
    )

    assert model.streaming is True
    assert model.default_request_timeout == 1800
    assert model.max_retries == 3
    assert model.max_tokens == 64_000


def test_adaptive_thinking_and_effort_are_configured_for_fable() -> None:
    model = create_anthropic_model(
        api_key="test-key",
        model="claude-fable-5",
        max_tokens=64_000,
        reasoning_effort="xhigh",
    )

    assert model.thinking == {"type": "adaptive"}
    assert model.output_config == {"effort": "xhigh"}


def test_legacy_models_receive_no_thinking_or_effort_parameters() -> None:
    """budget_tokens-era models reject both fields with HTTP 400."""
    model = create_anthropic_model(
        api_key="test-key",
        model="claude-haiku-4-5",
        max_tokens=8_000,
        reasoning_effort="xhigh",
    )

    assert model.thinking is None
    assert model.output_config is None


def test_effort_is_clamped_to_what_the_model_accepts() -> None:
    assert resolve_effort("claude-fable-5", "xhigh") == "xhigh"
    assert resolve_effort("claude-opus-5", "max") == "max"
    # xhigh only exists from Opus 4.7 onward.
    assert resolve_effort("claude-sonnet-4-6", "xhigh") == "high"
    assert resolve_effort("claude-sonnet-4-6", "medium") == "medium"
    assert resolve_effort("claude-haiku-4-5", "high") is None
    assert resolve_effort("claude-fable-5", None) is None
    assert resolve_effort("claude-fable-5", "enormous") is None


class _ScriptedModel(GenericFakeChatModel):
    """Replays canned turns and records the conversation it was handed."""

    def __init__(self, turns: list[AIMessage]) -> None:
        super().__init__(messages=iter(turns))
        object.__setattr__(self, "seen", [])

    async def ainvoke(self, input, config=None, **kwargs):  # type: ignore[override]
        self.seen.append(list(input))
        return next(self.messages)


def _turn(text: str, stop_reason: str) -> AIMessage:
    return AIMessage(content=text, response_metadata={"stop_reason": stop_reason})


@pytest.mark.asyncio
async def test_truncated_output_resumes_without_assistant_prefill() -> None:
    """Ending a request on an assistant turn is a 400 on every Claude 4.6+ model."""
    model = _ScriptedModel([_turn("part one", "max_tokens"), _turn(" and two", "end_turn")])

    result = await complete(model, system="sys", messages=[HumanMessage(content="go")])

    assert result.text == "part one and two"
    assert result.stop_reason == "end_turn"
    resumed = model.seen[1]
    assert resumed[-1].type == "human", "the conversation must end with a user message"
    assert resumed[-2].type == "ai"


@pytest.mark.asyncio
async def test_continuations_are_bounded() -> None:
    model = _ScriptedModel([_turn("chunk", "max_tokens") for _ in range(4)])

    result = await complete(
        model,
        system="sys",
        messages=[HumanMessage(content="go")],
        max_continuations=2,
    )

    assert len(model.seen) == 3
    assert result.stop_reason == "max_tokens"


_ALL_FILES_RESPONSE = """===FILE: index.html===
<!DOCTYPE html><html lang="en"><body>page</body></html>
===FILE: css/styles.css===
body{margin:0}
===FILE: js/script.js===
(function(){})();
===FILE: component-map.json===
{"mappings":[]}
===END==="""


@pytest.mark.asyncio
async def test_generate_sends_figma_design_screenshots_as_ground_truth(tmp_path: Path) -> None:
    model = _ScriptedModel([_turn(_ALL_FILES_RESPONSE, "end_turn")])
    agent = GeneratorAgent(model, raw_output_dir=tmp_path)
    context = GenerationContext(
        design_name="Test",
        root_size={"w": 1440, "h": 900},
        spec_json="{}",
        spec_json_small="{}",
        tokens_css=":root{}",
        asset_manifest=[],
        all_components=[],
        matches=[],
        shortlist=[],
        mcp_design_context=None,
        bootstrap_css_url="",
        bootstrap_js_url="",
        eds_native_available=False,
    )

    files = await agent.generate(
        context,
        design_references=[("TARGET — Figma design at 1440px:", ImagePayload(b"design-png"))],
    )

    assert set(files) == {"index.html", "css/styles.css", "js/script.js", "component-map.json"}
    user_message = model.seen[0][-1]
    blocks = user_message.content
    assert isinstance(blocks, list)
    labels = [block["text"] for block in blocks if isinstance(block, dict) and block.get("type") == "text"]
    assert any("VISUAL GROUND TRUTH" in label for label in labels)
    assert any("TARGET — Figma design at 1440px:" in label for label in labels)
    images = [block for block in blocks if isinstance(block, dict) and block.get("type") == "image"]
    assert len(images) == 1 and images[0]["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_missing_files_retry_replays_every_delivered_file(tmp_path: Path) -> None:
    """Later files must be authored with the already-delivered markup in view."""
    first = (
        "===FILE: index.html===\n<!DOCTYPE html><html><body>page</body></html>\n"
        "===FILE: css/styles.css===\nbody{margin:0}\n===END==="
    )
    second = "===FILE: js/script.js===\n(function(){})();\n===END==="
    third = '===FILE: component-map.json===\n{"mappings":[]}\n===END==='
    model = _ScriptedModel([_turn(first, "end_turn"), _turn(second, "end_turn"), _turn(third, "end_turn")])
    agent = GeneratorAgent(model, raw_output_dir=tmp_path)
    context = GenerationContext(
        design_name="Test",
        root_size={"w": 100, "h": 100},
        spec_json="{}",
        spec_json_small="{}",
        tokens_css=":root{}",
        asset_manifest=[],
        all_components=[],
        matches=[],
        shortlist=[],
        mcp_design_context=None,
        bootstrap_css_url="",
        bootstrap_js_url="",
        eds_native_available=False,
    )

    files = await agent.generate(context)

    assert set(files) == {"index.html", "css/styles.css", "js/script.js", "component-map.json"}
    # The second retry's assistant turn must contain the whole transcript so far,
    # not only the previous retry's single file.
    final_history = model.seen[2]
    ai_turn = next(message for message in final_history if message.type == "ai")
    assert "===FILE: index.html===" in ai_turn.content
    assert "===FILE: js/script.js===" in ai_turn.content


@pytest.mark.asyncio
async def test_continuation_preserves_the_newline_before_a_file_header() -> None:
    """Trimming the seam can glue a ===FILE:=== header mid-line and lose the file."""
    from figma_to_sitecore.generation.parsers import parse_generated_files

    model = _ScriptedModel(
        [
            _turn("===FILE: index.html===\n<html></html>\n", "max_tokens"),
            _turn("===FILE: css/styles.css===\nbody{margin:0}\n===END===", "end_turn"),
        ]
    )

    result = await complete(model, system="sys", messages=[HumanMessage(content="go")])

    files = parse_generated_files(result.text)
    assert set(files) == {"index.html", "css/styles.css"}


@pytest.mark.asyncio
async def test_refusal_is_reported_instead_of_returning_empty_files() -> None:
    model = _ScriptedModel(
        [
            AIMessage(
                content="",
                response_metadata={
                    "stop_reason": "refusal",
                    "stop_details": {"category": "cyber", "explanation": "declined"},
                },
            )
        ]
    )

    with pytest.raises(ModelRefusalError, match="cyber"):
        await complete(model, system="sys", messages=[HumanMessage(content="go")])
