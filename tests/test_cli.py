from pathlib import Path

import pytest

from figma_to_sitecore.cli import _run, build_parser


def test_cli_accepts_strict_accuracy_and_responsive_references() -> None:
    args = build_parser().parse_args(
        [
            "--accuracy",
            "strict",
            "--pixel-target",
            "0",
            "--reference",
            "375=12:34",
            "--reference",
            "1440=56:78",
        ]
    )

    assert args.accuracy == "strict"
    assert args.pixel_target == 0
    assert args.reference == ["375=12:34", "1440=56:78"]


@pytest.mark.asyncio
async def test_cli_rejects_subminimum_reference_width(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args(["--reference", "319=12:34"])

    assert await _run(args) == 2
