from __future__ import annotations

from typing import Any

# Rendered text reflows by a pixel or two between platforms; anything at or under
# this is noise the model cannot act on.
DEFAULT_TOLERANCE_PX = 2.0

DOM_GEOMETRY_SCRIPT = """
() => {
  const nodes = [];
  for (const element of document.querySelectorAll('[data-figma-id]')) {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    if (style.display === 'none' || style.visibility === 'hidden') continue;
    const classes = Array.from(element.classList || []).slice(0, 6).join('.');
    nodes.push({
      figmaId: element.getAttribute('data-figma-id'),
      selector: element.tagName.toLowerCase() + (classes ? '.' + classes : ''),
      x: Math.round((rect.left + window.scrollX) * 100) / 100,
      y: Math.round((rect.top + window.scrollY) * 100) / 100,
      w: Math.round(rect.width * 100) / 100,
      h: Math.round(rect.height * 100) / 100,
    });
  }
  return {
    documentHeight: Math.max(
      document.documentElement.scrollHeight,
      document.body ? document.body.scrollHeight : 0
    ),
    documentWidth: Math.max(
      document.documentElement.scrollWidth,
      document.body ? document.body.scrollWidth : 0
    ),
    nodes,
  };
}
"""


async def probe_dom_geometry(page: Any) -> dict[str, Any]:
    """Read every ``data-figma-id`` element's laid-out box from a live page."""
    return await page.evaluate(DOM_GEOMETRY_SCRIPT)


def _round(value: float) -> float:
    return round(float(value), 2)


def compare_geometry(
    design_index: dict[str, dict[str, Any]],
    dom: dict[str, Any] | None,
    *,
    design_width: float,
    design_height: float,
    tolerance_px: float = DEFAULT_TOLERANCE_PX,
    max_nodes: int = 24,
) -> dict[str, Any]:
    """Diff the rendered DOM against Figma boxes in CSS pixels.

    A whole-page image diff of a long page reports "everything is wrong" as soon
    as one section is the wrong height, because every later section shifts. This
    diff separates the two: ``heightErrorPx`` is a node's own defect, ``offsetErrorPx``
    is mostly inherited from earlier siblings, and ``driftIntroducedPx`` attributes
    each new pixel of vertical error to the gap that actually produced it.
    """
    document_height = float((dom or {}).get("documentHeight") or 0)
    document_width = float((dom or {}).get("documentWidth") or 0)
    summary: dict[str, Any] = {
        "designSize": [_round(design_width), _round(design_height)],
        "renderedSize": [_round(document_width), _round(document_height)],
        "documentHeightErrorPx": _round(document_height - design_height) if document_height else None,
        "matchedNodes": 0,
        "measurableNodes": len(design_index),
        "hookCoveragePct": 0.0,
        "unmatchedHooks": [],
        "worstNodes": [],
        "driftSequence": [],
    }
    if not dom or not design_index:
        return summary

    rendered_by_id: dict[str, dict[str, Any]] = {}
    unmatched_hooks: list[str] = []
    for node in dom.get("nodes") or []:
        figma_id = str(node.get("figmaId") or "").strip()
        if not figma_id:
            continue
        if figma_id not in design_index:
            # The model invented a hook value (usually a layer name) instead of
            # echoing the node id, so this element cannot be measured at all.
            if figma_id not in unmatched_hooks:
                unmatched_hooks.append(figma_id)
            continue
        # Keep the outermost element when several share one id.
        existing = rendered_by_id.get(figma_id)
        if existing is None or float(node.get("h") or 0) > float(existing.get("h") or 0):
            rendered_by_id[figma_id] = node

    comparisons: list[dict[str, Any]] = []
    for figma_id, rendered in rendered_by_id.items():
        expected = design_index[figma_id]
        offset_x = float(rendered.get("x") or 0) - expected["x"]
        offset_y = float(rendered.get("y") or 0) - expected["y"]
        width_error = float(rendered.get("w") or 0) - expected["w"]
        height_error = float(rendered.get("h") or 0) - expected["h"]
        comparisons.append(
            {
                "figmaId": figma_id,
                "name": expected.get("name"),
                "selector": rendered.get("selector"),
                "figmaBox": [expected["x"], expected["y"], expected["w"], expected["h"]],
                "renderedBox": [
                    _round(rendered.get("x") or 0),
                    _round(rendered.get("y") or 0),
                    _round(rendered.get("w") or 0),
                    _round(rendered.get("h") or 0),
                ],
                "offsetErrorPx": [_round(offset_x), _round(offset_y)],
                "widthErrorPx": _round(width_error),
                "heightErrorPx": _round(height_error),
            }
        )

    ordered = sorted(comparisons, key=lambda item: item["figmaBox"][1])
    previous_offset = 0.0
    drift_sequence: list[dict[str, Any]] = []
    for item in ordered:
        offset_y = float(item["offsetErrorPx"][1])
        item["driftIntroducedPx"] = _round(offset_y - previous_offset)
        previous_offset = offset_y
        if abs(item["driftIntroducedPx"]) > tolerance_px:
            drift_sequence.append(
                {
                    "figmaId": item["figmaId"],
                    "name": item["name"],
                    "designY": item["figmaBox"][1],
                    "driftIntroducedPx": item["driftIntroducedPx"],
                    "heightErrorPx": item["heightErrorPx"],
                }
            )

    def severity(item: dict[str, Any]) -> float:
        return max(
            abs(float(item["heightErrorPx"])),
            abs(float(item["widthErrorPx"])),
            abs(float(item["driftIntroducedPx"])),
            abs(float(item["offsetErrorPx"][0])),
        )

    actionable = [item for item in comparisons if severity(item) > tolerance_px]
    actionable.sort(key=severity, reverse=True)

    summary.update(
        {
            "matchedNodes": len(comparisons),
            "hookCoveragePct": _round(len(comparisons) / len(design_index) * 100),
            "unmatchedHooks": unmatched_hooks[:20],
            "tolerancePx": tolerance_px,
            "nodesOutOfTolerance": len(actionable),
            "worstNodes": actionable[:max_nodes],
            "driftSequence": drift_sequence[:max_nodes],
        }
    )
    return summary


def detect_layout_pinning(
    audits: list[dict[str, Any]],
    *,
    design_width: float,
    min_drift_fraction: float = 0.5,
    max_elements: int = 12,
) -> dict[str, Any]:
    """Find content that stops centring once the viewport passes the design width.

    Matching Figma coordinates is easiest to fake: pin every section to a fixed
    left offset and the numbers come out exact at the design width. The page then
    hugs the left edge on any wider screen while full-bleed bands keep stretching.

    A centred element keeps a constant distance from the viewport centre as the
    viewport grows. A pinned element's distance grows by exactly half the width
    increase, so the ratio between the two is a scale-free score: 0 is centred,
    1 is fully pinned.
    """
    baseline = next(
        (item for item in audits if abs(float(item.get("viewportWidth", 0)) - design_width) < 1),
        None,
    )
    result: dict[str, Any] = {
        "designWidth": design_width,
        "checkedWidths": [],
        "pinnedElements": [],
        "worstDriftFraction": 0.0,
    }
    if not baseline or not baseline.get("hookCentres"):
        return result

    base_centres: dict[str, float] = {
        key: float(value) for key, value in baseline["hookCentres"].items()
    }
    worst_by_id: dict[str, dict[str, Any]] = {}
    for audit in audits:
        width = float(audit.get("viewportWidth", 0))
        delta = width - design_width
        if delta <= 1 or not audit.get("hookCentres"):
            continue
        result["checkedWidths"].append(round(width))
        for figma_id, raw_centre in audit["hookCentres"].items():
            if figma_id not in base_centres:
                continue
            drift = abs(float(raw_centre) - base_centres[figma_id])
            fraction = drift / (delta / 2)
            if fraction < min_drift_fraction:
                continue
            entry = {
                "figmaId": figma_id,
                "viewportWidth": round(width),
                "centreOffsetAtDesignPx": _round(base_centres[figma_id]),
                "centreOffsetPx": _round(float(raw_centre)),
                "driftPx": _round(drift),
                "driftFraction": _round(fraction),
            }
            existing = worst_by_id.get(figma_id)
            # Many elements pin at 100% across every wider width; report each at
            # the width where the visible displacement is largest.
            rank = (entry["driftFraction"], entry["driftPx"])
            if existing is None or rank > (existing["driftFraction"], existing["driftPx"]):
                worst_by_id[figma_id] = entry

    pinned = sorted(
        worst_by_id.values(),
        key=lambda item: (item["driftFraction"], item["driftPx"]),
        reverse=True,
    )
    result["pinnedElements"] = pinned[:max_elements]
    result["pinnedCount"] = len(pinned)
    result["worstDriftFraction"] = pinned[0]["driftFraction"] if pinned else 0.0
    return result


def pinning_headline(pinning: dict[str, Any] | None) -> str | None:
    if not pinning or not pinning.get("pinnedElements"):
        return None
    worst = pinning["pinnedElements"][0]
    return (
        f"{pinning['pinnedCount']} element(s) stop centring above the "
        f"{pinning['designWidth']:g}px design width — at {worst['viewportWidth']}px the worst drifts "
        f"{worst['driftPx']:g}px off centre ({worst['driftFraction']:.0%} of full pinning). "
        "Fixed left offsets reproduce the design width and leave every wider screen "
        "hugging the left edge; centre the content band instead."
    )


def geometry_headline(summary: dict[str, Any] | None) -> str | None:
    """One human-readable line describing the dominant layout error."""
    if not summary:
        return None
    height_error = summary.get("documentHeightErrorPx")
    if height_error is None:
        return None
    parts = [
        f"Page height is {height_error:+.0f}px versus the Figma frame "
        f"({summary['renderedSize'][1]:g}px rendered vs {summary['designSize'][1]:g}px design)."
    ]
    drift = summary.get("driftSequence") or []
    if drift:
        worst = max(drift, key=lambda item: abs(float(item["driftIntroducedPx"])))
        parts.append(
            f"Largest single contributor: {worst['name']!r} ({worst['figmaId']}) introduces "
            f"{float(worst['driftIntroducedPx']):+.0f}px at design y={worst['designY']:g}."
        )
    coverage = summary.get("hookCoveragePct")
    if isinstance(coverage, (int, float)) and coverage < 5:
        parts.append(
            "Geometry coverage is near zero — data-figma-id values must be Figma node ids "
            "(for example 68226:5173), not layer names."
        )
    return " ".join(parts)
