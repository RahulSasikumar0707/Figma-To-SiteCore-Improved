from __future__ import annotations

from pathlib import Path
from typing import Any

from figma_to_sitecore.eds.storybook import scan_storybook_components
from figma_to_sitecore.utils.files import read_json_if_exists
from figma_to_sitecore.utils.logging import log


async def load_eds_manifest(path: Path, storybook_base: str) -> tuple[list[dict[str, Any]], bool]:
    """Load the curated manifest, crawling Storybook only when it is unusable.

    The second element is True when the curated file supplied the components, so
    callers can skip network work that the manifest has already made unnecessary.
    """
    try:
        curated = read_json_if_exists(path)
    except (OSError, ValueError) as exc:
        log.warning("EDS manifest %s is invalid (%s); scanning Storybook", path, exc)
        curated = None
    raw_components = curated.get("components", []) if isinstance(curated, dict) else []
    components = [
        {**component, "name": component.get("name") or component.get("folder"), "folder": component.get("folder") or component.get("name")}
        for component in raw_components
        if isinstance(component, dict) and isinstance(component.get("name") or component.get("folder"), str)
    ]
    if components:
        dropped = len(raw_components) - len(components)
        if dropped:
            log.warning("Dropped %s malformed EDS manifest entries", dropped)
        log.info("Loaded %s curated EDS components from %s", len(components), path.name)
        return components, True
    log.warning("Curated EDS manifest is unavailable; scanning Storybook")
    return await scan_storybook_components(storybook_base), False


def manifest_catalog(components: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for component in components:
        classes = " ".join((component.get("edsClasses") or [])[:4])
        keywords = ", ".join((component.get("keywords") or [])[:10])
        use = f"Use when: {component['whenToUse']}" if component.get("whenToUse") else ""
        lines.append(
            f"- {component['name']} [{classes}] — {component.get('description', '')} {use} (keywords: {keywords})"
        )
    return "\n".join(lines)

