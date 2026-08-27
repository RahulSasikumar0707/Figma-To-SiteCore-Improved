from __future__ import annotations

import hashlib
import struct
from pathlib import Path
from typing import Any

from figma_to_sitecore.figma.client import FigmaRestClient
from figma_to_sitecore.utils.files import safe_file_name, write_file
from figma_to_sitecore.utils.logging import log


async def download_assets(
    rest: FigmaRestClient,
    file_key: str,
    assets: list[dict[str, Any]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    if not assets:
        return []
    taken: set[str] = set()
    manifest: list[dict[str, Any]] = []
    node_to_file: dict[str, str] = {}
    ref_to_file: dict[str, str] = {}
    hash_to_file: dict[str, str] = {}

    def store(asset: dict[str, Any], data: bytes, relative_file: str) -> str:
        digest = hashlib.sha256(data).hexdigest()
        file_name = hash_to_file.get(digest)
        if not file_name:
            file_name = relative_file
            write_file(output_dir / file_name, data)
            hash_to_file[digest] = file_name
        node_to_file[asset["nodeId"]] = file_name
        if asset.get("imageRef"):
            ref_to_file[asset["imageRef"]] = file_name
        manifest.append({**asset, "file": file_name})
        return file_name

    image_refs = [asset for asset in assets if asset["export"] == "imageRef" and asset.get("imageRef")]
    svg_assets = [asset for asset in assets if asset["export"] == "svg"]
    png_assets = [
        asset for asset in assets if asset["export"] == "png" or (asset["export"] == "imageRef" and not asset.get("imageRef"))
    ]

    fill_urls: dict[str, str] = {}
    if image_refs:
        try:
            fill_urls = await rest.get_image_fills(file_key)
        except Exception as exc:
            log.warning("Original image fills unavailable (%s); using PNG renders", exc)
            png_assets.extend(image_refs)
            image_refs = []

    for asset in image_refs:
        existing = ref_to_file.get(asset["imageRef"])
        if existing:
            node_to_file[asset["nodeId"]] = existing
            manifest.append({**asset, "file": existing})
            continue
        url = fill_urls.get(asset["imageRef"])
        if not url:
            png_assets.append(asset)
            continue
        try:
            data = await rest.download(url)
            extension = sniff_extension(data, "png")
            name = safe_file_name(asset.get("name"), extension, taken)
            store(asset, data, f"assets/images/{name}")
        except Exception as exc:
            log.warning("Image fill export failed for %s (%s)", asset.get("name"), exc)
            png_assets.append(asset)

    svg_pending = [asset for asset in svg_assets if asset["nodeId"] not in node_to_file]
    svg_urls: dict[str, str | None] = {}
    if svg_pending:
        try:
            svg_urls = await rest.render_images(
                file_key, [asset["nodeId"] for asset in svg_pending], image_format="svg"
            )
        except Exception as exc:
            log.warning("SVG export batch failed (%s); using PNG renders", exc)
    for asset in svg_pending:
        url = svg_urls.get(asset["nodeId"])
        if not url:
            png_assets.append(asset)
            continue
        try:
            data = await rest.download(url)
            subfolder = "icons" if asset["kind"] == "icon" else "vectors"
            name = safe_file_name(asset.get("name"), "svg", taken)
            store(asset, data, f"assets/{subfolder}/{name}")
        except Exception as exc:
            log.warning("SVG export failed for %s (%s)", asset.get("name"), exc)
            png_assets.append(asset)

    png_pending = [asset for asset in png_assets if asset["nodeId"] not in node_to_file]
    png_urls: dict[str, str | None] = {}
    if png_pending:
        try:
            png_urls = await rest.render_images(
                file_key, [asset["nodeId"] for asset in png_pending], image_format="png", scale=2
            )
        except Exception as exc:
            log.warning("PNG export batch failed (%s)", exc)
    for asset in png_pending:
        url = png_urls.get(asset["nodeId"])
        if not url:
            log.warning("Figma could not render %s (%s)", asset.get("name"), asset["nodeId"])
            continue
        try:
            data = await rest.download(url)
            name = safe_file_name(asset.get("name"), "png", taken)
            store(asset, data, f"assets/images/{name}")
        except Exception as exc:
            log.warning("PNG export failed for %s (%s)", asset.get("name"), exc)

    log.info("Downloaded %s/%s assets into %s", len(manifest), len(assets), output_dir / "assets")
    return manifest


async def download_reference_screenshot(
    rest: FigmaRestClient,
    file_key: str,
    node_id: str,
    node_size: dict[str, float] | None,
    output_dir: Path,
    *,
    relative_path: str = "reference/figma-design.png",
) -> dict[str, Any]:
    maximum_side = max((node_size or {}).get("w", 1440), (node_size or {}).get("h", 1440))
    png_scale = min(1, 3800 / maximum_side)
    jpg_scale = min(1, 2800 / maximum_side)
    # PNG is the required, lossless comparison evidence. Fetch it first so an
    # optional JPG preview failure can never discard a valid strict reference.
    png_urls = await rest.render_images(
        file_key, [node_id], image_format="png", scale=png_scale
    )
    png_url = png_urls.get(node_id)
    png = await rest.download(png_url) if png_url else None
    jpg = None
    try:
        jpg_urls = await rest.render_images(
            file_key, [node_id], image_format="jpg", scale=jpg_scale
        )
        jpg_url = jpg_urls.get(node_id)
        jpg = await rest.download(jpg_url) if jpg_url else None
    except Exception as exc:
        log.warning("Optional JPG reference preview unavailable for %s (%s)", node_id, exc)
    if png:
        write_file(output_dir / relative_path, png)
    png_size = png_dimensions(png) if png else None
    render_scale = (
        png_size[0] / float((node_size or {}).get("w", png_size[0]))
        if png_size
        else png_scale
    )
    return {
        "png": png,
        "jpg": jpg,
        "pngScale": png_scale,
        "renderScale": render_scale,
        "pngSize": list(png_size) if png_size else None,
    }


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    return struct.unpack(">II", data[16:24])


def sniff_extension(data: bytes, default: str) -> str:
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data.startswith(b"\x89PNG"):
        return "png"
    if len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp"
    if data.startswith((b"<?xml", b"<svg")):
        return "svg"
    if data.startswith(b"GIF8"):
        return "gif"
    return default
