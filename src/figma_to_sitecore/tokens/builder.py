from __future__ import annotations

import re
from typing import Any


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")


def build_design_tokens(
    tokens: dict[str, Any], figma_variables: dict[str, Any] | None = None
) -> tuple[str, dict[str, dict[Any, str]]]:
    lines: list[str] = [
        "/* Design tokens extracted from Figma — single source of truth for generated CSS. */",
        ":root {",
        "  /* colors (ordered by frequency in the design) */",
    ]
    token_map: dict[str, dict[Any, str]] = {
        "colors": {},
        "fonts": {},
        "text": {},
        "spacing": {},
        "radius": {},
        "shadows": {},
    }

    for index, palette_entry in enumerate(tokens.get("palette") or []):
        color = palette_entry["hex"]
        suffix = "primary" if index == 0 else "secondary" if index == 1 else _slug(color.replace("#", "c-"))
        name = f"--fig-color-{suffix}"
        lines.append(f"  {name}: {color}; /* used {palette_entry['count']}x */")
        token_map["colors"][color] = name

    lines.append("  /* typography */")
    for index, font in enumerate(tokens.get("fontFamilies") or []):
        name = "--fig-font-primary" if index == 0 else f"--fig-font-{_slug(font)}"
        escaped_font = str(font).replace("\\", "\\\\").replace("'", "\\'")
        lines.append(f"  {name}: '{escaped_font}', sans-serif;")
        token_map["fonts"][font] = name
    seen_sizes: set[float] = set()
    for text_style in tokens.get("textStyles") or []:
        size = text_style.get("size")
        if not size or size in seen_sizes:
            continue
        seen_sizes.add(size)
        name = f"--fig-text-{str(size).replace('.', '_')}"
        comment = f" /* line-height ~{text_style['lineHeight']}px */" if text_style.get("lineHeight") else ""
        lines.append(f"  {name}: {size}px;{comment}")
        token_map["text"][size] = name

    lines.append("  /* spacing scale */")
    for space in tokens.get("spacingScale") or []:
        name = f"--fig-space-{space}"
        lines.append(f"  {name}: {space}px;")
        token_map["spacing"][space] = name

    if tokens.get("radii"):
        lines.append("  /* border radii */")
        for radius in tokens["radii"]:
            name = f"--fig-radius-{radius}"
            lines.append(f"  {name}: {radius}px;")
            token_map["radius"][radius] = name

    if tokens.get("shadows"):
        lines.append("  /* shadows */")
        for index, shadow in enumerate(tokens["shadows"], start=1):
            name = f"--fig-shadow-{index}"
            lines.append(f"  {name}: {shadow};")
            token_map["shadows"][shadow] = name

    if isinstance(figma_variables, dict):
        lines.append("  /* Figma variable definitions (Dev Mode MCP) */")
        used: dict[str, str] = {}
        for key, value in _flatten(figma_variables).items():
            base_name = f"--fig-var-{_slug(key)}"
            name = base_name
            if name in used:
                if used[name] == str(value):
                    continue
                counter = 2
                while f"{base_name}-{counter}" in used:
                    counter += 1
                name = f"{base_name}-{counter}"
            used[name] = str(value)
            lines.append(f"  {name}: {_css_safe_value(value)};")

    lines.append("}")
    return "\n".join(lines) + "\n", token_map


def _css_safe_value(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    text = str(value)
    if re.fullmatch(r"[^;{}\"'\\]*", text) and "/*" not in text:
        return text
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\r\n", "\\a ").replace("\n", "\\a ")
    return f'"{escaped}"'


def _flatten(value: dict[str, Any], prefix: str = "", output: dict[str, Any] | None = None) -> dict[str, Any]:
    output = output if output is not None else {}
    for key, child in value.items():
        path = f"{prefix}-{key}" if prefix else key
        if isinstance(child, dict):
            _flatten(child, path, output)
        elif isinstance(child, (str, int, float)) and not isinstance(child, bool):
            output[path] = child
    return output

