from pathlib import Path

import pytest

from figma_to_sitecore.figma.assets import download_reference_screenshot


class PreviewFailingRestClient:
    def __init__(self, png: bytes) -> None:
        self.png = png

    async def render_images(self, file_key, node_ids, *, image_format, scale):
        if image_format == "jpg":
            raise RuntimeError("preview export failed")
        return {node_ids[0]: "https://example.test/reference.png"}

    async def download(self, url: str) -> bytes:
        return self.png


class PreviewDownloadFailingRestClient(PreviewFailingRestClient):
    async def render_images(self, file_key, node_ids, *, image_format, scale):
        return {node_ids[0]: f"https://example.test/reference.{image_format}"}

    async def download(self, url: str) -> bytes:
        if url.endswith(".jpg"):
            raise RuntimeError("preview download failed")
        return self.png


@pytest.mark.asyncio
async def test_optional_jpg_failure_preserves_required_png(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 8) + (375).to_bytes(4, "big") + (800).to_bytes(4, "big")
    result = await download_reference_screenshot(
        PreviewFailingRestClient(png),
        "file",
        "1:2",
        {"w": 375, "h": 800},
        tmp_path,
    )

    assert result["png"] == png
    assert result["jpg"] is None
    assert result["pngSize"] == [375, 800]
    assert result["renderScale"] == 1
    assert (tmp_path / "reference" / "figma-design.png").read_bytes() == png


@pytest.mark.asyncio
async def test_optional_jpg_download_failure_preserves_required_png(tmp_path: Path) -> None:
    png = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 8) + (1440).to_bytes(4, "big") + (900).to_bytes(4, "big")
    result = await download_reference_screenshot(
        PreviewDownloadFailingRestClient(png),
        "file",
        "3:4",
        {"w": 1440, "h": 900},
        tmp_path,
    )

    assert result["png"] == png
    assert result["jpg"] is None
    assert result["pngSize"] == [1440, 900]
