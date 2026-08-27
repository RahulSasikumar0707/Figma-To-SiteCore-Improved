from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


def _collect_stats(
    node: dict[str, Any],
    stats: dict[str, int] | None = None,
    depth: int = 0,
) -> dict[str, int]:
    stats = stats or {"texts": 0, "images": 0, "buttons": 0, "links": 0, "inputs": 0, "repeats": 0, "depth": 0}
    stats["depth"] = max(stats["depth"], depth)
    if node.get("text"):
        stats["texts"] += 1
    if node.get("asset") or node.get("bgImage"):
        stats["images"] += 1
    name = node.get("name", "").lower()
    stats["buttons"] += bool(re.search(r"\b(btn|button|cta)\b", name))
    stats["links"] += bool(re.search(r"\b(link|nav item|menu)\b", name))
    stats["inputs"] += bool(re.search(r"\b(input|field|form|textarea|checkbox|radio|select)\b", name))
    if node.get("repeats"):
        stats["repeats"] = max(stats["repeats"], node["repeats"]["count"])
    for child in node.get("children") or []:
        _collect_stats(child, stats, depth + 1)
    return stats


def _collect_text(node: dict[str, Any], output: list[str] | None = None) -> list[str]:
    output = output if output is not None else []
    output.append(node.get("name", ""))
    if node.get("text", {}).get("content"):
        output.append(node["text"]["content"])
    for child in node.get("children") or []:
        _collect_text(child, output)
    return output


def _tokens(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", value.lower()) if len(part) > 2}


Hint = tuple[Callable[[dict[str, Any]], bool], dict[str, int]]


STRUCTURE_HINTS: list[Hint] = [
    (lambda c: c["stats"]["repeats"] >= 3 and c["stats"]["images"] >= 2, {"cards": 6, "carousel": 4, "flip-card": 2}),
    (
        lambda c: c["stats"]["depth"] <= 3
        and c["stats"]["buttons"] >= 1
        and c["stats"]["images"] >= 1
        and c["section"].get("frame", {}).get("y") == 0,
        {"hero-banner": 6, "content-block": 2},
    ),
    (
        lambda c: bool(re.search(r"head|nav", c["section"].get("name", ""), re.I))
        or (c["section"].get("frame", {}).get("y", 1) == 0 and c["stats"]["links"] >= 3),
        {"header": 5, "breadcrumb": 1},
    ),
    (lambda c: bool(re.search(r"foot", c["section"].get("name", ""), re.I)), {"footer": 8}),
    (
        lambda c: c["stats"]["texts"] >= 4 and c["stats"]["images"] == 0 and c["stats"]["repeats"] >= 3,
        {"accordion": 3, "references": 2, "table": 2},
    ),
    (lambda c: c["stats"]["inputs"] > 0, {"form": 8, "search": 3}),
    (lambda c: bool(re.search(r"video|play", c["all_names"], re.I)), {"video": 5, "video-modal": 3}),
    (lambda c: bool(re.search(r"tab", c["all_names"], re.I)), {"tabs": 5}),
    (lambda c: bool(re.search(r"testimonial|quote", c["all_names"], re.I)), {"testimonial": 6}),
    (lambda c: bool(re.search(r"breadcrumb", c["all_names"], re.I)), {"breadcrumb": 8}),
    (lambda c: bool(re.search(r"accordion|faq|expand", c["all_names"], re.I)), {"accordion": 6, "accordion-media": 3}),
]


def match_sections(
    spec_root: dict[str, Any] | None,
    components: list[dict[str, Any]],
    top_k: int = 5,
) -> list[dict[str, Any]]:
    if not spec_root:
        return []
    sections = [
        child
        for child in spec_root.get("children") or []
        if child.get("children") or child.get("asset") or child.get("bgImage")
    ]
    targets = sections or [spec_root]
    matches: list[dict[str, Any]] = []
    for section in targets:
        stats = _collect_stats(section)
        all_names = " ".join(_collect_text(section))
        words = _tokens(all_names)
        context = {"section": section, "stats": stats, "all_names": all_names}
        scores: list[dict[str, Any]] = []
        for component in components:
            score = sum(2 for keyword in component.get("keywords") or [] if str(keyword).lower() in words)
            name = component.get("name") or component.get("folder") or ""
            score += sum(3 for token in _tokens(name.replace("-", " ")) if token in words)
            for test, boosts in STRUCTURE_HINTS:
                if test(context):
                    component_name = str(component.get("name") or "")
                    component_folder = str(component.get("folder") or "")
                    score += boosts.get(component_name, boosts.get(component_folder, 0))
            scores.append({"name": component.get("name"), "score": score})
        scores.sort(key=lambda item: item["score"], reverse=True)
        matches.append(
            {
                "section": section.get("name"),
                # The node id doubles as the data-figma-id hook the geometry
                # audit measures, so it must travel with the section match.
                "sectionId": section.get("id"),
                "frame": section.get("frame"),
                "abs": section.get("abs"),
                "stats": stats,
                "candidates": [item for item in scores[:top_k] if item["score"] > 0],
            }
        )
    return matches


def shortlisted_components(
    matches: list[dict[str, Any]],
    components: list[dict[str, Any]],
    maximum: int = 12,
) -> list[dict[str, Any]]:
    names = {candidate["name"] for match in matches for candidate in match["candidates"]}
    shortlist = [component for component in components if component.get("name") in names]
    for always in ("buttons", "button-links", "content-block", "cards", "card"):
        component = next(
            (item for item in components if item.get("name") == always or item.get("folder") == always),
            None,
        )
        if component and component not in shortlist:
            shortlist.append(component)
    return shortlist[:maximum]
