from __future__ import annotations

import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from figma_to_sitecore.config import Settings
from figma_to_sitecore.utils.files import write_file
from figma_to_sitecore.utils.logging import log

WINDOWS_INVALID = re.compile(r'[<>:"|?*]')
WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com\d|lpt\d)$", re.I)
GENERATED_FILE_ALLOWLIST = {
    "index.html",
    "css/styles.css",
    "js/script.js",
    "component-map.json",
}


def find_eds_native_css(settings: Settings) -> Path | None:
    candidates = [
        settings.native_css_path,
        settings.project_root / "assets" / "eds" / "styles" / "eds-native.css",
        settings.project_root / "eds-native.css",
        settings.project_root.parent / "assets" / "eds" / "styles" / "eds-native.css",
    ]
    return next((path.resolve() for path in candidates if path and path.is_file()), None)


def copy_eds_native_css(source: Path, output_dir: Path) -> Path:
    destination = output_dir / "css" / "eds-native.css"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    return destination


def _safe_destination(output_dir: Path, relative: str) -> Path | None:
    if not isinstance(relative, str) or not relative.strip():
        return None
    normalized = relative.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or re.match(r"^[a-z]:", normalized, re.I):
        return None
    if any(
        part in {"", ".", ".."}
        or WINDOWS_INVALID.search(part)
        or any(ord(character) < 32 for character in part)
        or WINDOWS_RESERVED.match(part.split(".")[0])
        for part in path.parts
    ):
        return None
    root = output_dir.resolve()
    destination = (root / Path(*path.parts)).resolve()
    try:
        destination.relative_to(root)
    except ValueError:
        return None
    return destination


def write_generated_files(output_dir: Path, files: dict[str, str]) -> list[Path]:
    written: list[Path] = []
    for relative, content in files.items():
        normalized = relative.replace("\\", "/") if isinstance(relative, str) else relative
        if normalized not in GENERATED_FILE_ALLOWLIST:
            log.warning("Skipping unexpected model-generated file: %r", relative)
            continue
        destination = _safe_destination(output_dir, relative)
        if destination is None:
            log.warning("Skipping model-generated unsafe path: %r", relative)
            continue
        write_file(destination, content)
        written.append(destination)
    log.info("Wrote %s generated files to %s", len(written), output_dir)
    return written


def sync_generated_files(
    output_dir: Path,
    files: dict[str, str],
    previous_files: dict[str, str] | None = None,
) -> list[Path]:
    """Write a candidate and remove only stale paths owned by the prior candidate."""
    stale = set(previous_files or {}) - set(files)
    for relative in stale:
        normalized = relative.replace("\\", "/") if isinstance(relative, str) else relative
        if normalized not in GENERATED_FILE_ALLOWLIST:
            continue
        destination = _safe_destination(output_dir, relative)
        if destination and destination.is_file():
            destination.unlink()
            log.info("Removed stale generated file %s", destination)
    return write_generated_files(output_dir, files)


def write_report(output_dir: Path, report: dict[str, Any]) -> None:
    write_file(output_dir / "report.json", json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    design = report["design"]
    pixel = report.get("pixelMismatchPct")
    final_score = report.get("finalScore")
    accuracy = report.get("accuracy") or {}
    score_text = final_score if final_score is not None else "n/a"
    score_suffix = f" — pixel mismatch {pixel:.6f}%" if pixel is not None else ""
    status = report.get("status", "completed").upper()
    lines = [
        "# Figma → EDS Conversion Report",
        "",
        f"- **Status:** {status}",
        f"- **Design:** {design['name']} ({design['fileKey']} / node {design['nodeId']})",
        f"- **Source:** {design['source']}",
        f"- **Generated:** {report['generatedAt']}",
        f"- **Final score:** {score_text}/100 (threshold {report['threshold']}){score_suffix}",
        f"- **Review iterations:** {len(report['iterations'])}",
    ]
    if accuracy:
        target = accuracy.get("targetMismatchPct")
        target_text = f"{target:.6f}%" if isinstance(target, (int, float)) else "n/a"
        lines.extend(
            [
                f"- **Accuracy mode:** {accuracy.get('mode', 'standard')}",
                f"- **Pixel target:** {target_text} (channel threshold {accuracy.get('diffThreshold', 'n/a')})",
                f"- **Converged:** {'yes' if accuracy.get('converged') else 'no'}",
                f"- **Exact decoded pixels:** {'yes' if accuracy.get('exact') else 'no'}",
                f"- **Selected iteration:** {accuracy.get('bestIteration') or 'n/a'}",
                f"- **Stop reason:** {accuracy.get('stopReason') or 'n/a'}",
            ]
        )
        viewports = accuracy.get("viewports") or []
        if viewports:
            lines.extend(["", "## Viewport accuracy", "", "| Viewport | Size match | Mismatched pixels | Mismatch | Stable |", "|---|---:|---:|---:|---:|"])
            for viewport in viewports:
                viewport_mismatch = viewport.get("mismatchPct")
                viewport_mismatch_text = (
                    f"{float(viewport_mismatch):.6f}%"
                    if isinstance(viewport_mismatch, (int, float))
                    else "n/a"
                )
                lines.append(
                    f"| {viewport.get('name')} | {'yes' if viewport.get('dimensionsEqual') else 'no'} | "
                    f"{viewport.get('mismatchedPixels', 'n/a')} | "
                    f"{viewport_mismatch_text} | "
                    f"{'yes' if viewport.get('stable') else 'no'} |"
                )
        if not accuracy.get("converged"):
            blockers: list[str] = []
            seen_blockers: set[str] = set()

            def add_blocker(message: str) -> None:
                if message not in seen_blockers:
                    seen_blockers.add(message)
                    blockers.append(message)

            for viewport in viewports:
                name = str(viewport.get("name") or "unknown viewport")
                if not viewport.get("dimensionsEqual"):
                    add_blocker(
                        f"**{name}:** canvas size differs: "
                        f"reference `{viewport.get('referenceSize')}`, "
                        f"rendered `{viewport.get('renderedSize')}`."
                    )
                if not viewport.get("stable"):
                    add_blocker(f"**{name}:** repeated browser captures were not pixel-stable.")
                for error in viewport.get("resourceErrors") or []:
                    add_blocker(f"**{name}:** resource error — `{error}`")

            for audit in accuracy.get("responsiveAudit") or []:
                width = audit.get("viewportWidth", "unknown")
                overflow = float(audit.get("horizontalOverflowPx") or 0)
                if overflow > 0:
                    add_blocker(f"**{width}px audit:** document overflows horizontally by {overflow:g}px.")
                overflow_elements = audit.get("overflowElements") or []
                if overflow_elements:
                    selectors = ", ".join(
                        f"`{item.get('selector', '<unknown>')}`"
                        for item in overflow_elements[:5]
                    )
                    suffix = " …" if len(overflow_elements) > 5 else ""
                    add_blocker(
                        f"**{width}px audit:** {len(overflow_elements)} visible element(s) "
                        f"cross the viewport boundary: {selectors}{suffix}."
                    )
                broken_images = audit.get("brokenImages") or []
                if broken_images:
                    add_blocker(
                        f"**{width}px audit:** {len(broken_images)} image(s) failed to load: "
                        + ", ".join(f"`{item}`" for item in broken_images[:5])
                    )
                if not audit.get("fontsReady", False):
                    add_blocker(f"**{width}px audit:** web fonts did not reach the loaded state.")

            if blockers:
                lines.extend(["", "## Accuracy blockers", ""])
                lines.extend(f"- {blocker}" for blocker in blockers)
        geometry = accuracy.get("geometry") or {}
        worst_nodes = geometry.get("worstNodes") or []
        if geometry.get("documentHeightErrorPx") is not None or worst_nodes:
            lines.extend(["", "## Measured geometry vs Figma", ""])
            height_error = geometry.get("documentHeightErrorPx")
            if height_error is not None:
                design_size = geometry.get("designSize") or ["?", "?"]
                rendered_size = geometry.get("renderedSize") or ["?", "?"]
                lines.append(
                    f"- **Document height:** {rendered_size[1]}px rendered vs {design_size[1]}px "
                    f"design ({float(height_error):+g}px)."
                )
            coverage = geometry.get("hookCoveragePct")
            if coverage is not None:
                lines.append(
                    f"- **Measured nodes:** {geometry.get('matchedNodes', 0)} of "
                    f"{geometry.get('measurableNodes', 0)} ({coverage}% hook coverage)."
                )
            unmatched = geometry.get("unmatchedHooks") or []
            if unmatched:
                lines.append(
                    "- **Unusable data-figma-id values** (not Figma node ids): "
                    + ", ".join(f"`{value}`" for value in unmatched[:5])
                    + (" …" if len(unmatched) > 5 else "")
                )
            pinning = geometry.get("layoutPinning") or {}
            pinned = pinning.get("pinnedElements") or []
            if pinned:
                lines.append(
                    f"- **Not responsive above the design width:** {pinning.get('pinnedCount', 0)} "
                    f"element(s) stop centring past {pinning.get('designWidth', '?')}px; the worst "
                    f"drifts {pinned[0].get('driftPx')}px off centre at "
                    f"{pinned[0].get('viewportWidth')}px. Centre the content band instead of "
                    f"pinning it with fixed left offsets."
                )
            if worst_nodes:
                lines.extend(
                    [
                        "",
                        "| Node | Name | Δheight | Δwidth | Δx | Δy | Drift introduced |",
                        "|---|---|---:|---:|---:|---:|---:|",
                    ]
                )
                for node in worst_nodes[:12]:
                    offset = node.get("offsetErrorPx") or [0, 0]
                    lines.append(
                        f"| `{node.get('figmaId')}` | {node.get('name')} | "
                        f"{float(node.get('heightErrorPx', 0)):+g} | "
                        f"{float(node.get('widthErrorPx', 0)):+g} | "
                        f"{float(offset[0]):+g} | {float(offset[1]):+g} | "
                        f"{float(node.get('driftIntroducedPx', 0)):+g} |"
                    )

    contract = report.get("contract") or {}
    if contract:
        violations = contract.get("violations") or []
        lines.extend(
            [
                "",
                "## Output contract",
                "",
                f"- **Status:** {'PASSED' if contract.get('passed') else 'FAILED'}"
                + ("" if contract.get("passed") else f" ({len(violations)} violation(s))"),
            ]
        )
        lines.extend(
            f"- ⛔ **[{item.get('severity')}] {item.get('area')}:** {item.get('description')} "
            f"→ {item.get('fix')}"
            for item in violations
        )

    lines.extend(["", "## Score history", ""])
    for index, iteration in enumerate(report["iterations"], start=1):
        mismatch = iteration.get("pixelMismatchPct")
        mismatch_text = f" — mismatch {mismatch:.6f}%" if mismatch is not None else ""
        decision = f" — {iteration['decision']}" if iteration.get("decision") else ""
        lines.append(
            f"{index}. score **{iteration['score']}** — {iteration['issueCount']} issues "
            f"({iteration['critical']} critical, {iteration['major']} major, {iteration['minor']} minor)"
            f"{mismatch_text}{decision}"
        )

    mappings = (report.get("componentMap") or {}).get("mappings") or []
    if mappings:
        lines.extend(["", "## EDS component mapping", ""])
        for mapping in mappings:
            modifiers = f" ({', '.join(mapping.get('modifiers') or [])})" if mapping.get("modifiers") else ""
            notes = f" — {mapping['notes']}" if mapping.get("notes") else ""
            lines.append(
                f"- **{mapping.get('designSection')}** → `{mapping.get('edsComponent')}`{modifiers} "
                f"— confidence {mapping.get('confidence')}%{notes}"
            )

    lines.extend(["", f"## Assets ({len(report['assets'])})", ""])
    for asset in report["assets"]:
        lines.append(
            f"- `{asset['file']}` — {asset['kind']}, {asset['w']}×{asset['h']} ({asset['name']!r})"
        )
    if report.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- ⚠ {warning}" for warning in report["warnings"])
    if report.get("remainingIssues"):
        lines.extend(["", "## Remaining review issues", ""])
        lines.extend(
            f"- **[{issue['severity']}] {issue['area']}:** {issue['description']}"
            for issue in report["remainingIssues"]
        )
    write_file(output_dir / "REPORT.md", "\n".join(lines) + "\n")
