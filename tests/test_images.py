import io
import os

import pytest

from figma_to_sitecore.domain.models import ImagePayload
from figma_to_sitecore.utils.images import fit_image_payload

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


def _noise_png(side: int) -> bytes:
    image = Image.frombytes("RGB", (side, side), os.urandom(side * side * 3))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_small_image_passes_through_unchanged() -> None:
    payload = ImagePayload(_noise_png(32), "image/png")

    assert fit_image_payload(payload) is payload


def test_none_passes_through() -> None:
    assert fit_image_payload(None) is None


def test_oversized_image_is_reencoded_under_the_limit() -> None:
    payload = ImagePayload(_noise_png(600), "image/png")
    limit = 200_000
    assert len(payload.data) > limit

    fitted = fit_image_payload(payload, max_bytes=limit)

    assert fitted is not None
    assert len(fitted.data) <= limit
    assert fitted.media_type == "image/jpeg"
    with Image.open(io.BytesIO(fitted.data)) as decoded:
        assert decoded.format == "JPEG"


def test_oversized_undecodable_image_is_omitted_not_sent() -> None:
    payload = ImagePayload(os.urandom(300_000), "image/png")

    assert fit_image_payload(payload, max_bytes=100_000) is None
