from figma_to_sitecore.review.geometry import (
    compare_geometry,
    detect_layout_pinning,
    geometry_headline,
    pinning_headline,
)


def _index() -> dict[str, dict[str, object]]:
    return {
        "1:10": {"id": "1:10", "name": "Header", "type": "FRAME", "x": 0.0, "y": 0.0, "w": 1366.0, "h": 160.0},
        "1:20": {"id": "1:20", "name": "Hero", "type": "FRAME", "x": 0.0, "y": 160.0, "w": 1366.0, "h": 460.0},
        "1:30": {"id": "1:30", "name": "Video", "type": "FRAME", "x": 0.0, "y": 620.0, "w": 1366.0, "h": 727.0},
        "1:40": {"id": "1:40", "name": "Footer", "type": "FRAME", "x": 0.0, "y": 1347.0, "w": 1366.0, "h": 300.0},
    }


def _node(figma_id: str, y: float, h: float, x: float = 0.0, w: float = 1366.0) -> dict[str, object]:
    return {"figmaId": figma_id, "selector": f"div#{figma_id}", "x": x, "y": y, "w": w, "h": h}


def test_drift_is_attributed_to_the_section_that_introduces_it() -> None:
    """One over-tall section displaces everything below it; only it should be blamed."""
    dom = {
        "documentHeight": 2232,
        "documentWidth": 1366,
        "nodes": [
            _node("1:10", 0, 160),
            _node("1:20", 160, 460),
            _node("1:30", 620, 1312),  # 585px too tall
            _node("1:40", 1932, 300),  # displaced by exactly that amount
        ],
    }

    summary = compare_geometry(_index(), dom, design_width=1366, design_height=1647)

    assert summary["documentHeightErrorPx"] == 585
    assert summary["matchedNodes"] == 4
    assert summary["hookCoveragePct"] == 100.0

    drift = {item["figmaId"]: item["driftIntroducedPx"] for item in summary["driftSequence"]}
    assert drift == {"1:40": 585.0}, "the displaced footer inherits nothing new after the video"

    by_id = {item["figmaId"]: item for item in summary["worstNodes"]}
    assert by_id["1:30"]["heightErrorPx"] == 585.0
    assert by_id["1:30"]["driftIntroducedPx"] == 0.0
    assert by_id["1:40"]["heightErrorPx"] == 0.0
    assert by_id["1:40"]["offsetErrorPx"] == [0.0, 585.0]


def test_nodes_within_tolerance_are_not_reported() -> None:
    dom = {
        "documentHeight": 1647,
        "documentWidth": 1366,
        "nodes": [
            _node("1:10", 0, 161),
            _node("1:20", 161, 460),
            _node("1:30", 621, 727),
            _node("1:40", 1348, 300),
        ],
    }

    summary = compare_geometry(_index(), dom, design_width=1366, design_height=1647, tolerance_px=2)

    assert summary["nodesOutOfTolerance"] == 0
    assert summary["worstNodes"] == []
    assert summary["driftSequence"] == []


def test_hooks_that_are_not_node_ids_are_flagged_rather_than_silently_dropped() -> None:
    dom = {
        "documentHeight": 1647,
        "documentWidth": 1366,
        "nodes": [
            {"figmaId": "Promo/hero banner", "selector": "div.hero", "x": 0, "y": 160, "w": 1366, "h": 460}
        ],
    }

    summary = compare_geometry(_index(), dom, design_width=1366, design_height=1647)

    assert summary["matchedNodes"] == 0
    assert summary["unmatchedHooks"] == ["Promo/hero banner"]
    assert summary["hookCoveragePct"] == 0.0
    assert "must be Figma node ids" in (geometry_headline(summary) or "")


def test_missing_measurements_degrade_to_an_empty_summary() -> None:
    summary = compare_geometry(_index(), None, design_width=1366, design_height=1647)
    assert summary["matchedNodes"] == 0
    assert summary["documentHeightErrorPx"] is None
    assert geometry_headline(summary) is None
    assert geometry_headline(None) is None


def test_headline_names_the_largest_contributor() -> None:
    dom = {
        "documentHeight": 2232,
        "documentWidth": 1366,
        "nodes": [_node("1:10", 0, 160), _node("1:20", 160, 460), _node("1:40", 1932, 300)],
    }

    headline = geometry_headline(
        compare_geometry(_index(), dom, design_width=1366, design_height=1647)
    )

    assert headline is not None
    assert "+585px" in headline
    assert "'Footer'" in headline and "1:40" in headline


def test_the_outermost_element_wins_when_an_id_is_reused() -> None:
    dom = {
        "documentHeight": 1647,
        "documentWidth": 1366,
        "nodes": [_node("1:20", 160, 40), _node("1:20", 160, 460)],
    }

    summary = compare_geometry(_index(), dom, design_width=1366, design_height=1647)

    assert summary["matchedNodes"] == 1
    assert summary["nodesOutOfTolerance"] == 0


def _audit(width: int, centres: dict[str, float]) -> dict[str, object]:
    return {"viewportWidth": width, "hookCentres": centres}


def test_pinning_is_detected_when_content_stops_centring() -> None:
    """A left-pinned band drifts by exactly half the extra viewport width."""
    audits = [
        _audit(1366, {"1:20": 0.0, "1:30": -100.0}),
        # 554px wider: a centred element holds its offset, a pinned one loses 277.
        _audit(1920, {"1:20": -277.0, "1:30": -100.0}),
    ]

    result = detect_layout_pinning(audits, design_width=1366)

    assert result["pinnedCount"] == 1
    pinned = result["pinnedElements"][0]
    assert pinned["figmaId"] == "1:20"
    assert pinned["driftPx"] == 277.0
    assert pinned["driftFraction"] == 1.0
    assert result["checkedWidths"] == [1920]


def test_centred_layout_reports_no_pinning() -> None:
    audits = [
        _audit(1366, {"1:20": 0.0, "1:30": -150.0}),
        _audit(1920, {"1:20": 0.0, "1:30": -150.0}),
    ]

    result = detect_layout_pinning(audits, design_width=1366)

    assert result["pinnedCount"] == 0
    assert pinning_headline(result) is None


def test_partially_fluid_layout_is_judged_on_its_share_of_full_pinning() -> None:
    # Drifts 100 of a possible 277: fluid enough not to be called pinned.
    audits = [_audit(1366, {"1:20": 0.0}), _audit(1920, {"1:20": -100.0})]
    assert detect_layout_pinning(audits, design_width=1366)["pinnedCount"] == 0

    # Drifts 200 of 277: mostly pinned.
    audits = [_audit(1366, {"1:20": 0.0}), _audit(1920, {"1:20": -200.0})]
    assert detect_layout_pinning(audits, design_width=1366)["pinnedCount"] == 1


def test_pinning_needs_a_baseline_at_the_design_width() -> None:
    audits = [_audit(768, {"1:20": 0.0}), _audit(1920, {"1:20": -277.0})]
    result = detect_layout_pinning(audits, design_width=1366)
    assert result["pinnedElements"] == []
    assert result["checkedWidths"] == []


def test_pinning_headline_quantifies_the_worst_offender() -> None:
    audits = [_audit(1366, {"1:20": 0.0}), _audit(1920, {"1:20": -277.0})]
    headline = pinning_headline(detect_layout_pinning(audits, design_width=1366))
    assert headline is not None
    assert "277px off centre" in headline
    assert "1366px design width" in headline
