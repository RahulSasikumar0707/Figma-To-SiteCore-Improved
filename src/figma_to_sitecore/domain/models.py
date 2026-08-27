from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, field_validator


@dataclass(frozen=True, slots=True)
class ImagePayload:
    data: bytes
    media_type: str = "image/png"


@dataclass(frozen=True, slots=True)
class ViewportReference:
    name: str
    node_id: str
    width: float
    height: float
    scale: float
    png: bytes
    preview: ImagePayload | None = None


class ReviewIssue(BaseModel):
    severity: Literal["critical", "major", "minor"]
    area: str
    description: str
    fix: str


class ReviewVerdict(BaseModel):
    score: float = Field(ge=0, le=100)
    summary: str
    issues: list[ReviewIssue] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def normalize_score(cls, value: Any) -> float:
        return max(0.0, min(100.0, float(value or 0)))


@dataclass(slots=True)
class GenerationContext:
    design_name: str
    root_size: dict[str, float] | None
    spec_json: str
    spec_json_small: str
    tokens_css: str
    asset_manifest: list[dict[str, Any]]
    all_components: list[dict[str, Any]]
    matches: list[dict[str, Any]]
    shortlist: list[dict[str, Any]]
    mcp_design_context: str | None
    bootstrap_css_url: str
    bootstrap_js_url: str
    eds_native_available: bool
    responsive_specs: list[dict[str, Any]] = field(default_factory=list)
    # Complete design copy, never abbreviated by the spec character budget.
    text_inventory_json: str = "[]"
    # Reference frame node id -> {figma node id: absolute box}, used to measure
    # the rendered DOM against Figma at each ground-truth viewport.
    geometry_indexes: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)


class WorkflowState(TypedDict, total=False):
    context: GenerationContext
    files: dict[str, str]
    review: ReviewVerdict | None
    iterations: list[dict[str, Any]]
    iteration: int
    last_pixel_mismatch: float | None
    reference_image: ImagePayload | None
    render_image: ImagePayload | None
    diff_image: ImagePayload | None
    reference_png: bytes | None
    reference_scale: float
    viewport_references: list[ViewportReference]
    viewport_metrics: list[dict[str, Any]]
    responsive_audit: list[dict[str, Any]]
    visual_diagnostics: dict[str, Any] | None
    geometry_diagnostics: dict[str, Any] | None
    contract_issues: list[ReviewIssue]
    render_png: bytes | None
    viewport_artifacts: list[dict[str, Any]]
    best_files: dict[str, str]
    best_review: ReviewVerdict | None
    best_quality: tuple[float, ...]
    best_pixel_mismatch: float | None
    best_viewport_metrics: list[dict[str, Any]]
    best_responsive_audit: list[dict[str, Any]]
    best_visual_diagnostics: dict[str, Any] | None
    best_geometry_diagnostics: dict[str, Any] | None
    best_contract_issues: list[ReviewIssue]
    best_render_image: ImagePayload | None
    best_render_png: bytes | None
    best_diff_image: ImagePayload | None
    best_viewport_artifacts: list[dict[str, Any]]
    best_iteration: int
    candidate_is_best: bool
    no_improvement_count: int
    accuracy_achieved: bool
    visual_verified: bool
    # Set once the browser render + pixel diff have succeeded at least once this
    # run; standard-mode acceptance then requires the comparison on every pass.
    visual_ever_verified: bool
    # Consecutive review passes whose render failed after a comparison had
    # succeeded; the loop stops early instead of burning iterations blind.
    render_failure_streak: int
    force_finalize: bool
    termination_reason: str
    workflow_warnings: list[str]
