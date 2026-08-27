from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import PydanticBaseSettingsSource


def normalize_node_id(value: str | None) -> str:
    """Normalize URL-style Figma node ids (12-34) to API form (12:34)."""
    return str(value or "").strip().replace("-", ":")


class Settings(BaseSettings):
    """Environment-backed application settings.

    Paths are resolved against ``project_root`` once settings are loaded. CLI
    values are passed as explicit constructor inputs and therefore take precedence.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """Make the project's .env authoritative over stale OS variables.

        Explicit constructor/CLI values remain highest priority. This mirrors
        the previous Node application, which loaded dotenv with override=true.
        """
        return init_settings, dotenv_settings, env_settings, file_secret_settings

    anthropic_api_key_1: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("ANTHROPIC_API_KEY_1", "ANTHROPIC_API_KEY"),
    )
    anthropic_api_key_2: SecretStr = SecretStr("")
    anthropic_model: str = "claude-sonnet-4-6"
    # Claude 4.6+ models accept up to 128K output tokens when streaming. A full
    # page plus its stylesheet routinely exceeds 32K, and every truncation costs
    # a continuation round trip that can drop or duplicate markup.
    llm_max_tokens: int = Field(default=64_000, ge=1, le=128_000)
    # The reviewer's ceiling covers adaptive thinking as well as the verdict, and
    # unlike the generator it has no resume path: a truncated verdict fails the
    # structured parse and ends the loop. The ceiling is only a cap, not a target.
    llm_reviewer_max_tokens: int = Field(default=32_000, ge=1, le=128_000)
    # output_config.effort on adaptive-thinking models. Pixel-accurate conversion
    # is intelligence-sensitive, so this defaults above the API default of "high".
    llm_reasoning_effort: Literal["low", "medium", "high", "xhigh", "max"] | None = "xhigh"

    figma_token: SecretStr = SecretStr("")
    figma_file_key: str = ""
    figma_node_id: str = ""
    figma_reference_nodes: dict[str, str] = Field(default_factory=dict)
    figma_mcp_url: str = "http://127.0.0.1:3845/mcp"
    figma_source: Literal["auto", "mcp", "rest"] = "auto"

    eds_manifest_path: Path = Path("eds-manifest.json")
    eds_storybook_base: str = "https://affinitycmpd103.gilead.com"
    # Storybook lives behind the corporate network. Off-network every request answers
    # HTTP 403, so snippets are only re-fetched when a run explicitly asks for it; the
    # curated manifest is the default source of component grounding.
    eds_storybook_refresh: bool = False
    eds_native_css_path: Path | None = None
    bootstrap_css_url: str = "https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css"
    bootstrap_js_url: str = "https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"

    match_threshold: float = Field(default=95, gt=0, le=100)
    review_target_issues: int = Field(default=0, ge=0)
    max_review_iterations: int = Field(default=8, ge=1)
    visual_diff: bool = True
    accuracy_mode: Literal["standard", "strict"] = "standard"
    pixel_mismatch_target: float = Field(default=0, ge=0, le=100)
    pixel_diff_threshold: int = Field(default=31, ge=0, le=255)
    pixel_diff_tile_size: int = Field(default=160, ge=8, le=1024)
    accuracy_patience: int = Field(default=2, ge=1)
    min_pixel_improvement: float = Field(default=0.01, ge=0, le=100)
    responsive_viewports: str = "375,768,1440"
    # Per-node CSS-pixel tolerance for the deterministic DOM/Figma geometry audit.
    geometry_tolerance_px: float = Field(default=2.0, ge=0, le=64)
    # A width above the design width is always audited, as a multiple of it, so a
    # layout pinned to the design's pixel offsets cannot pass unnoticed.
    wide_audit_ratio: float = Field(default=1.4, ge=1.05, le=4)
    render_allowed_origins: str = (
        "https://cdn.jsdelivr.net,https://fonts.googleapis.com,https://fonts.gstatic.com"
    )

    output_prefix: str = "Output"
    output_root: Path = Path(".")
    project_root: Path = Field(default_factory=Path.cwd, exclude=True)

    @property
    def generator_key(self) -> str:
        return self.anthropic_api_key_1.get_secret_value()

    @property
    def reviewer_key(self) -> str:
        return self.anthropic_api_key_2.get_secret_value() or self.generator_key

    @field_validator("figma_reference_nodes")
    @classmethod
    def validate_reference_nodes(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_width, raw_node_id in value.items():
            try:
                width = int(raw_width)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid Figma reference width: {raw_width!r}") from exc
            if width < 320:
                raise ValueError(f"Figma reference width must be at least 320px: {width}")
            node_id = normalize_node_id(raw_node_id)
            if not node_id:
                raise ValueError(f"Figma reference node is empty for width {width}")
            normalized[str(width)] = node_id
        return normalized

    @field_validator("responsive_viewports")
    @classmethod
    def validate_responsive_viewports(cls, value: str) -> str:
        """Reject malformed audit widths instead of silently weakening coverage."""
        normalized: list[str] = []
        for raw_width in value.split(","):
            token = raw_width.strip()
            if not token:
                raise ValueError("Responsive viewport widths cannot be empty")
            try:
                width = int(token)
            except ValueError as exc:
                raise ValueError(f"Invalid responsive viewport width: {token!r}") from exc
            if width < 320:
                raise ValueError(f"Responsive viewport width must be at least 320px: {width}")
            normalized.append(str(width))
        return ",".join(normalized)

    @property
    def figma_access_token(self) -> str:
        return self.figma_token.get_secret_value()

    @property
    def node_id(self) -> str:
        return normalize_node_id(self.figma_node_id)

    @property
    def reference_nodes(self) -> dict[int, str]:
        return {
            int(width): normalize_node_id(node_id)
            for width, node_id in self.figma_reference_nodes.items()
        }

    @property
    def manifest_path(self) -> Path:
        return self._resolve(self.eds_manifest_path)

    @property
    def resolved_output_root(self) -> Path:
        return self._resolve(self.output_root)

    @property
    def native_css_path(self) -> Path | None:
        return self._resolve(self.eds_native_css_path) if self.eds_native_css_path else None

    @property
    def strict_accuracy(self) -> bool:
        return self.accuracy_mode == "strict"

    @property
    def effective_pixel_diff_threshold(self) -> int:
        # Strict means decoded-pixel equality; tolerant thresholds are diagnostic only.
        return 0 if self.strict_accuracy else self.pixel_diff_threshold

    @property
    def responsive_widths(self) -> tuple[int, ...]:
        return tuple(sorted({int(value) for value in self.responsive_viewports.split(",")}))

    @property
    def allowed_render_origins(self) -> tuple[str, ...]:
        origins: set[str] = set()
        for value in self.render_allowed_origins.split(","):
            parsed = urlsplit(value.strip())
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                origins.add(f"{parsed.scheme}://{parsed.netloc}".lower())
        return tuple(sorted(origins))

    def _resolve(self, value: Path) -> Path:
        return value.resolve() if value.is_absolute() else (self.project_root / value).resolve()

    def validate_for_run(
        self,
        *,
        manifest_only: bool = False,
        skip_review: bool = False,
    ) -> list[str]:
        errors: list[str] = []
        if manifest_only:
            return errors
        if not self.generator_key:
            errors.append("ANTHROPIC_API_KEY_1 (or ANTHROPIC_API_KEY) is required.")
        if not self.figma_file_key:
            errors.append("FIGMA_FILE_KEY is required (or pass --file-key).")
        if not self.node_id:
            errors.append("FIGMA_NODE_ID is required (or pass --node).")
        # REST is always needed for the structured node tree and asset exports.
        if not self.figma_access_token:
            errors.append("FIGMA_TOKEN is required for the node tree and asset exports.")
        if self.strict_accuracy and not self.visual_diff:
            errors.append("ACCURACY_MODE=strict requires VISUAL_DIFF=true.")
        if self.strict_accuracy and skip_review:
            errors.append("ACCURACY_MODE=strict cannot be combined with --skip-review.")
        if self.strict_accuracy and not self.responsive_widths:
            errors.append("RESPONSIVE_VIEWPORTS must contain at least one integer width in strict mode.")
        return errors
