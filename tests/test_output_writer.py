from pathlib import Path

from figma_to_sitecore.output.writer import write_generated_files, write_report


def test_writer_keeps_model_files_inside_output(tmp_path: Path) -> None:
    written = write_generated_files(
        tmp_path,
        {
            "index.html": "ok",
            "css/styles.css": "ok",
            "../escape.txt": "bad",
            "C:/absolute.txt": "bad",
            "reference/figma-design.png": "bad",
        },
    )
    assert {path.relative_to(tmp_path).as_posix() for path in written} == {"index.html", "css/styles.css"}
    assert not (tmp_path.parent / "escape.txt").exists()


def test_report_makes_strict_accuracy_failure_explicit(tmp_path: Path) -> None:
    write_report(
        tmp_path,
        {
            "design": {"name": "Page", "fileKey": "file", "nodeId": "1:2", "source": "REST"},
            "generatedAt": "2026-01-01T00:00:00Z",
            "finalScore": 99,
            "threshold": 95,
            "pixelMismatchPct": 0.125,
            "iterations": [],
            "status": "best-effort",
            "accuracy": {
                "mode": "strict",
                "targetMismatchPct": 0,
                "diffThreshold": 0,
                "converged": False,
                "exact": False,
                "bestIteration": 2,
                "stopReason": "max_iterations",
                "viewports": [
                    {
                        "name": "375px",
                        "dimensionsEqual": False,
                        "referenceSize": [375, 800],
                        "renderedSize": [375, 820],
                        "mismatchedPixels": 100,
                        "mismatchPct": 0.125,
                        "stable": False,
                        "resourceErrors": ["GET https://example.invalid/font.woff2: HTTP 404"],
                    }
                ],
                "responsiveAudit": [
                    {
                        "viewportWidth": 375,
                        "horizontalOverflowPx": 12,
                        "overflowElements": [{"selector": "main.fixed"}],
                        "brokenImages": ["missing.png"],
                        "fontsReady": False,
                    }
                ],
            },
            "componentMap": None,
            "assets": [],
            "warnings": ["target not met"],
            "remainingIssues": [],
        },
    )

    markdown = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    assert "**Status:** BEST-EFFORT" in markdown
    assert "**Converged:** no" in markdown
    assert "**Pixel target:** 0.000000%" in markdown
    assert "## Accuracy blockers" in markdown
    assert "canvas size differs" in markdown
    assert "resource error" in markdown
    assert "document overflows horizontally by 12px" in markdown
    assert "`main.fixed`" in markdown
    assert "`missing.png`" in markdown
    assert "web fonts did not reach the loaded state" in markdown


def test_report_surfaces_geometry_errors_and_contract_violations(tmp_path: Path) -> None:
    write_report(
        tmp_path,
        {
            "design": {"name": "Page", "fileKey": "file", "nodeId": "1:2", "source": "REST"},
            "generatedAt": "2026-01-01T00:00:00Z",
            "finalScore": 70,
            "threshold": 95,
            "pixelMismatchPct": 38.6,
            "iterations": [],
            "status": "best-effort",
            "accuracy": {
                "mode": "standard",
                "targetMismatchPct": 0,
                "diffThreshold": 31,
                "converged": False,
                "exact": False,
                "bestIteration": 1,
                "stopReason": "max_iterations",
                "viewports": [],
                "responsiveAudit": [],
                "geometry": {
                    "designSize": [1366, 4846],
                    "renderedSize": [1366, 5498],
                    "documentHeightErrorPx": 652,
                    "matchedNodes": 18,
                    "measurableNodes": 24,
                    "hookCoveragePct": 75.0,
                    "unmatchedHooks": ["Promo/hero banner"],
                    "worstNodes": [
                        {
                            "figmaId": "1:30",
                            "name": "Video",
                            "heightErrorPx": 585.0,
                            "widthErrorPx": 0.0,
                            "offsetErrorPx": [0.0, 12.0],
                            "driftIntroducedPx": 0.0,
                        }
                    ],
                },
            },
            "contract": {
                "passed": False,
                "violations": [
                    {
                        "severity": "critical",
                        "area": "css/inline",
                        "description": "index.html contains 3 inline style attribute(s).",
                        "fix": "Move them into css/styles.css.",
                    }
                ],
            },
            "componentMap": None,
            "assets": [],
            "warnings": [],
            "remainingIssues": [],
        },
    )

    markdown = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    assert "## Measured geometry vs Figma" in markdown
    assert "5498px rendered vs 4846px design (+652px)" in markdown
    assert "18 of 24 (75.0% hook coverage)" in markdown
    assert "`Promo/hero banner`" in markdown
    assert "| `1:30` | Video | +585 |" in markdown
    assert "## Output contract" in markdown
    assert "**Status:** FAILED (1 violation(s))" in markdown
    assert "css/inline" in markdown


def test_report_omits_geometry_and_contract_sections_when_absent(tmp_path: Path) -> None:
    write_report(
        tmp_path,
        {
            "design": {"name": "Page", "fileKey": "file", "nodeId": "1:2", "source": "REST"},
            "generatedAt": "2026-01-01T00:00:00Z",
            "finalScore": 99,
            "threshold": 95,
            "pixelMismatchPct": None,
            "iterations": [],
            "status": "accepted",
            "accuracy": {"mode": "standard", "converged": True, "viewports": []},
            "componentMap": None,
            "assets": [],
            "warnings": [],
            "remainingIssues": [],
        },
    )

    markdown = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    assert "## Measured geometry vs Figma" not in markdown
    assert "## Output contract" not in markdown
