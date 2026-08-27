from __future__ import annotations

import hashlib
import io
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlsplit

from figma_to_sitecore.review.geometry import probe_dom_geometry
from figma_to_sitecore.utils.files import write_file
from figma_to_sitecore.utils.logging import log


@dataclass(frozen=True, slots=True)
class DiffRegion:
    x: int
    y: int
    width: int
    height: int
    mismatched_pixels: int
    mismatch_pct: float
    max_channel_delta: int

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VisualDiffResult:
    dimensions_equal: bool
    reference_width: int
    reference_height: int
    rendered_width: int
    rendered_height: int
    mismatched_pixels: int
    total_pixels: int
    mismatch_pct: float
    mean_absolute_error: float
    max_channel_delta: int
    threshold: int
    mismatch_bounds: tuple[int, int, int, int] | None
    regions: tuple[DiffRegion, ...]
    heatmap_png: bytes | None = None

    @property
    def exact(self) -> bool:
        return self.threshold == 0 and self.dimensions_equal and self.mismatched_pixels == 0

    def to_dict(self, *, include_regions: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "dimensionsEqual": self.dimensions_equal,
            "referenceSize": [self.reference_width, self.reference_height],
            "renderedSize": [self.rendered_width, self.rendered_height],
            "mismatchedPixels": self.mismatched_pixels,
            "totalPixels": self.total_pixels,
            "mismatchPct": self.mismatch_pct,
            "meanAbsoluteError": self.mean_absolute_error,
            "maxChannelDelta": self.max_channel_delta,
            "threshold": self.threshold,
            "exact": self.exact,
            "mismatchBounds": list(self.mismatch_bounds) if self.mismatch_bounds else None,
        }
        if include_regions:
            result["regions"] = [region.to_dict() for region in self.regions]
        return result


_STABILITY_CSS = """
*, *::before, *::after {
  animation-delay: 0s !important;
  animation-duration: 0s !important;
  animation-iteration-count: 1 !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
  transition-delay: 0s !important;
  transition-duration: 0s !important;
}
html { scrollbar-width: none !important; }
::-webkit-scrollbar { display: none !important; }
"""


class _QuietStaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_: object) -> None:
        return


@contextmanager
def _serve_output(output_dir: Path):
    handler = partial(_QuietStaticHandler, directory=str(output_dir.resolve()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address[:2]
        host_text = host.decode("ascii") if isinstance(host, bytes) else host
        yield f"http://{host_text}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _decoded_pixel_hash(png: bytes) -> str:
    try:
        from PIL import Image

        with Image.open(io.BytesIO(png)) as image:
            decoded = image.convert("RGBA")
            payload = f"{decoded.width}x{decoded.height}:RGBA".encode() + decoded.tobytes()
    except (ImportError, OSError):
        payload = png
    return hashlib.sha256(payload).hexdigest()


async def _stabilize_page(page: Any) -> None:
    await page.add_style_tag(content=_STABILITY_CSS)
    await page.evaluate(
        """
        async () => {
          for (const image of document.images) image.loading = 'eager';
          if (document.fonts?.ready) await document.fonts.ready;
          const imagesReady = Promise.all(Array.from(document.images).map((image) => {
              if (image.complete) return image.decode?.().catch(() => undefined);
              return new Promise((resolve) => {
                image.addEventListener('load', resolve, { once: true });
                image.addEventListener('error', resolve, { once: true });
              });
            }));
          await Promise.race([
            imagesReady,
            new Promise((resolve) => setTimeout(resolve, 10000)),
          ]);
          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        }
        """
    )


async def _responsive_audit(page: Any) -> dict[str, Any]:
    return await page.evaluate(
        """
        () => {
          const viewportWidth = window.innerWidth;
          const documentWidth = Math.max(
            document.documentElement.scrollWidth,
            document.body?.scrollWidth || 0
          );
          const visible = (element, rect) => {
            const style = getComputedStyle(element);
            return style.display !== 'none' && style.visibility !== 'hidden' &&
              Number(style.opacity || 1) !== 0 && rect.width > 0 && rect.height > 0;
          };
          const label = (element) => {
            if (element.id) return `${element.tagName.toLowerCase()}#${element.id}`;
            const classes = Array.from(element.classList || []).slice(0, 3).join('.');
            return `${element.tagName.toLowerCase()}${classes ? `.${classes}` : ''}`;
          };
          const meaningful = (element) => {
            const semanticTags = new Set([
              'A', 'BUTTON', 'CANVAS', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
              'IFRAME', 'IMG', 'INPUT', 'LABEL', 'LI', 'P', 'PRE', 'SELECT',
              'SVG', 'TABLE', 'TEXTAREA', 'VIDEO'
            ]);
            if (semanticTags.has(element.tagName) || element.getAttribute('role')) return true;
            return Array.from(element.childNodes || []).some(
              (node) => node.nodeType === Node.TEXT_NODE && node.textContent.trim()
            );
          };
          const overflowElements = [];
          for (const element of document.body?.querySelectorAll('*') || []) {
            const rect = element.getBoundingClientRect();
            if (!visible(element, rect) || !meaningful(element)) continue;
            const leftOverflow = Math.max(0, -rect.left);
            const rightOverflow = Math.max(0, rect.right - viewportWidth);
            if (leftOverflow > 0.5 || rightOverflow > 0.5) {
              overflowElements.push({
                selector: label(element),
                left: Math.round(rect.left * 100) / 100,
                right: Math.round(rect.right * 100) / 100,
                width: Math.round(rect.width * 100) / 100,
                overflowPx: Math.round(Math.max(leftOverflow, rightOverflow) * 100) / 100,
              });
              if (overflowElements.length >= 20) break;
            }
          }
          const brokenImages = Array.from(document.images)
            .filter((image) => !image.complete || image.naturalWidth === 0)
            .map((image) => image.currentSrc || image.src || image.alt || '<unknown>')
            .slice(0, 20);
          // A fixed height plus overflow:hidden silently cuts content off. It
          // never trips an overflow check because the box itself does not grow.
          const clippedElements = [];
          for (const element of document.body?.querySelectorAll('*') || []) {
            const style = getComputedStyle(element);
            const hidesY = style.overflowY === 'hidden' || style.overflowY === 'clip';
            const hidesX = style.overflowX === 'hidden' || style.overflowX === 'clip';
            const hiddenY = hidesY ? element.scrollHeight - element.clientHeight : 0;
            const hiddenX = hidesX ? element.scrollWidth - element.clientWidth : 0;
            if (hiddenY > 1 || hiddenX > 1) {
              clippedElements.push({
                selector: label(element),
                hiddenPx: Math.round(Math.max(hiddenY, hiddenX)),
                boxHeight: element.clientHeight,
                contentHeight: element.scrollHeight,
              });
              if (clippedElements.length >= 20) break;
            }
          }
          // Distance from each hooked element's centre to the viewport centre.
          // Comparing this across widths separates a centred layout from one
          // pinned to fixed pixel offsets.
          const hookCentres = {};
          for (const element of document.querySelectorAll('[data-figma-id]')) {
            const id = element.getAttribute('data-figma-id');
            const rect = element.getBoundingClientRect();
            if (!id || rect.width <= 0 || hookCentres[id] !== undefined) continue;
            hookCentres[id] = Math.round((rect.left + rect.width / 2 - viewportWidth / 2) * 100) / 100;
          }
          return {
            viewportWidth,
            documentWidth,
            documentHeight: Math.max(
              document.documentElement.scrollHeight,
              document.body?.scrollHeight || 0
            ),
            horizontalOverflowPx: Math.max(0, documentWidth - viewportWidth),
            overflowElements,
            brokenImages,
            clippedElements,
            hookCentres,
            fontsReady: !document.fonts || document.fonts.status === 'loaded',
          };
        }
        """
    )


async def _render_capture(
    browser: Any,
    site_origin: str,
    *,
    width: float,
    height: float,
    scale: float,
    responsive_widths: tuple[int, ...],
    stability_runs: int,
    allowed_origins: tuple[str, ...],
) -> dict[str, Any]:
    viewport_width = max(1, round(width))
    viewport_height = max(1, round(height))
    if scale <= 0:
        raise ValueError(f"Capture scale must be positive, got {scale}")
    resource_errors: list[str] = []
    permitted_origins = {
        site_origin.lower(),
        *(origin.rstrip("/").lower() for origin in allowed_origins),
    }

    async def open_page(page_width: int, device_scale: float = 1) -> tuple[Any, Any]:
        context = await browser.new_context(
            viewport={"width": page_width, "height": viewport_height},
            device_scale_factor=device_scale,
            color_scheme="light",
            locale="en-US",
            timezone_id="UTC",
            reduced_motion="reduce",
        )

        async def restrict_request(route: Any, request: Any) -> None:
            parsed = urlsplit(request.url)
            origin = f"{parsed.scheme}://{parsed.netloc}".lower()
            safe_embedded = parsed.scheme in {"about", "blob", "data"}
            external_navigation = request.is_navigation_request() and origin != site_origin.lower()
            if (safe_embedded or origin in permitted_origins) and not external_navigation:
                await route.continue_()
                return
            resource_errors.append(f"Blocked non-allowlisted request: {request.url}")
            await route.abort("blockedbyclient")

        await context.route("**/*", restrict_request)
        page = await context.new_page()

        def record_http_error(response: Any) -> None:
            if response.status >= 400:
                resource_errors.append(
                    f"{response.request.method} {response.url}: "
                    f"HTTP {response.status} {response.status_text}"
                )

        page.on(
            "requestfailed",
            lambda request: resource_errors.append(
                f"{request.method} {request.url}: {request.failure or 'request failed'}"
            ),
        )
        page.on("response", record_http_error)
        await page.goto(
            f"{site_origin}/index.html",
            wait_until="networkidle",
            timeout=60_000,
        )
        await _stabilize_page(page)
        return context, page

    context, page = await open_page(viewport_width, scale)
    responsive = [await _responsive_audit(page)]
    # Read the laid-out boxes from the same page state that is about to be
    # photographed, so the geometry report and the pixels always agree.
    dom_geometry = await probe_dom_geometry(page)
    png = await page.screenshot(full_page=True, type="png", omit_background=True)
    pixel_hash = _decoded_pixel_hash(png)
    stable = True
    jpg = await page.screenshot(full_page=True, type="jpeg", quality=82)
    await context.close()

    for _ in range(max(1, stability_runs) - 1):
        repeated_context, repeated_page = await open_page(viewport_width, scale)
        repeated = await repeated_page.screenshot(
            full_page=True,
            type="png",
            omit_background=True,
        )
        stable = stable and _decoded_pixel_hash(repeated) == pixel_hash
        await repeated_context.close()

    audited = {viewport_width}
    for audit_width in responsive_widths:
        audit_width = max(1, round(audit_width))
        if audit_width in audited:
            continue
        audit_context, audit_page = await open_page(audit_width)
        responsive.append(await _responsive_audit(audit_page))
        audited.add(audit_width)
        await audit_context.close()

    return {
        "png": png,
        "jpg": jpg,
        "pixelHash": pixel_hash,
        "stable": stable,
        "responsive": sorted(responsive, key=lambda item: item["viewportWidth"]),
        "resourceErrors": resource_errors,
        "domGeometry": dom_geometry,
    }


async def render_generated_pages(
    output_dir: Path,
    *,
    captures: tuple[tuple[float, float, float], ...],
    responsive_widths: tuple[int, ...] = (),
    stability_runs: int = 1,
    allowed_origins: tuple[str, ...] = (),
) -> list[dict[str, Any] | None]:
    """Capture every exact viewport with one isolated server/browser evaluation."""
    if not captures:
        return []
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        log.warning("Playwright is not installed; skipping browser render and pixel diff")
        return [None] * len(captures)

    try:
        with _serve_output(output_dir) as site_origin:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                try:
                    results: list[dict[str, Any] | None] = []
                    for index, (width, height, scale) in enumerate(captures):
                        try:
                            results.append(
                                await _render_capture(
                                    browser,
                                    site_origin,
                                    width=width,
                                    height=height,
                                    scale=scale,
                                    responsive_widths=responsive_widths if index == 0 else (),
                                    stability_runs=stability_runs,
                                    allowed_origins=allowed_origins,
                                )
                            )
                        except Exception as exc:
                            log.warning("Browser capture %s failed (%s)", index + 1, exc)
                            results.append(None)
                    return results
                finally:
                    await browser.close()
    except Exception as exc:
        log.warning("Browser render failed (%s)", exc)
        return [None] * len(captures)


async def render_generated_page(
    output_dir: Path,
    *,
    width: float = 1440,
    height: float = 900,
    scale: float = 1,
    responsive_widths: tuple[int, ...] = (),
    stability_runs: int = 1,
    allowed_origins: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    """Compatibility wrapper for callers that need one capture."""
    rendered = await render_generated_pages(
        output_dir,
        captures=((width, height, scale),),
        responsive_widths=responsive_widths,
        stability_runs=stability_runs,
        allowed_origins=allowed_origins,
    )
    return rendered[0]


def analyze_visual_diff(
    figma_png: bytes,
    render_png: bytes,
    *,
    threshold: int = 31,
    tile_size: int = 160,
    max_regions: int = 12,
    output_dir: Path | None = None,
) -> VisualDiffResult | None:
    """Compare decoded pixels without resizing or silently discarding extra canvas area."""
    try:
        from PIL import Image, ImageChops, ImageDraw
    except ImportError:
        log.warning("Pillow is not installed; skipping pixel diff")
        return None

    try:
        reference = Image.open(io.BytesIO(figma_png)).convert("RGBA")
        rendered = Image.open(io.BytesIO(render_png)).convert("RGBA")
        width = max(reference.width, rendered.width)
        height = max(reference.height, rendered.height)
        total_pixels = width * height
        if total_pixels == 0:
            return None

        reference_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        rendered_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        reference_canvas.paste(reference, (0, 0))
        rendered_canvas.paste(rendered, (0, 0))
        difference = ImageChops.difference(reference_canvas, rendered_canvas)
        red, green, blue, alpha = difference.split()
        maximum = ImageChops.lighter(ImageChops.lighter(ImageChops.lighter(red, green), blue), alpha)
        mask = maximum.point(lambda value: 255 if value > threshold else 0)

        if reference.size != rendered.size:
            reference_extent = Image.new("1", (width, height), 0)
            rendered_extent = Image.new("1", (width, height), 0)
            ImageDraw.Draw(reference_extent).rectangle(
                (0, 0, reference.width - 1, reference.height - 1), fill=1
            )
            ImageDraw.Draw(rendered_extent).rectangle(
                (0, 0, rendered.width - 1, rendered.height - 1), fill=1
            )
            extent_difference = ImageChops.logical_xor(reference_extent, rendered_extent).convert("L")
            mask = ImageChops.lighter(mask, extent_difference)
            maximum = ImageChops.lighter(maximum, extent_difference)

        mismatched = mask.histogram()[255]
        maximum_histogram = maximum.histogram()
        absolute_error = sum(value * count for value, count in enumerate(maximum_histogram))
        max_delta = next((value for value in range(255, -1, -1) if maximum_histogram[value]), 0)

        regions: list[DiffRegion] = []
        tile_size = max(8, tile_size)
        for y in range(0, height, tile_size):
            for x in range(0, width, tile_size):
                right = min(width, x + tile_size)
                bottom = min(height, y + tile_size)
                tile_mask = mask.crop((x, y, right, bottom))
                tile_mismatched = tile_mask.histogram()[255]
                if not tile_mismatched:
                    continue
                tile_histogram = maximum.crop((x, y, right, bottom)).histogram()
                tile_max = next(
                    (value for value in range(255, -1, -1) if tile_histogram[value]),
                    0,
                )
                tile_pixels = (right - x) * (bottom - y)
                regions.append(
                    DiffRegion(
                        x=x,
                        y=y,
                        width=right - x,
                        height=bottom - y,
                        mismatched_pixels=tile_mismatched,
                        mismatch_pct=tile_mismatched / tile_pixels * 100,
                        max_channel_delta=tile_max,
                    )
                )
        regions.sort(key=lambda region: (region.mismatched_pixels, region.max_channel_delta), reverse=True)

        heatmap = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        heatmap.paste((255, 20, 80, 230), mask=mask)
        buffer = io.BytesIO()
        heatmap.save(buffer, format="PNG")
        diff_bytes = buffer.getvalue()
        if output_dir:
            write_file(output_dir / "reference" / "pixel-diff.png", diff_bytes)

        return VisualDiffResult(
            dimensions_equal=reference.size == rendered.size,
            reference_width=reference.width,
            reference_height=reference.height,
            rendered_width=rendered.width,
            rendered_height=rendered.height,
            mismatched_pixels=mismatched,
            total_pixels=total_pixels,
            mismatch_pct=mismatched / total_pixels * 100,
            mean_absolute_error=absolute_error / total_pixels,
            max_channel_delta=max_delta,
            threshold=threshold,
            mismatch_bounds=mask.getbbox(),
            regions=tuple(regions[:max_regions]),
            heatmap_png=diff_bytes,
        )
    except Exception as exc:
        log.warning("Pixel diff failed (%s)", exc)
        return None


def pixel_mismatch(
    figma_png: bytes,
    render_png: bytes,
    output_dir: Path | None = None,
    *,
    threshold: int = 31,
) -> tuple[float, bytes | None] | None:
    """Backward-compatible wrapper around the richer visual analysis."""
    result = analyze_visual_diff(
        figma_png,
        render_png,
        threshold=threshold,
        output_dir=output_dir,
    )
    if result is None:
        return None
    return result.mismatch_pct, result.heatmap_png
