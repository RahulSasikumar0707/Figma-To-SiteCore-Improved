import io
from pathlib import Path

import pytest

from figma_to_sitecore.review.visual import analyze_visual_diff, pixel_mismatch

PIL = pytest.importorskip("PIL.Image")


def _png(color: str, size: tuple[int, int] = (4, 4)) -> bytes:
    image = PIL.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_pixel_mismatch_creates_heatmap(tmp_path: Path) -> None:
    result = pixel_mismatch(_png("black"), _png("white"), tmp_path)
    assert result is not None
    mismatch, heatmap = result
    assert mismatch == 100
    assert heatmap
    assert (tmp_path / "reference" / "pixel-diff.png").is_file()


def test_exact_diff_detects_a_single_channel_delta() -> None:
    reference = PIL.new("RGB", (4, 4), (10, 20, 30))
    rendered = reference.copy()
    rendered.putpixel((2, 1), (11, 20, 30))
    reference_buffer = io.BytesIO()
    rendered_buffer = io.BytesIO()
    reference.save(reference_buffer, format="PNG")
    rendered.save(rendered_buffer, format="PNG")

    exact = analyze_visual_diff(reference_buffer.getvalue(), rendered_buffer.getvalue(), threshold=0)
    tolerant = analyze_visual_diff(reference_buffer.getvalue(), rendered_buffer.getvalue(), threshold=1)

    assert exact is not None and tolerant is not None
    assert exact.mismatched_pixels == 1
    assert exact.mismatch_pct == pytest.approx(6.25)
    assert not exact.exact
    assert tolerant.mismatched_pixels == 0


def test_exact_diff_cannot_hide_canvas_size_mismatch() -> None:
    result = analyze_visual_diff(_png("white", (4, 4)), _png("white", (5, 4)), threshold=0)

    assert result is not None
    assert not result.dimensions_equal
    assert result.mismatched_pixels == 4
    assert result.mismatch_pct == pytest.approx(20)
    assert not result.exact


def test_exact_diff_reports_zero_only_for_equal_decoded_pixels() -> None:
    image = _png("#123456")
    result = analyze_visual_diff(image, image, threshold=0)

    assert result is not None
    assert result.exact
    assert result.mismatched_pixels == 0
    assert result.mismatch_pct == 0


def test_exact_diff_includes_alpha_channel() -> None:
    transparent = PIL.new("RGBA", (1, 1), (10, 20, 30, 0))
    opaque = PIL.new("RGBA", (1, 1), (10, 20, 30, 255))
    transparent_buffer = io.BytesIO()
    opaque_buffer = io.BytesIO()
    transparent.save(transparent_buffer, format="PNG")
    opaque.save(opaque_buffer, format="PNG")

    result = analyze_visual_diff(
        transparent_buffer.getvalue(),
        opaque_buffer.getvalue(),
        threshold=0,
    )

    assert result is not None
    assert result.mismatched_pixels == 1
    assert not result.exact
