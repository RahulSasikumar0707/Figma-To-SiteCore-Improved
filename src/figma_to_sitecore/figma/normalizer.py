from __future__ import annotations

import json
import math
import re
from collections import Counter
from typing import Any

PURE_VECTOR_TYPES = {"VECTOR", "BOOLEAN_OPERATION", "STAR", "LINE", "POLYGON", "REGULAR_POLYGON"}
SHAPE_TYPES = PURE_VECTOR_TYPES | {"ELLIPSE", "RECTANGLE"}
CONTAINER_TYPES = {"FRAME", "GROUP", "INSTANCE", "COMPONENT", "COMPONENT_SET", "SECTION"}
ICON_NAME_RE = re.compile(r"\b(icon|logo|glyph|vector|illustration|arrow|chevron|badge)\b", re.I)


def _js_round(value: float) -> int:
    return math.floor(value + 0.5)


def _round1(value: Any) -> Any:
    return _js_round(value * 10) / 10 if isinstance(value, (int, float)) else value


def rgba_to_hex(color: dict[str, Any] | None, opacity: float = 1) -> str | None:
    if not color:
        return None
    alpha = float(color.get("a", 1)) * opacity
    channels = [_js_round(float(color.get(channel, 0)) * 255) for channel in ("r", "g", "b")]
    value = "#" + "".join(f"{channel:02x}" for channel in channels)
    return value if alpha >= 0.999 else value + f"{_js_round(alpha * 255):02x}"


def _visible_fills(node: dict[str, Any]) -> list[dict[str, Any]]:
    return [fill for fill in node.get("fills") or [] if fill.get("visible") is not False and fill.get("type")]


def _has_image_fill(node: dict[str, Any]) -> bool:
    return any(fill.get("type") == "IMAGE" for fill in _visible_fills(node))


def _is_vector_only_subtree(node: dict[str, Any]) -> bool:
    if node.get("visible") is False:
        return True
    if node.get("type") == "TEXT" or _has_image_fill(node):
        return False
    if node.get("type") in SHAPE_TYPES:
        return True
    if node.get("type") in CONTAINER_TYPES:
        children = node.get("children") or []
        return bool(children) and all(_is_vector_only_subtree(child) for child in children)
    return False


def _box(node: dict[str, Any]) -> dict[str, float] | None:
    bounds = node.get("absoluteBoundingBox") or node.get("absoluteRenderBounds")
    if not bounds:
        return None
    return {"x": bounds["x"], "y": bounds["y"], "w": bounds["width"], "h": bounds["height"]}


def _clean(mapping: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in mapping.items() if value is not None}


def normalize_design(root_node: dict[str, Any]) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    asset_by_node: dict[str, dict[str, Any]] = {}
    asset_by_signature: dict[str, dict[str, Any]] = {}
    palette: Counter[str] = Counter()
    text_styles: dict[str, dict[str, Any]] = {}
    spacing: Counter[int] = Counter()
    radii: set[int] = set()
    shadows: set[str] = set()
    font_families: Counter[str] = Counter()

    def register_asset(
        node: dict[str, Any], kind: str, export_as: str, image_ref: str | None = None
    ) -> str:
        if node["id"] in asset_by_node:
            return asset_by_node[node["id"]]["id"]
        bounds = _box(node) or {"w": 0, "h": 0}
        signature = None
        if export_as == "svg":
            signature = (
                f"cmp|{node['componentId']}"
                if node.get("componentId")
                else f"{kind}|{node.get('name', '').lower()}|{_round1(bounds['w'])}x{_round1(bounds['h'])}"
            )
            if signature in asset_by_signature:
                duplicate = asset_by_signature[signature]
                asset_by_node[node["id"]] = duplicate
                return duplicate["id"]
        asset = {
            "id": f"a{len(assets) + 1}",
            "nodeId": node["id"],
            "name": node.get("name") or kind,
            "kind": kind,
            "export": export_as,
            "imageRef": image_ref,
            "w": _round1(bounds["w"]),
            "h": _round1(bounds["h"]),
        }
        assets.append(asset)
        asset_by_node[node["id"]] = asset
        if signature:
            asset_by_signature[signature] = asset
        return asset["id"]

    def note_color(value: str | None) -> None:
        if value:
            palette[value] += 1

    def note_spacing(value: Any) -> None:
        if isinstance(value, (int, float)) and value > 0:
            spacing[_js_round(value)] += 1

    def map_fills(node: dict[str, Any]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for fill in _visible_fills(node):
            fill_type = fill["type"]
            if fill_type == "SOLID":
                color = rgba_to_hex(fill.get("color"), fill.get("opacity", 1))
                note_color(color)
                result.append({"type": "solid", "hex": color})
            elif fill_type.startswith("GRADIENT"):
                stops = [
                    {"hex": rgba_to_hex(stop.get("color")), "pos": _round1(stop.get("position"))}
                    for stop in fill.get("gradientStops") or []
                ]
                for stop in stops:
                    note_color(stop["hex"])
                result.append({"type": fill_type.replace("GRADIENT_", "gradient-").lower(), "stops": stops})
            elif fill_type == "IMAGE":
                result.append(
                    {
                        "type": "image",
                        "imageRef": fill.get("imageRef"),
                        "scaleMode": fill.get("scaleMode", "FILL").lower(),
                    }
                )
        return result

    def map_stroke(node: dict[str, Any]) -> dict[str, Any] | None:
        strokes = [
            stroke
            for stroke in node.get("strokes") or []
            if stroke.get("visible") is not False and stroke.get("type") == "SOLID"
        ]
        if not strokes and "cornerRadius" not in node and not node.get("rectangleCornerRadii"):
            return None
        result: dict[str, Any] = {}
        if strokes:
            result["color"] = rgba_to_hex(strokes[0].get("color"), strokes[0].get("opacity", 1))
            result["weight"] = _round1(node.get("strokeWeight", 1))
            note_color(result["color"])
        radius_values = node.get("rectangleCornerRadii")
        if not radius_values and "cornerRadius" in node:
            radius_values = [node["cornerRadius"]]
        if radius_values:
            radius = (
                _round1(radius_values[0])
                if len(radius_values) == 1 or all(value == radius_values[0] for value in radius_values)
                else [_round1(value) for value in radius_values]
            )
            result["radius"] = radius
            first_radius = radius[0] if isinstance(radius, list) else radius
            if first_radius > 0:
                radii.add(_js_round(first_radius))
        return result or None

    def map_effects(node: dict[str, Any]) -> list[str] | None:
        result: list[str] = []
        for effect in node.get("effects") or []:
            if effect.get("visible") is False:
                continue
            effect_type = effect.get("type")
            if effect_type in {"DROP_SHADOW", "INNER_SHADOW"}:
                offset = effect.get("offset") or {}
                value = (
                    ("inset " if effect_type == "INNER_SHADOW" else "")
                    + f"{_round1(offset.get('x', 0))}px {_round1(offset.get('y', 0))}px "
                    + f"{_round1(effect.get('radius', 0))}px {_round1(effect.get('spread', 0))}px "
                    + str(rgba_to_hex(effect.get("color")))
                )
                shadows.add(value)
                result.append(value)
            elif effect_type == "LAYER_BLUR":
                result.append(f"blur({_round1(effect.get('radius'))}px)")
            elif effect_type == "BACKGROUND_BLUR":
                result.append(f"backdrop-blur({_round1(effect.get('radius'))}px)")
        return result or None

    def map_layout(node: dict[str, Any]) -> dict[str, Any] | None:
        if node.get("layoutMode") in (None, "NONE"):
            return None
        justify = {"MIN": "flex-start", "CENTER": "center", "MAX": "flex-end", "SPACE_BETWEEN": "space-between"}
        align = {"MIN": "flex-start", "CENTER": "center", "MAX": "flex-end", "BASELINE": "baseline"}
        result: dict[str, Any] = {
            "mode": "row" if node["layoutMode"] == "HORIZONTAL" else "column",
            "gap": _round1(node.get("itemSpacing", 0)),
            "padding": [
                _round1(node.get(key, 0))
                for key in ("paddingTop", "paddingRight", "paddingBottom", "paddingLeft")
            ],
            "justify": justify.get(str(node.get("primaryAxisAlignItems")), "flex-start"),
            "align": align.get(str(node.get("counterAxisAlignItems")), "flex-start"),
        }
        if node.get("layoutWrap") == "WRAP":
            result["wrap"] = True
        note_spacing(result["gap"])
        for value in result["padding"]:
            note_spacing(value)
        return result

    def map_sizing(node: dict[str, Any]) -> dict[str, Any] | None:
        names = {"FIXED": "fixed", "HUG": "hug", "FILL": "fill"}
        result = _clean(
            {
                "h": names.get(str(node.get("layoutSizingHorizontal"))),
                "v": names.get(str(node.get("layoutSizingVertical"))),
                "grow": node.get("layoutGrow") or None,
                "stretch": True if node.get("layoutAlign") == "STRETCH" else None,
            }
        )
        return result or None

    def map_text(node: dict[str, Any]) -> dict[str, Any]:
        style = node.get("style") or {}
        solid = next((fill for fill in _visible_fills(node) if fill.get("type") == "SOLID"), None)
        color = rgba_to_hex(solid.get("color"), solid.get("opacity", 1)) if solid else None
        note_color(color)
        result = _clean(
            {
                "content": node.get("characters", ""),
                "font": style.get("fontFamily"),
                "weight": style.get("fontWeight"),
                "size": _round1(style.get("fontSize")),
                "lineHeight": _round1(style.get("lineHeightPx")) if style.get("lineHeightPx") else None,
                "letterSpacing": _round1(style.get("letterSpacing")) if style.get("letterSpacing") else None,
                "align": str(style.get("textAlignHorizontal", "LEFT")).lower(),
                "case": str(style.get("textCase", "")).lower()
                if style.get("textCase") not in (None, "ORIGINAL")
                else None,
                "decoration": str(style.get("textDecoration", "")).lower()
                if style.get("textDecoration") not in (None, "NONE")
                else None,
                "color": color,
            }
        )
        if style.get("fontFamily"):
            font_families[style["fontFamily"]] += 1
        signature = "|".join(str(result.get(key)) for key in ("font", "weight", "size", "lineHeight"))
        entry = text_styles.setdefault(
            signature, {**result, "count": 0, "sample": result.get("content", "")[:40]}
        )
        entry["count"] += 1
        return result

    root_origin = _box(root_node)

    def signature(node: dict[str, Any]) -> str:
        children = node.get("children") or []
        return f"{node.get('type')}:{len(children)}:{','.join(child.get('type', '') for child in children)}"

    def walk(node: dict[str, Any], parent_box: dict[str, float] | None) -> dict[str, Any] | None:
        if node.get("visible") is False:
            return None
        bounds = _box(node)
        spec: dict[str, Any] = {"id": node.get("id"), "name": node.get("name"), "type": node.get("type")}
        if bounds:
            spec["frame"] = {
                "x": _round1(bounds["x"] - (parent_box or bounds)["x"]),
                "y": _round1(bounds["y"] - (parent_box or bounds)["y"]),
                "w": _round1(bounds["w"]),
                "h": _round1(bounds["h"]),
            }
            # Frame-relative geometry is what the browser must reproduce; the
            # deterministic geometry audit compares this against getBoundingClientRect.
            origin = root_origin or bounds
            spec["abs"] = {
                "x": _round1(bounds["x"] - origin["x"]),
                "y": _round1(bounds["y"] - origin["y"]),
            }
        if node.get("opacity", 1) < 1:
            spec["opacity"] = _round1(node["opacity"])

        is_leaf_image = node.get("type") != "TEXT" and _has_image_fill(node) and not (node.get("children") or [])
        if is_leaf_image:
            fills = map_fills(node)
            image = next((fill for fill in fills if fill["type"] == "image"), None)
            image_ref = image.get("imageRef") if image else None
            spec.update(asset=register_asset(node, "image", "imageRef" if image_ref else "png", image_ref), role="image")
            overlays = [fill for fill in fills if fill["type"] != "image"]
            if overlays:
                spec["bg"] = overlays
            if stroke := map_stroke(node):
                spec["border"] = stroke
            if effects := map_effects(node):
                spec["effects"] = effects
            return spec

        node_type = str(node.get("type") or "")
        if node_type in SHAPE_TYPES | CONTAINER_TYPES:
            vector_only = _is_vector_only_subtree(node)
            small = bool(bounds and bounds["w"] <= 96 and bounds["h"] <= 96)
            named = bool(ICON_NAME_RE.search(node.get("name", "")))
            if vector_only and (node_type in PURE_VECTOR_TYPES or small or named):
                kind = "icon" if small or named else "vector"
                spec.update(asset=register_asset(node, kind, "svg"), role=kind)
                return spec

        fills = map_fills(node)
        image_fill = next((fill for fill in fills if fill["type"] == "image"), None)
        if image_fill:
            image_ref = image_fill.get("imageRef")
            spec["bgImage"] = register_asset(node, "image", "imageRef" if image_ref else "png", image_ref)
            spec["bgImageMode"] = image_fill["scaleMode"]
        backgrounds = [fill for fill in fills if fill["type"] != "image"]
        if backgrounds:
            spec["bg"] = backgrounds
        if stroke := map_stroke(node):
            spec["border"] = stroke
        if effects := map_effects(node):
            spec["effects"] = effects
        if layout := map_layout(node):
            spec["layout"] = layout
        if sizing := map_sizing(node):
            spec["sizing"] = sizing
        if node.get("clipsContent"):
            spec["clips"] = True
        if node_type == "TEXT":
            spec["text"] = map_text(node)
            return spec

        children: list[dict[str, Any]] = []
        signatures: list[str] = []
        for child in node.get("children") or []:
            child_spec = walk(child, bounds)
            if child_spec:
                children.append(child_spec)
                signatures.append(signature(child))
        if children:
            spec["children"] = children
            counts = Counter(signatures)
            top_signature, top_count = counts.most_common(1)[0]
            if top_count >= 3:
                spec["repeats"] = {"count": top_count, "of": top_signature}
        return spec

    root = walk(root_node, None)
    return {
        "root": root,
        "rootSize": {"w": _round1(root_origin["w"]), "h": _round1(root_origin["h"])} if root_origin else None,
        "assets": assets,
        "tokens": {
            "palette": [{"hex": color, "count": count} for color, count in palette.most_common()],
            "textStyles": sorted(text_styles.values(), key=lambda item: item["count"], reverse=True),
            "fontFamilies": [name for name, _ in font_families.most_common()],
            "spacingScale": sorted(spacing),
            "radii": sorted(radii),
            "shadows": sorted(shadows),
        },
    }


def compact_spec(spec_root: dict[str, Any], budget_chars: int = 140_000) -> str:
    """Serialize the design tree for the model without ever losing design copy.

    Structural depth is traded away before anything else, and decorative detail
    before that. Text ``content`` is never shortened: a truncated string reads as
    finished copy to the model, which then invents the remainder.
    """

    def count_nodes(node: dict[str, Any]) -> int:
        return 1 + sum(count_nodes(child) for child in node.get("children") or [])

    def clip(node: dict[str, Any], depth: int, max_depth: int, plain: bool) -> dict[str, Any]:
        result = dict(node)
        if plain:
            for key in ("effects", "bg", "border", "opacity", "repeats"):
                result.pop(key, None)
        children = node.get("children")
        if children:
            if depth >= max_depth:
                result.pop("children", None)
                result["omitted"] = f"{count_nodes(node) - 1} descendant nodes omitted (depth cap)"
            else:
                result["children"] = [clip(child, depth + 1, max_depth, plain) for child in children]
        return result

    for plain in (False, True):
        for max_depth in range(40, 1, -2):
            value = json.dumps(clip(spec_root, 0, max_depth, plain), separators=(",", ":"), ensure_ascii=False)
            if len(value) <= budget_chars:
                return value
    # Even the flattest form is over budget. Copy fidelity outranks the budget.
    return json.dumps(clip(spec_root, 0, 1, True), separators=(",", ":"), ensure_ascii=False)


def text_inventory(spec_root: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Every text run in document order, complete and never clipped.

    ``compact_spec`` may drop nodes below its depth cap. This inventory is the
    authoritative copy deck, so no wording can be lost to a structural budget.
    """
    inventory: list[dict[str, Any]] = []

    def walk(node: dict[str, Any]) -> None:
        text = node.get("text")
        if isinstance(text, dict) and str(text.get("content", "")).strip():
            inventory.append(
                _clean(
                    {
                        "id": node.get("id"),
                        "name": node.get("name"),
                        "abs": node.get("abs"),
                        "w": (node.get("frame") or {}).get("w"),
                        "content": text.get("content"),
                        "font": text.get("font"),
                        "weight": text.get("weight"),
                        "size": text.get("size"),
                        "lineHeight": text.get("lineHeight"),
                        "letterSpacing": text.get("letterSpacing"),
                        "align": text.get("align"),
                        "case": text.get("case"),
                        "decoration": text.get("decoration"),
                        "color": text.get("color"),
                    }
                )
            )
        for child in node.get("children") or []:
            walk(child)

    if spec_root:
        walk(spec_root)
    return inventory


def geometry_index(spec_root: dict[str, Any] | None, *, min_side: float = 8.0) -> dict[str, dict[str, Any]]:
    """Map every laid-out node id to its absolute box inside the root frame.

    This is the ground truth the rendered DOM is measured against. Sub-pixel
    decorations are excluded because they carry no useful layout signal.
    """
    index: dict[str, dict[str, Any]] = {}

    def walk(node: dict[str, Any]) -> None:
        node_id = node.get("id")
        frame = node.get("frame") or {}
        absolute = node.get("abs") or {}
        width = float(frame.get("w") or 0)
        height = float(frame.get("h") or 0)
        if node_id and width >= min_side and height >= min_side:
            index[str(node_id)] = {
                "id": str(node_id),
                "name": node.get("name"),
                "type": node.get("type"),
                "x": float(absolute.get("x") or 0),
                "y": float(absolute.get("y") or 0),
                "w": width,
                "h": height,
            }
        for child in node.get("children") or []:
            walk(child)

    if spec_root:
        walk(spec_root)
    return index
