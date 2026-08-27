import json
from pathlib import Path
from typing import Any

import pytest

from figma_to_sitecore.application import ConversionApplication, StorybookUnavailable
from figma_to_sitecore.config import Settings
from figma_to_sitecore.eds.manifest import load_eds_manifest

STORYBOOK_BASE = "https://storybook.example.com"

CURATED = {
    "components": [
        {"name": "accordion", "folder": "accordion", "edsClasses": ["eds-accordion"], "snippet": "<div>"}
    ]
}


def write_manifest(path: Path, document: dict[str, Any]) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_curated_manifest_is_used_without_scanning_storybook(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = write_manifest(tmp_path / "eds-manifest.json", CURATED)

    async def unreachable_scan(base: str) -> list[dict[str, Any]]:
        raise AssertionError("Storybook must not be scanned when the manifest is usable")

    monkeypatch.setattr("figma_to_sitecore.eds.manifest.scan_storybook_components", unreachable_scan)

    components, curated = await load_eds_manifest(manifest, STORYBOOK_BASE)

    assert curated is True
    assert [component["name"] for component in components] == ["accordion"]


@pytest.mark.asyncio
async def test_missing_manifest_falls_back_to_storybook_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scanned: list[str] = []

    async def fake_scan(base: str) -> list[dict[str, Any]]:
        scanned.append(base)
        return [{"name": "card", "folder": "card"}]

    monkeypatch.setattr("figma_to_sitecore.eds.manifest.scan_storybook_components", fake_scan)

    components, curated = await load_eds_manifest(tmp_path / "absent.json", STORYBOOK_BASE)

    assert curated is False
    assert scanned == [STORYBOOK_BASE]
    assert [component["name"] for component in components] == ["card"]


@pytest.mark.asyncio
async def test_unreadable_manifest_falls_back_to_storybook_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "eds-manifest.json"
    manifest.write_text("{ not json", encoding="utf-8")

    async def fake_scan(base: str) -> list[dict[str, Any]]:
        return [{"name": "card", "folder": "card"}]

    monkeypatch.setattr("figma_to_sitecore.eds.manifest.scan_storybook_components", fake_scan)

    _, curated = await load_eds_manifest(manifest, STORYBOOK_BASE)

    assert curated is False


@pytest.mark.asyncio
async def test_rebuild_manifest_keeps_curated_file_when_storybook_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = write_manifest(tmp_path / "eds-manifest.json", CURATED)
    original = manifest.read_text(encoding="utf-8")

    async def blocked_scan(base: str) -> list[dict[str, Any]]:
        # What an off-network HTTP 403 sweep produces: one empty shell per component.
        return [{"name": "accordion", "folder": "accordion", "edsClasses": [], "snippet": ""}]

    monkeypatch.setattr("figma_to_sitecore.application.scan_storybook_components", blocked_scan)
    application = ConversionApplication(Settings(_env_file=None, project_root=tmp_path))

    with pytest.raises(StorybookUnavailable):
        await application.rebuild_manifest()

    assert manifest.read_text(encoding="utf-8") == original
