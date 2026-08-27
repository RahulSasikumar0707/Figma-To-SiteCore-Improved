import re
from pathlib import Path

import pytest

from figma_to_sitecore.config import Settings
from figma_to_sitecore.domain.models import (
    GenerationContext,
    ImagePayload,
    ReviewIssue,
    ReviewVerdict,
    ViewportReference,
)
from figma_to_sitecore.review.visual import VisualDiffResult
from figma_to_sitecore.workflow.graph import (
    RENDER_LOST_WARNING,
    VISUAL_FALLBACK_WARNING,
    ConversionGraph,
)

# The graph now enforces the output contract (no embedded CSS, wired stylesheets
# and scripts, real breakpoints) before a candidate can be accepted, so these
# loop-mechanics tests need candidates that satisfy it. A candidate is identified
# by its data-marker value rather than by its whole file body.
_MARKER = re.compile(r'data-marker="([^"]+)"')

_BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css"
_BOOTSTRAP_JS = "https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"


def _page(marker: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link href="{_BOOTSTRAP_CSS}" rel="stylesheet" />
<link href="css/tokens.css" rel="stylesheet" />
<link href="css/styles.css" rel="stylesheet" />
</head>
<body>
<main data-marker="{marker}">{marker}</main>
<script src="{_BOOTSTRAP_JS}"></script>
<script src="js/script.js"></script>
</body>
</html>
"""


def _files(marker: str) -> dict[str, str]:
    return {
        "index.html": _page(marker),
        "css/styles.css": "main{display:block}\n@media (min-width: 768px){main{display:flex}}\n",
        "js/script.js": "(function(){})();\n",
        "component-map.json": '{"mappings":[]}\n',
    }


def _marker(html: str) -> str:
    found = _MARKER.search(html)
    return found.group(1) if found else html


class FakeGenerator:
    def __init__(self) -> None:
        self.refinements = 0
        self.design_references: list = []

    async def generate(self, context: GenerationContext, design_references=None) -> dict[str, str]:
        self.design_references = list(design_references or [])
        return _files("first")

    async def refine(self, context, files, review, *images):
        self.refinements += 1
        return {**files, "index.html": _page("fixed")}


class FakeReviewer:
    def __init__(self) -> None:
        self.calls = 0

    async def review(self, *args):
        self.calls += 1
        issues = (
            [ReviewIssue(severity="major", area="main", description="wrong", fix="fix it")]
            if self.calls == 1
            else []
        )
        return ReviewVerdict(score=80 if issues else 99, summary="review", issues=issues)


def _context() -> GenerationContext:
    return GenerationContext(
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


@pytest.mark.asyncio
async def test_graph_refines_until_reviewer_has_no_issues(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        visual_diff=False,
        max_review_iterations=3,
    )
    generator = FakeGenerator()
    reviewer = FakeReviewer()
    context = _context()
    graph = ConversionGraph(
        generator=generator,
        reviewer=reviewer,
        settings=settings,
        output_dir=tmp_path,
    )
    result = await graph.run(
        {
            "context": context,
            "files": {},
            "iterations": [],
            "iteration": 0,
            "reference_scale": 1,
        }
    )
    assert generator.refinements == 1
    assert reviewer.calls == 2
    assert len(result["iterations"]) == 2
    assert _marker(result["files"]["index.html"]) == "fixed"


class SequenceGenerator:
    def __init__(self, candidates: list[str]) -> None:
        self.candidates = candidates
        self.index = 0
        self.design_references: list = []

    async def generate(self, context: GenerationContext, design_references=None) -> dict[str, str]:
        self.design_references = list(design_references or [])
        return _files(self.candidates[0])

    async def refine(self, context, files, review, *diagnostics):
        self.index += 1
        return {**files, "index.html": _page(self.candidates[self.index])}


class NoIssueReviewer:
    async def review(self, *args):
        return ReviewVerdict(score=100, summary="clear", issues=[])


class PersistentIssueReviewer:
    async def review(self, *args):
        issue = ReviewIssue(severity="major", area="page", description="mismatch", fix="align")
        return ReviewVerdict(score=80, summary="continue", issues=[issue])


def _install_visual_fakes(monkeypatch, mismatches: dict[str, float]) -> None:
    async def fake_render(output_dir: Path, **kwargs):
        marker = _marker((output_dir / "index.html").read_text(encoding="utf-8"))
        rendered = {
            "png": marker.encode(),
            "jpg": marker.encode(),
            "pixelHash": marker,
            "stable": True,
            "resourceErrors": [],
            "domGeometry": {"documentHeight": 100, "documentWidth": 100, "nodes": []},
            "responsive": [
                {
                    "viewportWidth": 375,
                    "horizontalOverflowPx": 0,
                    "brokenImages": [],
                    "fontsReady": True,
                }
            ],
        }
        return [rendered for _ in kwargs["captures"]]

    def fake_diff(reference_png: bytes, render_png: bytes, **kwargs):
        marker = render_png.decode()
        mismatch = mismatches[marker]
        mismatched_pixels = round(mismatch)
        return VisualDiffResult(
            dimensions_equal=True,
            reference_width=10,
            reference_height=10,
            rendered_width=10,
            rendered_height=10,
            mismatched_pixels=mismatched_pixels,
            total_pixels=100,
            mismatch_pct=mismatch,
            mean_absolute_error=mismatch,
            max_channel_delta=255 if mismatch else 0,
            threshold=0,
            mismatch_bounds=(0, 0, 1, 1) if mismatch else None,
            regions=(),
            heatmap_png=f"diff:{marker}".encode(),
        )

    monkeypatch.setattr("figma_to_sitecore.workflow.graph.render_generated_pages", fake_render)
    monkeypatch.setattr("figma_to_sitecore.workflow.graph.analyze_visual_diff", fake_diff)


def _strict_initial_state(context: GenerationContext) -> dict:
    return {
        "context": context,
        "files": {},
        "iterations": [],
        "iteration": 0,
        "reference_image": ImagePayload(b"reference"),
        "viewport_references": [
            ViewportReference(
                name="100px",
                node_id="1:1",
                width=100,
                height=100,
                scale=1,
                png=b"reference",
                preview=ImagePayload(b"reference"),
            )
        ],
        "workflow_warnings": [],
        "no_improvement_count": 0,
    }


@pytest.mark.asyncio
async def test_strict_mode_continues_when_review_is_clear_but_pixels_are_not(monkeypatch, tmp_path: Path) -> None:
    _install_visual_fakes(monkeypatch, {"first": 10, "exact": 0})
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="strict",
        max_review_iterations=3,
    )
    generator = SequenceGenerator(["first", "exact"])
    graph = ConversionGraph(
        generator=generator,
        reviewer=NoIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert generator.index == 1
    assert len(result["iterations"]) == 2
    assert result["accuracy_achieved"] is True
    assert result["last_pixel_mismatch"] == 0
    assert _marker(result["files"]["index.html"]) == "exact"


@pytest.mark.asyncio
async def test_regressed_candidate_is_rejected_and_best_files_and_artifacts_are_restored(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_visual_fakes(monkeypatch, {"first": 10, "best": 5, "regressed": 8})
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="strict",
        max_review_iterations=3,
    )
    graph = ConversionGraph(
        generator=SequenceGenerator(["first", "best", "regressed"]),
        reviewer=PersistentIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert result["best_iteration"] == 2
    assert result["last_pixel_mismatch"] == 5
    assert _marker(result["files"]["index.html"]) == "best"
    assert _marker((tmp_path / "index.html").read_text(encoding="utf-8")) == "best"
    assert (tmp_path / "reference" / "generated-render.png").read_bytes() == b"best"
    assert result["iterations"][-1]["decision"] == "rejected-regression"


@pytest.mark.asyncio
async def test_passing_candidate_is_selected_even_when_visual_tiebreaker_regresses(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_visual_fakes(monkeypatch, {"first": 5, "passing": 8})
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=3,
    )
    graph = ConversionGraph(
        generator=SequenceGenerator(["first", "passing"]),
        reviewer=FakeReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert result["accuracy_achieved"] is True
    assert _marker(result["files"]["index.html"]) == "passing"
    assert result["review"] is not None and result["review"].issues == []


class EmbeddedCssGenerator(SequenceGenerator):
    """Emits a page whose only defect is an inline style attribute."""

    async def generate(self, context: GenerationContext, design_references=None) -> dict[str, str]:
        files = _files(self.candidates[0])
        files["index.html"] = files["index.html"].replace("<main ", '<main style="color:red" ')
        return files


@pytest.mark.asyncio
async def test_embedded_css_blocks_acceptance_and_is_sent_back_for_repair(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_visual_fakes(monkeypatch, {"first": 0, "clean": 0})
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=3,
    )
    generator = EmbeddedCssGenerator(["first", "clean"])
    graph = ConversionGraph(
        generator=generator,
        reviewer=NoIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    # The reviewer was happy on the first pass; only the contract check caught it.
    assert generator.index == 1
    assert _marker(result["files"]["index.html"]) == "clean"
    assert result["accuracy_achieved"] is True
    assert result["iterations"][0]["contractViolations"] == 1
    assert result["iterations"][-1]["contractViolations"] == 0


@pytest.mark.asyncio
async def test_unfixed_contract_violation_is_reported_not_accepted(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _install_visual_fakes(monkeypatch, {"first": 0})

    class NeverRepairs(EmbeddedCssGenerator):
        async def refine(self, context, files, review, *diagnostics):
            return dict(files)

    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=2,
    )
    graph = ConversionGraph(
        generator=NeverRepairs(["first"]),
        reviewer=NoIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert result["accuracy_achieved"] is False
    assert result["termination_reason"] == "max_iterations"
    assert [issue.area for issue in result["contract_issues"]] == ["css/inline"]
    assert any("output-contract violation" in warning for warning in result["workflow_warnings"])
    # The violation is also handed to the reviewer verdict so it reaches the report.
    assert any(issue.area == "css/inline" for issue in result["review"].issues)


def test_dimension_correct_candidate_outranks_lower_mismatch_with_wrong_canvas(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, project_root=tmp_path, accuracy_mode="strict")
    graph = ConversionGraph(
        generator=FakeGenerator(),
        reviewer=FakeReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )
    verdict = ReviewVerdict(score=90, summary="review", issues=[])
    severity = {"critical": 0, "major": 0, "minor": 0}
    base = {
        "verified": True,
        "stable": True,
        "resourceErrorCount": 0,
        "responsiveViolations": 0,
        "weightedMismatchPct": 2,
        "viewports": [],
    }

    correct = graph._quality({}, {**base, "dimensionsEqual": True, "worstMismatchPct": 2}, severity, verdict)
    wrong = graph._quality({}, {**base, "dimensionsEqual": False, "worstMismatchPct": 1}, severity, verdict)

    assert correct < wrong


class FailingRefineGenerator(FakeGenerator):
    async def refine(self, context, files, review, *images):
        raise RuntimeError("malformed model response")


@pytest.mark.asyncio
async def test_refinement_parse_failure_restores_best_and_finishes_with_warning(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        visual_diff=False,
        max_review_iterations=3,
    )
    graph = ConversionGraph(
        generator=FailingRefineGenerator(),
        reviewer=PersistentIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert result["termination_reason"] == "refinement_model_error"
    assert _marker(result["files"]["index.html"]) == "first"
    assert result["workflow_warnings"]


class ExtraFileGenerator(SequenceGenerator):
    async def refine(self, context, files, review, *diagnostics):
        refined = await super().refine(context, files, review, *diagnostics)
        return {**refined, "component-map.json": '{"mappings":[{"edsComponent":"ghost"}]}\n'}


@pytest.mark.asyncio
async def test_rollback_restores_file_owned_only_by_rejected_candidate(monkeypatch, tmp_path: Path) -> None:
    _install_visual_fakes(monkeypatch, {"first": 5, "regressed": 8})
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="strict",
        max_review_iterations=2,
    )
    graph = ConversionGraph(
        generator=ExtraFileGenerator(["first", "regressed"]),
        reviewer=PersistentIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert _marker(result["files"]["index.html"]) == "first"
    assert result["files"]["component-map.json"] == '{"mappings":[]}\n'
    assert (tmp_path / "component-map.json").read_text(encoding="utf-8") == '{"mappings":[]}\n'


class ClippingGenerator(SequenceGenerator):
    """First candidate clips content; the repair lets the box grow again.

    The clipping is expressed across two rules so the static contract check does
    not see it — only the rendered measurement can.
    """

    async def generate(self, context: GenerationContext, design_references=None) -> dict[str, str]:
        files = _files(self.candidates[0])
        files["css/styles.css"] += ".lv-footer{height:40px}\n.lv-footer{overflow:hidden}\n"
        return files

    async def refine(self, context, files, review, *diagnostics):
        self.index += 1
        return _files(self.candidates[self.index])


@pytest.mark.asyncio
async def test_clipped_content_counts_as_a_responsive_violation(monkeypatch, tmp_path: Path) -> None:
    """A box that cannot grow never trips an overflow check, so it needs its own."""

    def _clipping_render(marker: str) -> list[dict]:
        clipped = [{"selector": "footer.lv-footer", "hiddenPx": 88}] if marker == "first" else []
        return [
            {
                "viewportWidth": 375,
                "horizontalOverflowPx": 0,
                "brokenImages": [],
                "clippedElements": clipped,
                "hookCentres": {},
                "fontsReady": True,
            }
        ]

    async def fake_render(output_dir: Path, **kwargs):
        marker = _marker((output_dir / "index.html").read_text(encoding="utf-8"))
        return [
            {
                "png": marker.encode(),
                "jpg": marker.encode(),
                "pixelHash": marker,
                "stable": True,
                "resourceErrors": [],
                "domGeometry": {"documentHeight": 100, "documentWidth": 100, "nodes": []},
                "responsive": _clipping_render(marker),
            }
            for _ in kwargs["captures"]
        ]

    _install_visual_fakes(monkeypatch, {"first": 0, "clean": 0})
    monkeypatch.setattr("figma_to_sitecore.workflow.graph.render_generated_pages", fake_render)

    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="strict",
        max_review_iterations=3,
    )
    generator = ClippingGenerator(["first", "clean"])
    graph = ConversionGraph(
        generator=generator,
        reviewer=NoIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    # Pixels and the reviewer were both clean on the first pass; only the
    # clipping check kept the loop going.
    assert generator.index == 1
    assert result["iterations"][0]["responsiveViolations"] == 1
    assert result["iterations"][-1]["responsiveViolations"] == 0
    assert result["accuracy_achieved"] is True
    assert _marker(result["files"]["index.html"]) == "clean"


@pytest.mark.asyncio
async def test_generator_receives_figma_design_screenshots(monkeypatch, tmp_path: Path) -> None:
    """The first generation pass is grounded on the Figma design renders."""
    _install_visual_fakes(monkeypatch, {"first": 0})
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=2,
    )
    generator = FakeGenerator()
    graph = ConversionGraph(
        generator=generator,
        reviewer=NoIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    await graph.run(_strict_initial_state(_context()))

    assert generator.design_references == [
        ("TARGET — Figma design at 100px:", ImagePayload(b"reference"))
    ]


@pytest.mark.asyncio
async def test_generator_falls_back_to_primary_reference_image(tmp_path: Path) -> None:
    """Without viewport references the single primary screenshot still grounds generation."""
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        visual_diff=False,
        max_review_iterations=2,
    )
    generator = FakeGenerator()
    graph = ConversionGraph(
        generator=generator,
        reviewer=NoIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    await graph.run(
        {
            "context": _context(),
            "files": {},
            "iterations": [],
            "iteration": 0,
            "reference_image": ImagePayload(b"primary"),
            "reference_scale": 1,
        }
    )

    assert generator.design_references == [("TARGET — Figma design:", ImagePayload(b"primary"))]


@pytest.mark.asyncio
async def test_standard_mode_falls_back_to_reviewer_when_render_never_works(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """An environment that cannot render must not burn every iteration retrying."""

    async def broken_render(output_dir: Path, **kwargs):
        return [None for _ in kwargs["captures"]]

    monkeypatch.setattr("figma_to_sitecore.workflow.graph.render_generated_pages", broken_render)
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=3,
    )
    graph = ConversionGraph(
        generator=FakeGenerator(),
        reviewer=NoIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert result["accuracy_achieved"] is True
    assert len(result["iterations"]) == 1
    assert any("falls back to reviewer judgment" in warning for warning in result["workflow_warnings"])


@pytest.mark.asyncio
async def test_standard_mode_rejects_unverified_candidate_once_visual_has_worked(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A clear reviewer verdict alone cannot accept a candidate that skipped the design comparison."""
    _install_visual_fakes(monkeypatch, {"first": 10, "third": 0})

    async def selective_render(output_dir: Path, **kwargs):
        marker = _marker((output_dir / "index.html").read_text(encoding="utf-8"))
        if marker == "second":
            return [None for _ in kwargs["captures"]]
        rendered = {
            "png": marker.encode(),
            "jpg": marker.encode(),
            "pixelHash": marker,
            "stable": True,
            "resourceErrors": [],
            "domGeometry": {"documentHeight": 100, "documentWidth": 100, "nodes": []},
            "responsive": [
                {
                    "viewportWidth": 375,
                    "horizontalOverflowPx": 0,
                    "brokenImages": [],
                    "fontsReady": True,
                }
            ],
        }
        return [rendered for _ in kwargs["captures"]]

    monkeypatch.setattr("figma_to_sitecore.workflow.graph.render_generated_pages", selective_render)
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=3,
    )
    graph = ConversionGraph(
        generator=SequenceGenerator(["first", "second", "third"]),
        reviewer=FakeReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    # Iteration 2 rendered nothing, so its clean review verdict was not accepted;
    # the loop continued until a compared candidate passed.
    assert len(result["iterations"]) == 3
    assert result["iterations"][1]["decision"] != "accepted"
    assert result["accuracy_achieved"] is True
    assert _marker(result["files"]["index.html"]) == "third"


def _flaky_render(fail_calls: set[int], mismatch_marker_pngs: bool = True):
    """A render fake that fails on the given 1-based call numbers."""
    calls = {"count": 0}

    async def fake_render(output_dir: Path, **kwargs):
        calls["count"] += 1
        if calls["count"] in fail_calls:
            return [None for _ in kwargs["captures"]]
        marker = _marker((output_dir / "index.html").read_text(encoding="utf-8"))
        rendered = {
            "png": marker.encode(),
            "jpg": marker.encode(),
            "pixelHash": marker,
            "stable": True,
            "resourceErrors": [],
            "domGeometry": {"documentHeight": 100, "documentWidth": 100, "nodes": []},
            "responsive": [
                {
                    "viewportWidth": 375,
                    "horizontalOverflowPx": 0,
                    "brokenImages": [],
                    "fontsReady": True,
                }
            ],
        }
        return [rendered for _ in kwargs["captures"]]

    return fake_render, calls


@pytest.mark.asyncio
async def test_transient_render_flake_is_retried_within_the_pass(monkeypatch, tmp_path: Path) -> None:
    """One failed render must not waive the visual gate: the pass retries and stays gated."""
    _install_visual_fakes(monkeypatch, {"first": 0})
    fake_render, calls = _flaky_render(fail_calls={1})
    monkeypatch.setattr("figma_to_sitecore.workflow.graph.render_generated_pages", fake_render)
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=3,
    )
    graph = ConversionGraph(
        generator=FakeGenerator(),
        reviewer=NoIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert calls["count"] == 2, "the failed render must be retried within the same pass"
    assert result["accuracy_achieved"] is True
    assert result["iterations"][0]["visualVerified"] is True
    assert VISUAL_FALLBACK_WARNING not in result["workflow_warnings"]


@pytest.mark.asyncio
async def test_render_lost_midrun_stops_early_with_best_candidate(monkeypatch, tmp_path: Path) -> None:
    """Permanent mid-run render breakage must not silently burn every remaining iteration."""
    _install_visual_fakes(monkeypatch, {"first": 5})
    fake_render, _ = _flaky_render(fail_calls=set(range(2, 50)))
    monkeypatch.setattr("figma_to_sitecore.workflow.graph.render_generated_pages", fake_render)
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=6,
    )
    graph = ConversionGraph(
        generator=SequenceGenerator(["first", "second", "third", "fourth"]),
        reviewer=PersistentIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert result["termination_reason"] == "render_lost"
    # Iteration 1 verified, iteration 2 failed (streak 1), iteration 3 gave up
    # before spending another reviewer/refiner round.
    assert len(result["iterations"]) == 2
    assert any(RENDER_LOST_WARNING in warning for warning in result["workflow_warnings"])
    assert _marker(result["files"]["index.html"]) == "first"


@pytest.mark.asyncio
async def test_fallback_warning_is_removed_after_visual_comparison_recovers(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A stale iteration-1 fallback warning must not misreport a visually gated result."""
    _install_visual_fakes(monkeypatch, {"first": 0, "fixed": 0})
    fake_render, _ = _flaky_render(fail_calls={1, 2})
    monkeypatch.setattr("figma_to_sitecore.workflow.graph.render_generated_pages", fake_render)
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=3,
    )
    graph = ConversionGraph(
        generator=FakeGenerator(),
        reviewer=FakeReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert result["accuracy_achieved"] is True
    assert result["iterations"][-1]["visualVerified"] is True
    assert VISUAL_FALLBACK_WARNING not in result["workflow_warnings"]


@pytest.mark.asyncio
async def test_strict_mode_never_emits_the_reviewer_fallback_warning(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Strict acceptance never falls back to the reviewer, so the warning would be false."""
    fake_render, _ = _flaky_render(fail_calls=set(range(1, 50)))
    monkeypatch.setattr("figma_to_sitecore.workflow.graph.render_generated_pages", fake_render)
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="strict",
        max_review_iterations=2,
    )
    graph = ConversionGraph(
        generator=SequenceGenerator(["first", "second"]),
        reviewer=NoIssueReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert result["accuracy_achieved"] is False
    assert VISUAL_FALLBACK_WARNING not in result["workflow_warnings"]


class ExplodingSecondReviewer:
    def __init__(self) -> None:
        self.calls = 0

    async def review(self, *args):
        self.calls += 1
        if self.calls == 1:
            issue = ReviewIssue(severity="major", area="page", description="off", fix="align")
            return ReviewVerdict(score=70, summary="issues", issues=[issue])
        raise RuntimeError("reviewer transport failed")


@pytest.mark.asyncio
async def test_finalize_reports_only_the_delivered_candidates_evidence(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A rejected candidate's pixel metrics must never be attributed to the delivered best files."""
    _install_visual_fakes(monkeypatch, {"first": 0, "second": 0})
    # Iteration 1 (candidate "first") never renders; iteration 2 renders but its
    # reviewer call explodes, so "first" is delivered while only "second" has metrics.
    fake_render, _ = _flaky_render(fail_calls={1, 2})
    monkeypatch.setattr("figma_to_sitecore.workflow.graph.render_generated_pages", fake_render)
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="standard",
        max_review_iterations=3,
    )
    graph = ConversionGraph(
        generator=SequenceGenerator(["first", "second"]),
        reviewer=ExplodingSecondReviewer(),
        settings=settings,
        output_dir=tmp_path,
    )

    result = await graph.run(_strict_initial_state(_context()))

    assert result["termination_reason"] == "review_model_error"
    assert _marker(result["files"]["index.html"]) == "first"
    assert result["viewport_metrics"] == []
    assert result.get("visual_diagnostics") is None
    assert result.get("render_png") is None
