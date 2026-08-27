from pathlib import Path

import pytest

from figma_to_sitecore.application import ConversionApplication

pytest.importorskip("PIL")
pytest.importorskip("playwright.async_api")


class FailingChromium:
    async def launch(self, *, headless: bool):
        raise OSError("browser executable is unavailable")


class FakePlaywright:
    chromium = FailingChromium()


class FakePlaywrightManager:
    async def __aenter__(self):
        return FakePlaywright()

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.asyncio
async def test_strict_preflight_rejects_unlaunchable_chromium(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "playwright.async_api.async_playwright",
        lambda: FakePlaywrightManager(),
    )

    with pytest.raises(RuntimeError, match="playwright install chromium"):
        await ConversionApplication._validate_strict_runtime(
            skip_review=False,
            visual_diff=True,
        )
