from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import quote

import httpx

from figma_to_sitecore.utils.logging import log

STORYBOOK_PATHS = {
    "accordion": "/edsredesign/Accordion",
    "carousel": "/edsredesign/Carousel",
    "footer": "/edsredesign/footer",
    "hero-banner": "/edsredesign/Herobanner",
    "header": "/edsredesign/header",
    "button-links": "/edsredesign/buttons and links",
    "card": "/edsredesign/card",
    "content-block": "/edsredesign/content-block",
    "filter": "/edsredesign/a/filter#customsearch_e=0",
    "announcement-banner": "/edsredesign/Announcement Banner",
    "breadcrumb": "/edsredesign/Breadcrumb Demo/Breadcrumb",
    "dropdown": "/edsredesign/dropdown",
    "isi": "/eDSRedesign/isi variant 1",
    "modal": "/edsredesign/a/modal",
    "video": "/edsredesign/video",
    "professional-profile": "/edsredesign/Professional Profile Card",
    "quiz": "/edsredesign/quiz",
    "resources-downloads": "/edsredesign/Resources and Downloads",
    "sticky-cta": "/edsredesign/sticky CTA",
    "search": "/edsredesign/a/Search",
    "tabs": "/edsredesign/tabdemo",
    "testimonial": "/edsredesign/Testimonial Variants",
    "flip-card": "/edsredesign/Flipcards",
    "read-more-read-less": "/edsredesign/a/rd",
}


def storybook_url(name: str, base: str) -> str | None:
    relative = STORYBOOK_PATHS.get(name)
    if not relative:
        return None
    path, _, fragment = relative.partition("#")
    encoded_path = "/".join(quote(segment, safe="") for segment in path.split("/"))
    suffix = f"#{fragment}" if fragment else ""
    return f"{base.rstrip('/')}{encoded_path}{suffix}"


async def fetch_storybook_html(client: httpx.AsyncClient, url: str) -> str:
    try:
        response = await client.get(url, headers={"Accept": "text/html,application/xhtml+xml"})
        if response.is_error:
            log.warning("Storybook %s -> HTTP %s", url, response.status_code)
            return ""
        return response.text
    except (httpx.HTTPError, asyncio.TimeoutError) as exc:
        log.warning("Storybook %s unavailable (%s)", url, exc)
        return ""


def extract_snippet(html: str) -> str:
    match = re.search(r'<\w+[^>]*class="[^"]*\bcomponent eds-[a-z0-9-]+', html)
    if not match:
        return ""
    return "\n".join(html[match.start() : match.start() + 6000].splitlines()[:90])


def collect_eds_classes(html: str) -> list[str]:
    classes = {match.group(0) for match in re.finditer(r"\beds-[a-z0-9-]+\b", html)}
    classes = {name for name in classes if not name.startswith("eds-btn") or name == "eds-btn"}
    classes -= {"eds-wrapper", "eds-header", "eds-main", "eds-footer"}
    return sorted(classes)


async def hydrate_storybook_snippets(components: list[dict[str, Any]], base: str) -> list[dict[str, Any]]:
    targets = [component for component in components if (component.get("name") or component.get("folder")) in STORYBOOK_PATHS]
    if not targets:
        return components
    log.info("Fetching %s EDS component snippets from Storybook", len(targets))
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        async def hydrate(component: dict[str, Any]) -> bool:
            name = str(component.get("name") or component.get("folder") or "")
            url = storybook_url(name, base)
            html = await fetch_storybook_html(client, url) if url else ""
            snippet = extract_snippet(html)
            if not snippet:
                return False
            component["snippet"] = snippet[:4000]
            if not component.get("edsClasses"):
                component["edsClasses"] = collect_eds_classes(html)
            component["source"] = "storybook"
            return True

        results = await asyncio.gather(*(hydrate(component) for component in targets))
    log.info("Refreshed %s/%s Storybook snippets", sum(results), len(targets))
    return components


async def scan_storybook_components(base: str) -> list[dict[str, Any]]:
    log.info("Building EDS manifest from %s Storybook pages", len(STORYBOOK_PATHS))
    async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
        async def scan(name: str) -> dict[str, Any]:
            url = storybook_url(name, base)
            html = await fetch_storybook_html(client, url) if url else ""
            bootstrap_features = sorted(
                {match.group(2) or match.group(1) for match in re.finditer(r'data-bs-(toggle|ride|target)="([a-z-]+)"?', html)}
            )
            return {
                "name": name,
                "folder": name,
                "edsClasses": collect_eds_classes(html),
                "bootstrapFeatures": bootstrap_features,
                "description": f"EDS {name.replace('-', ' ')} component",
                "whenToUse": "",
                "keywords": name.split("-"),
                "structureOutline": "",
                "snippet": extract_snippet(html)[:4000],
                "source": "storybook",
                "url": url,
            }

        components = await asyncio.gather(*(scan(name) for name in STORYBOOK_PATHS))
    return sorted(components, key=lambda component: component["name"])
