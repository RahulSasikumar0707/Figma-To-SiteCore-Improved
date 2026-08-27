from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from figma_to_sitecore.config import Settings, normalize_node_id


def test_normalize_node_id() -> None:
    assert normalize_node_id(" 68569-2790 ") == "68569:2790"


def test_settings_validate_required_conversion_values(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        anthropic_api_key_1=SecretStr(""),
        figma_token=SecretStr(""),
        figma_file_key="",
        figma_node_id="",
    )
    assert len(settings.validate_for_run()) == 4
    assert settings.validate_for_run(manifest_only=True) == []


def test_reviewer_key_falls_back_to_generator(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        anthropic_api_key_1=SecretStr("generator"),
    )
    assert settings.reviewer_key == "generator"


def test_dotenv_overrides_stale_os_environment(monkeypatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FIGMA_TOKEN=fresh-project-token\n", encoding="utf-8")
    monkeypatch.setenv("FIGMA_TOKEN", "expired-windows-token")

    settings = Settings(_env_file=env_file, project_root=tmp_path)

    assert settings.figma_access_token == "fresh-project-token"


def test_strict_accuracy_uses_exact_pixels_and_parses_viewports(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="strict",
        pixel_diff_threshold=31,
        responsive_viewports="1440, 375,768",
        figma_reference_nodes={"375": "12-34", "1440": "56:78"},
    )

    assert settings.strict_accuracy
    assert settings.effective_pixel_diff_threshold == 0
    assert settings.responsive_widths == (375, 768, 1440)
    assert settings.reference_nodes == {375: "12:34", 1440: "56:78"}


@pytest.mark.parametrize("value", ["1440,invalid,375", "1440,,375", "1440,319"])
def test_responsive_viewports_fail_closed(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, project_root=tmp_path, responsive_viewports=value)


def test_strict_accuracy_rejects_unverifiable_cli_modes(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        project_root=tmp_path,
        accuracy_mode="strict",
        visual_diff=False,
    )

    errors = settings.validate_for_run(skip_review=True)

    assert "ACCURACY_MODE=strict requires VISUAL_DIFF=true." in errors
    assert "ACCURACY_MODE=strict cannot be combined with --skip-review." in errors


def test_reference_nodes_load_from_dotenv_json(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text('FIGMA_REFERENCE_NODES={"375":"12-34","1440":"56:78"}\n', encoding="utf-8")

    settings = Settings(_env_file=env_file, project_root=tmp_path)

    assert settings.reference_nodes == {375: "12:34", 1440: "56:78"}


def test_model_budget_and_effort_defaults_suit_current_claude_models() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_max_tokens == 64_000
    assert settings.llm_reviewer_max_tokens == 32_000
    assert settings.llm_reasoning_effort == "xhigh"
    assert settings.geometry_tolerance_px == 2.0
    assert settings.wide_audit_ratio == 1.4


def test_output_token_ceiling_is_rejected_above_the_api_maximum() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_max_tokens=200_000)
