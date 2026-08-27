from __future__ import annotations

import io

from figma_to_sitecore.domain.models import ImagePayload
from figma_to_sitecore.utils.logging import log

# Anthropic rejects any single image above 5MB; stay comfortably below it.
MAX_IMAGE_BYTES = 4_500_000
# It also rejects any side above 8000px. Figma REST exports are scaled lower,
# but MCP screenshots and PNG fallbacks are not guaranteed to be.
MAX_IMAGE_SIDE = 7_900


def fit_image_payload(
    image: ImagePayload | None,
    *,
    max_bytes: int = MAX_IMAGE_BYTES,
    label: str = "design preview",
) -> ImagePayload | None:
    """Ensure a model-bound preview fits the API image limits.

    Oversized payloads are composited onto white and re-encoded as JPEG,
    shrinking until they fit. Only previews sent to the LLM pass through here —
    never the lossless comparison PNGs — so the re-encode cannot affect the
    pixel diff. Returns ``None`` when the image cannot be made to fit: a missing
    preview degrades one prompt, an HTTP 400 aborts the whole conversion.
    """
    if image is None:
        return None
    oversized = len(image.data) > max_bytes
    try:
        from PIL import Image
    except ImportError:
        if oversized:
            log.warning(
                "%s is %.1fMB, above the model image limit, and Pillow is unavailable "
                "to re-encode it; omitting the image",
                label,
                len(image.data) / 1_000_000,
            )
            return None
        return image
    try:
        with Image.open(io.BytesIO(image.data)) as decoded:
            if not oversized and max(decoded.size) <= MAX_IMAGE_SIDE:
                return image
            frame = decoded.convert("RGBA")
    except Exception as exc:
        if oversized:
            log.warning("%s could not be decoded for re-encoding (%s); omitting the image", label, exc)
            return None
        return image

    background = Image.new("RGB", frame.size, (255, 255, 255))
    background.paste(frame, mask=frame.split()[-1])
    frame = background
    if max(frame.size) > MAX_IMAGE_SIDE:
        ratio = MAX_IMAGE_SIDE / max(frame.size)
        frame = frame.resize((max(1, round(frame.width * ratio)), max(1, round(frame.height * ratio))))
    quality = 85
    while True:
        buffer = io.BytesIO()
        frame.save(buffer, format="JPEG", quality=quality)
        data = buffer.getvalue()
        if len(data) <= max_bytes:
            log.info(
                "%s re-encoded from %.1fMB to %.1fMB (%sx%s JPEG q%s) to fit the model image limit",
                label,
                len(image.data) / 1_000_000,
                len(data) / 1_000_000,
                frame.width,
                frame.height,
                quality,
            )
            return ImagePayload(data, "image/jpeg")
        if quality > 50:
            quality -= 15
            continue
        if max(frame.size) <= 512:
            log.warning("%s could not be reduced below the model image limit; omitting the image", label)
            return None
        frame = frame.resize((max(1, round(frame.width * 0.7)), max(1, round(frame.height * 0.7))))
        quality = 85
