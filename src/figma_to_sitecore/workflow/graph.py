from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph

from figma_to_sitecore.config import Settings
from figma_to_sitecore.domain.models import (
    ImagePayload,
    ReviewIssue,
    ReviewVerdict,
    ViewportReference,
    WorkflowState,
)
from figma_to_sitecore.generation.agents import GeneratorAgent, ReviewerAgent
from figma_to_sitecore.generation.contracts import contract_report, validate_generated_output
from figma_to_sitecore.output.writer import sync_generated_files
from figma_to_sitecore.review.geometry import (
    compare_geometry,
    detect_layout_pinning,
    geometry_headline,
    pinning_headline,
)
from figma_to_sitecore.review.visual import analyze_visual_diff, render_generated_pages
from figma_to_sitecore.utils.files import write_file
from figma_to_sitecore.utils.logging import log

VISUAL_FALLBACK_WARNING = (
    "Visual comparison against the Figma design reference could not run (browser "
    "render or pixel diff unavailable); acceptance falls back to reviewer judgment."
)
RENDER_LOST_WARNING = (
    "Browser rendering stopped working mid-run after the design comparison had already "
    "succeeded; stopping early and keeping the best visually verified candidate."
)
# Consecutive fully-failed review passes (each pass already retries the render
# once) tolerated after a successful comparison before the loop stops early.
_RENDER_FAILURE_PATIENCE = 2


class ConversionGraph:
    """Objective visual convergence loop with transactional best-candidate selection."""

    def __init__(
        self,
        *,
        generator: GeneratorAgent,
        reviewer: ReviewerAgent,
        settings: Settings,
        output_dir: Path,
        skip_review: bool = False,
    ) -> None:
        self.generator = generator
        self.reviewer = reviewer
        self.settings = settings
        self.output_dir = output_dir
        self.skip_review = skip_review
        self.graph = self._build()

    def _build(self):
        builder = StateGraph(WorkflowState)
        builder.add_node("generate", self._generate)
        builder.add_node("review", self._review)
        builder.add_node("refine", self._refine)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "generate")
        builder.add_conditional_edges(
            "generate",
            lambda _: "finalize" if self.skip_review else "review",
            {"finalize": "finalize", "review": "review"},
        )
        builder.add_conditional_edges(
            "review",
            self._after_review,
            {"finalize": "finalize", "refine": "refine"},
        )
        builder.add_conditional_edges(
            "refine",
            lambda state: "finalize" if state.get("force_finalize") else "review",
            {"finalize": "finalize", "review": "review"},
        )
        builder.add_edge("finalize", END)
        return builder.compile()

    async def _generate(self, state: WorkflowState) -> WorkflowState:
        files = await self.generator.generate(state["context"], self._design_references(state))
        sync_generated_files(self.output_dir, files)
        return {"files": files}

    @staticmethod
    def _design_references(state: WorkflowState) -> list[tuple[str, ImagePayload]]:
        """Labelled Figma design screenshots that ground generation from pass one."""
        references = [
            (f"TARGET — Figma design at {reference.name}:", reference.preview)
            for reference in state.get("viewport_references") or []
            if reference.preview
        ]
        primary = state.get("reference_image")
        if not references and primary:
            references.append(("TARGET — Figma design:", primary))
        return references

    async def _evaluate_visual(self, state: WorkflowState) -> dict[str, Any]:
        empty: dict[str, Any] = {
            "verified": False,
            "exact": False,
            "stable": False,
            "worstMismatchPct": None,
            "weightedMismatchPct": None,
            "mismatchedPixels": None,
            "totalPixels": None,
            "responsiveViolations": 0,
            "resourceErrorCount": 0,
            "viewports": [],
            "responsive": [],
            "artifacts": [],
            "worstArtifact": None,
            "diagnostics": None,
            "geometry": None,
            "geometryHeadline": None,
            "pinning": None,
            "pinningHeadline": None,
        }
        if not self.settings.visual_diff:
            return empty

        references = list(state.get("viewport_references") or [])
        reference_png = state.get("reference_png")
        if not references and reference_png:
            root_size = state["context"].root_size or {}
            references = [
                ViewportReference(
                    name=f"{round(root_size.get('w', 1440))}px",
                    node_id="primary",
                    width=root_size.get("w", 1440),
                    height=root_size.get("h", 900),
                    scale=state.get("reference_scale", 1),
                    png=reference_png,
                    preview=state.get("reference_image"),
                )
            ]
        if not references:
            return empty

        viewport_metrics: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        responsive: list[dict[str, Any]] = []
        design_width = float(round(references[0].width))
        # Always audit a width above the design width. Without it, a layout that
        # hard-pins every section to the design's pixel offsets passes every check
        # while hugging the left edge on any larger screen.
        wide_width = round(max(design_width * self.settings.wide_audit_ratio, design_width + 240))
        required_widths = tuple(
            sorted(
                {
                    *self.settings.responsive_widths,
                    *(round(item.width) for item in references),
                    wide_width,
                }
            )
        )
        rendered_pages = await render_generated_pages(
            self.output_dir,
            captures=tuple(
                (reference.width, reference.height, reference.scale) for reference in references
            ),
            responsive_widths=required_widths,
            stability_runs=2 if self.settings.strict_accuracy else 1,
            allowed_origins=self.settings.allowed_render_origins,
        )
        geometry: dict[str, Any] | None = None
        for index, (reference, rendered) in enumerate(zip(references, rendered_pages, strict=True)):
            if not rendered:
                continue
            design_index = (state["context"].geometry_indexes or {}).get(reference.node_id)
            if design_index:
                measured = compare_geometry(
                    design_index,
                    rendered.get("domGeometry"),
                    design_width=reference.width,
                    design_height=reference.height,
                    tolerance_px=self.settings.geometry_tolerance_px,
                )
                measured["viewport"] = reference.name
                # The primary frame is the one the markup was authored against,
                # so its measurements drive refinement.
                if geometry is None or index == 0:
                    geometry = measured
            diff = analyze_visual_diff(
                reference.png,
                rendered["png"],
                threshold=self.settings.effective_pixel_diff_threshold,
                tile_size=self.settings.pixel_diff_tile_size,
            )
            if not diff:
                continue
            metric = {
                "name": reference.name,
                "nodeId": reference.node_id,
                "cssWidth": reference.width,
                "cssHeight": reference.height,
                "scale": reference.scale,
                **diff.to_dict(include_regions=False),
                "stable": bool(rendered.get("stable")),
                "pixelHash": rendered.get("pixelHash"),
                "resourceErrors": list(rendered.get("resourceErrors") or []),
            }
            viewport_metrics.append(metric)
            artifact = {
                "name": reference.name,
                "referenceImage": reference.preview,
                "referencePng": reference.png,
                "renderPng": rendered["png"],
                "renderJpg": rendered["jpg"],
                "diffPng": diff.heatmap_png,
                "metric": metric,
                "regions": [region.to_dict() for region in diff.regions],
            }
            artifacts.append(artifact)
            if index == 0:
                responsive = list(rendered.get("responsive") or [])

        if not viewport_metrics:
            return empty

        mismatched_pixels = sum(int(item["mismatchedPixels"]) for item in viewport_metrics)
        total_pixels = sum(int(item["totalPixels"]) for item in viewport_metrics)
        worst = max(viewport_metrics, key=lambda item: float(item["mismatchPct"]))
        worst_artifact = next(item for item in artifacts if item["name"] == worst["name"])
        pinning = detect_layout_pinning(responsive, design_width=design_width)
        responsive_violations = sum(
            int(float(item.get("horizontalOverflowPx", 0)) > 0)
            + len(item.get("overflowElements") or [])
            + len(item.get("brokenImages") or [])
            + len(item.get("clippedElements") or [])
            + int(not item.get("fontsReady", False))
            for item in responsive
        ) + int(pinning.get("pinnedCount", 0))
        resource_error_count = sum(len(item["resourceErrors"]) for item in viewport_metrics)
        verified = len(viewport_metrics) == len(references)
        stable = verified and all(bool(item["stable"]) for item in viewport_metrics)
        dimensions_equal = verified and all(
            bool(item["dimensionsEqual"]) for item in viewport_metrics
        )
        exact = verified and all(bool(item["exact"]) for item in viewport_metrics)
        aggregate = {
            "verified": verified,
            "exact": exact,
            "stable": stable,
            "dimensionsEqual": dimensions_equal,
            "worstMismatchPct": float(worst["mismatchPct"]),
            "weightedMismatchPct": mismatched_pixels / total_pixels * 100 if total_pixels else None,
            "mismatchedPixels": mismatched_pixels,
            "totalPixels": total_pixels,
            "responsiveViolations": responsive_violations,
            "resourceErrorCount": resource_error_count,
        }
        diagnostics = {
            "aggregate": aggregate,
            "worstViewport": {**worst, "regions": worst_artifact["regions"]},
            "allViewports": viewport_metrics,
        }
        return {
            **aggregate,
            "viewports": viewport_metrics,
            "responsive": responsive,
            "artifacts": artifacts,
            "worstArtifact": worst_artifact,
            "diagnostics": diagnostics,
            "geometry": geometry,
            "geometryHeadline": geometry_headline(geometry),
            "pinning": pinning,
            "pinningHeadline": pinning_headline(pinning),
        }

    def _contract_issues(self, files: dict[str, str], state: WorkflowState) -> list[ReviewIssue]:
        """Machine-check the non-negotiable half of the delivery contract."""
        context = state["context"]
        # A hook is valid if it names a node in any ground-truth frame.
        known_ids = {
            node_id
            for index in (context.geometry_indexes or {}).values()
            for node_id in index
        }
        issues = validate_generated_output(
            files,
            asset_manifest=context.asset_manifest,
            components=context.all_components,
            eds_native_available=context.eds_native_available,
            known_figma_ids=known_ids,
        )
        if issues:
            log.warning(
                "Output contract: %s violation(s) — %s",
                len(issues),
                "; ".join(f"{issue.area}" for issue in issues[:6]),
            )
        return issues

    @staticmethod
    def _merge_issues(verdict: ReviewVerdict, contract: list[ReviewIssue]) -> ReviewVerdict:
        """Fold mechanical violations into the verdict the refiner acts on.

        They are prepended and deduplicated so a contract breach can never be
        argued away by the reviewer, and so the acceptance gate counts it.
        """
        if not contract:
            return verdict
        seen = {(issue.area, issue.description) for issue in contract}
        merged = [*contract, *(issue for issue in verdict.issues if (issue.area, issue.description) not in seen)]
        return verdict.model_copy(update={"issues": merged})

    @staticmethod
    def _severity_counts(verdict: ReviewVerdict) -> dict[str, int]:
        return {
            severity: sum(issue.severity == severity for issue in verdict.issues)
            for severity in ("critical", "major", "minor")
        }

    def _locked_regressions(self, state: WorkflowState, evaluation: dict[str, Any]) -> int:
        locked = {
            item["name"]
            for item in state.get("best_viewport_metrics", [])
            if item.get("dimensionsEqual")
            and float(item.get("mismatchPct", 101)) <= self.settings.pixel_mismatch_target
        }
        current = {item["name"]: item for item in evaluation["viewports"]}
        return sum(
            name not in current
            or not current[name].get("dimensionsEqual")
            or float(current[name].get("mismatchPct", 101)) > self.settings.pixel_mismatch_target
            for name in locked
        )

    def _quality(
        self,
        state: WorkflowState,
        evaluation: dict[str, Any],
        severity: dict[str, int],
        verdict: ReviewVerdict,
    ) -> tuple[float, ...]:
        mismatch = evaluation.get("worstMismatchPct")
        weighted = evaluation.get("weightedMismatchPct")
        return (
            float(self._locked_regressions(state, evaluation) > 0),
            float(not evaluation.get("verified")),
            float(not evaluation.get("stable")),
            float(not evaluation.get("dimensionsEqual")),
            float(evaluation.get("resourceErrorCount", 0) > 0),
            float(evaluation.get("responsiveViolations", 0) > 0),
            float(severity["critical"] > 0),
            float(mismatch if mismatch is not None else 101),
            float(weighted if weighted is not None else 101),
            float(severity["critical"]),
            float(severity["major"]),
            float(severity["minor"]),
            -float(verdict.score),
        )

    def _meets_target(
        self,
        verdict: ReviewVerdict | None,
        evaluation: dict[str, Any],
        contract_issues: list[ReviewIssue] | None = None,
        *,
        require_visual: bool = False,
    ) -> bool:
        # The output contract is not a judgement call, so it is checked before
        # the reviewer's issue budget rather than being folded into it.
        if contract_issues:
            return False
        if verdict is None or len(verdict.issues) > self.settings.review_target_issues:
            return False
        if not self.settings.strict_accuracy:
            # A Figma reference exists and rendering is known to work, so a clear
            # reviewer verdict alone is not enough: the candidate must actually
            # have been compared against the design at every reference viewport.
            return bool(evaluation.get("verified")) if require_visual else True
        mismatch = evaluation.get("worstMismatchPct")
        return bool(
            evaluation.get("verified")
            and evaluation.get("stable")
            and evaluation.get("resourceErrorCount", 0) == 0
            and evaluation.get("responsiveViolations", 0) == 0
            and mismatch is not None
            and float(mismatch) <= self.settings.pixel_mismatch_target
            and all(item.get("dimensionsEqual") for item in evaluation.get("viewports", []))
        )

    def _write_iteration_artifacts(self, iteration: int, artifacts: list[dict[str, Any]]) -> None:
        for artifact in artifacts:
            label = re.sub(r"[^a-z0-9-]+", "-", artifact["name"].lower()).strip("-") or "viewport"
            root = self.output_dir / "reference" / "iterations" / f"{iteration:02d}-{label}"
            write_file(root / "figma-design.png", artifact["referencePng"])
            write_file(root / "generated-render.png", artifact["renderPng"])
            if artifact.get("diffPng"):
                write_file(root / "pixel-diff.png", artifact["diffPng"])

    async def _review(self, state: WorkflowState) -> WorkflowState:
        evaluation = await self._evaluate_visual(state)
        has_reference = bool(state.get("viewport_references") or state.get("reference_png"))
        visual_expected = self.settings.visual_diff and has_reference
        if visual_expected and not evaluation.get("verified"):
            # One in-pass retry separates a transient browser flake from an
            # environment that cannot render, so a single failure can neither
            # waive the visual gate nor abort a run that was converging.
            log.warning("Browser render produced no design comparison; retrying once")
            evaluation = await self._evaluate_visual(state)
        contract_issues = self._contract_issues(state["files"], state)
        iteration = state.get("iteration", 0) + 1
        # The design comparison is required for acceptance whenever a Figma
        # reference exists and rendering has proven to work in this run; when the
        # environment cannot render at all, fall back to the reviewer alone
        # instead of burning every iteration on a comparison that can never run.
        visual_verified_now = bool(evaluation.get("verified"))
        visual_possible = visual_verified_now or bool(state.get("visual_ever_verified"))
        workflow_warnings = list(state.get("workflow_warnings", []))
        if visual_verified_now and VISUAL_FALLBACK_WARNING in workflow_warnings:
            # The comparison recovered, so the accepted candidate is visually
            # gated after all; a stale fallback warning would misreport the run.
            workflow_warnings.remove(VISUAL_FALLBACK_WARNING)
        if (
            visual_expected
            and not visual_possible
            and not self.settings.strict_accuracy
            and VISUAL_FALLBACK_WARNING not in workflow_warnings
        ):
            log.warning(VISUAL_FALLBACK_WARNING)
            workflow_warnings.append(VISUAL_FALLBACK_WARNING)
        render_failure_streak = (
            state.get("render_failure_streak", 0) + 1
            if visual_expected and not visual_verified_now and state.get("visual_ever_verified")
            else 0
        )
        if render_failure_streak >= _RENDER_FAILURE_PATIENCE:
            # Rendering worked earlier but is now persistently gone: no further
            # candidate can be verified or outrank the verified best, so more
            # generator/reviewer rounds would be pure waste.
            log.warning(RENDER_LOST_WARNING)
            return {
                "force_finalize": True,
                "termination_reason": "render_lost",
                "workflow_warnings": (
                    workflow_warnings
                    if RENDER_LOST_WARNING in workflow_warnings
                    else [*workflow_warnings, RENDER_LOST_WARNING]
                ),
                "visual_ever_verified": True,
                "render_failure_streak": render_failure_streak,
                "iteration": iteration,
                "contract_issues": contract_issues,
            }
        self._write_iteration_artifacts(iteration, evaluation["artifacts"])
        worst_artifact = evaluation.get("worstArtifact")
        reference_image = (
            worst_artifact.get("referenceImage") if worst_artifact else state.get("reference_image")
        )
        render_image = (
            ImagePayload(worst_artifact["renderJpg"], "image/jpeg") if worst_artifact else None
        )
        diff_image = (
            ImagePayload(worst_artifact["diffPng"], "image/png")
            if worst_artifact and worst_artifact.get("diffPng")
            else None
        )
        mismatch = evaluation.get("worstMismatchPct")
        if mismatch is not None:
            log.info(
                "Worst pixel mismatch: %.6f%% across %s viewport(s)",
                mismatch,
                len(evaluation["viewports"]),
            )
        headline = " ".join(
            part
            for part in (evaluation.get("geometryHeadline"), evaluation.get("pinningHeadline"))
            if part
        ) or None
        if headline:
            log.info("Geometry: %s", headline)

        try:
            verdict = await self.reviewer.review(
                state["context"],
                state["files"],
                reference_image,
                render_image,
                diff_image,
                mismatch,
                evaluation.get("diagnostics"),
                evaluation.get("responsive"),
                {**(evaluation.get("geometry") or {}), "layoutPinning": evaluation.get("pinning")},
                contract_report(contract_issues) if contract_issues else None,
            )
        except Exception as exc:
            warning = f"Reviewer model failed after a usable page was generated: {exc}"
            log.warning(warning)
            updates: WorkflowState = {
                "force_finalize": True,
                "termination_reason": "review_model_error",
                "workflow_warnings": [*workflow_warnings, warning],
                "visual_ever_verified": visual_possible,
                "render_failure_streak": render_failure_streak,
                "iteration": iteration,
                "visual_diagnostics": evaluation.get("diagnostics"),
                "geometry_diagnostics": {
                    **(evaluation.get("geometry") or {}),
                    "layoutPinning": evaluation.get("pinning"),
                    "layoutPinningHeadline": evaluation.get("pinningHeadline"),
                },
                "contract_issues": contract_issues,
                "viewport_metrics": evaluation["viewports"],
                "responsive_audit": evaluation["responsive"],
            }
            if not state.get("best_files"):
                updates.update(
                    {
                        "best_files": dict(state["files"]),
                        "best_iteration": iteration,
                        "best_viewport_metrics": evaluation["viewports"],
                        "best_responsive_audit": evaluation["responsive"],
                        "best_visual_diagnostics": evaluation.get("diagnostics"),
                        "best_geometry_diagnostics": {
                        **(evaluation.get("geometry") or {}),
                        "layoutPinning": evaluation.get("pinning"),
                        "layoutPinningHeadline": evaluation.get("pinningHeadline"),
                    },
                        "best_contract_issues": contract_issues,
                        "best_viewport_artifacts": evaluation["artifacts"],
                        "best_pixel_mismatch": mismatch,
                    }
                )
            return updates

        verdict = self._merge_issues(verdict, contract_issues)
        severity = self._severity_counts(verdict)
        target_met = self._meets_target(
            verdict,
            evaluation,
            contract_issues,
            require_visual=visual_expected and visual_possible,
        )
        quality = self._quality(state, evaluation, severity, verdict)
        old_quality = state.get("best_quality")
        # A candidate satisfying the configured acceptance contract always wins,
        # even if a diagnostic tie-breaker (such as reviewer score or pixels in
        # standard mode) ranks an earlier, non-passing candidate more highly.
        improved = target_met or old_quality is None or quality < old_quality
        old_mismatch = state.get("best_pixel_mismatch")
        meaningful = improved and (
            old_quality is None
            or quality[:7] < old_quality[:7]
            or old_mismatch is None
            or mismatch is None
            or old_mismatch - mismatch >= self.settings.min_pixel_improvement
        )
        stagnation = 0 if meaningful else state.get("no_improvement_count", 0) + 1
        if target_met:
            decision = "accepted"
        elif improved:
            decision = "checkpointed"
        else:
            decision = "rejected-regression"
        iteration_record = {
            "score": verdict.score,
            "issueCount": len(verdict.issues),
            **severity,
            "pixelMismatchPct": mismatch,
            "weightedPixelMismatchPct": evaluation.get("weightedMismatchPct"),
            "mismatchedPixels": evaluation.get("mismatchedPixels"),
            "visualVerified": evaluation.get("verified"),
            "dimensionsMatch": all(
                item.get("dimensionsEqual") for item in evaluation.get("viewports", [])
            ),
            "responsiveViolations": evaluation.get("responsiveViolations", 0),
            "stable": evaluation.get("stable"),
            "improved": improved,
            "meaningfulImprovement": meaningful,
            "decision": decision,
            "stagnationCount": stagnation,
            "contractViolations": len(contract_issues),
            "documentHeightErrorPx": (evaluation.get("geometry") or {}).get("documentHeightErrorPx"),
            "viewports": evaluation["viewports"],
        }
        updates = {
            "review": verdict,
            "iteration": iteration,
            "iterations": [*state.get("iterations", []), iteration_record],
            "last_pixel_mismatch": mismatch,
            "render_image": render_image,
            "render_png": worst_artifact.get("renderPng") if worst_artifact else None,
            "diff_image": diff_image,
            "viewport_metrics": evaluation["viewports"],
            "responsive_audit": evaluation["responsive"],
            "visual_diagnostics": evaluation.get("diagnostics"),
            "geometry_diagnostics": {
                    **(evaluation.get("geometry") or {}),
                    "layoutPinning": evaluation.get("pinning"),
                    "layoutPinningHeadline": evaluation.get("pinningHeadline"),
                },
            "contract_issues": contract_issues,
            "viewport_artifacts": evaluation["artifacts"],
            "candidate_is_best": improved,
            "no_improvement_count": stagnation,
            "accuracy_achieved": target_met,
            "visual_verified": visual_verified_now,
            "visual_ever_verified": visual_possible,
            "render_failure_streak": render_failure_streak,
            "workflow_warnings": workflow_warnings,
            "force_finalize": False,
        }
        if target_met:
            updates["termination_reason"] = "target_met"
        elif iteration >= self.settings.max_review_iterations:
            updates["termination_reason"] = "max_iterations"
        if improved:
            updates.update(
                {
                    "best_files": dict(state["files"]),
                    "best_review": verdict,
                    "best_quality": quality,
                    "best_pixel_mismatch": mismatch,
                    "best_viewport_metrics": evaluation["viewports"],
                    "best_responsive_audit": evaluation["responsive"],
                    "best_visual_diagnostics": evaluation.get("diagnostics"),
                    "best_geometry_diagnostics": {
                        **(evaluation.get("geometry") or {}),
                        "layoutPinning": evaluation.get("pinning"),
                        "layoutPinningHeadline": evaluation.get("pinningHeadline"),
                    },
                    "best_contract_issues": contract_issues,
                    "best_render_image": render_image,
                    "best_render_png": worst_artifact.get("renderPng") if worst_artifact else None,
                    "best_diff_image": diff_image,
                    "best_viewport_artifacts": evaluation["artifacts"],
                    "best_iteration": iteration,
                }
            )
        return updates

    def _after_review(self, state: WorkflowState) -> Literal["finalize", "refine"]:
        if state.get("force_finalize") or state.get("accuracy_achieved"):
            return "finalize"
        if state.get("iteration", 0) >= self.settings.max_review_iterations:
            log.warning(
                "Reached MAX_REVIEW_ITERATIONS=%s; restoring best candidate from iteration %s",
                self.settings.max_review_iterations,
                state.get("best_iteration", "n/a"),
            )
            return "finalize"
        return "refine"

    async def _refine(self, state: WorkflowState) -> WorkflowState:
        review = state.get("best_review") or state.get("review")
        if review is None:
            return {"force_finalize": True, "termination_reason": "review_unavailable"}
        source_files = state.get("best_files") or state["files"]
        sync_generated_files(self.output_dir, source_files, state.get("files"))
        artifacts = state.get("best_viewport_artifacts") or state.get("viewport_artifacts") or []
        worst_artifact = None
        best_diagnostics = state.get("best_visual_diagnostics") or state.get("visual_diagnostics")
        stagnation = state.get("no_improvement_count", 0)
        if best_diagnostics and stagnation >= self.settings.accuracy_patience:
            best_diagnostics = {
                **best_diagnostics,
                "strategy": (
                    "Plateau escape: change only the causal geometry/typography/style rules affecting "
                    "the highest-error regions; preserve every locked viewport and zero-error region."
                ),
            }
            log.warning(
                "Accuracy plateau detected after %s non-improving candidate(s); using a targeted pass",
                stagnation,
            )
        worst_name = ((best_diagnostics or {}).get("worstViewport") or {}).get("name")
        if artifacts:
            worst_artifact = next(
                (item for item in artifacts if item["name"] == worst_name),
                artifacts[0],
            )
        reference_image = (
            worst_artifact.get("referenceImage") if worst_artifact else state.get("reference_image")
        )
        render_image = (
            ImagePayload(worst_artifact["renderJpg"], "image/jpeg") if worst_artifact else None
        )
        diff_image = (
            ImagePayload(worst_artifact["diffPng"], "image/png")
            if worst_artifact and worst_artifact.get("diffPng")
            else None
        )
        best_geometry = state.get("best_geometry_diagnostics") or state.get("geometry_diagnostics")
        try:
            files = await self.generator.refine(
                state["context"],
                source_files,
                review,
                state.get("best_pixel_mismatch"),
                reference_image,
                render_image,
                diff_image,
                best_diagnostics,
                state.get("best_responsive_audit") or state.get("responsive_audit"),
                stagnation,
                best_geometry,
                " ".join(
                    part
                    for part in (
                        geometry_headline(best_geometry),
                        (best_geometry or {}).get("layoutPinningHeadline"),
                    )
                    if part
                )
                or None,
            )
        except Exception as exc:
            warning = f"Refinement model failed; restored the best measured candidate: {exc}"
            log.warning(warning)
            return {
                "files": dict(source_files),
                "force_finalize": True,
                "termination_reason": "refinement_model_error",
                "workflow_warnings": [*state.get("workflow_warnings", []), warning],
            }
        sync_generated_files(self.output_dir, files, source_files)
        return {"files": files, "force_finalize": False}

    def _write_final_artifacts(self, artifacts: list[dict[str, Any]]) -> None:
        for artifact in artifacts:
            label = re.sub(r"[^a-z0-9-]+", "-", artifact["name"].lower()).strip("-") or "viewport"
            root = self.output_dir / "reference" / "viewports" / label
            write_file(root / "figma-design.png", artifact["referencePng"])
            write_file(root / "generated-render.png", artifact["renderPng"])
            if artifact.get("diffPng"):
                write_file(root / "pixel-diff.png", artifact["diffPng"])

    async def _finalize(self, state: WorkflowState) -> WorkflowState:
        # Metrics, artifacts and images must describe the delivered candidate.
        # When a best checkpoint is delivered, never fall through its (possibly
        # empty) measurements to the current, rejected candidate's — that would
        # attribute one candidate's pixel evidence to another's files.
        use_best = bool(state.get("best_files"))

        def delivered(best_key: str, current_key: str) -> Any:
            return state.get(best_key) if use_best else state.get(current_key)

        files = state["best_files"] if use_best else state["files"]
        sync_generated_files(self.output_dir, files, state.get("files"))
        review = state.get("best_review") or state.get("review")
        artifacts = delivered("best_viewport_artifacts", "viewport_artifacts") or []
        self._write_final_artifacts(artifacts)
        diagnostics = delivered("best_visual_diagnostics", "visual_diagnostics") or {}
        worst_name = (diagnostics.get("worstViewport") or {}).get("name")
        worst_artifact = next(
            (artifact for artifact in artifacts if artifact["name"] == worst_name),
            artifacts[0] if artifacts else None,
        )
        render_png = delivered("best_render_png", "render_png")
        diff_image = delivered("best_diff_image", "diff_image")
        if render_png:
            write_file(self.output_dir / "reference" / "generated-render.png", render_png)
        if worst_artifact:
            write_file(self.output_dir / "reference" / "figma-design.png", worst_artifact["referencePng"])
        if diff_image:
            write_file(self.output_dir / "reference" / "pixel-diff.png", diff_image.data)

        viewport_metrics = delivered("best_viewport_metrics", "viewport_metrics") or []
        responsive = delivered("best_responsive_audit", "responsive_audit") or []
        best_diagnostics = delivered("best_visual_diagnostics", "visual_diagnostics")
        evaluation = {
            **((best_diagnostics or {}).get("aggregate") or {}),
            "viewports": viewport_metrics,
            "responsive": responsive,
        }
        contract_issues = self._contract_issues(files, state)
        has_reference = bool(state.get("viewport_references") or state.get("reference_png"))
        achieved = self._meets_target(
            review,
            evaluation,
            contract_issues,
            require_visual=(
                self.settings.visual_diff and has_reference and bool(state.get("visual_ever_verified"))
            ),
        )
        reason = state.get("termination_reason")
        if contract_issues and reason in {None, "target_met", "best_effort"}:
            reason = "contract_violations"
        if self.skip_review:
            reason = "review_skipped"
        elif achieved:
            reason = "target_met"
        elif not reason:
            reason = "visual_unavailable" if not evaluation.get("verified") else "best_effort"
        warnings = list(state.get("workflow_warnings", []))
        if self.settings.strict_accuracy and not achieved:
            warnings.append(
                "Strict accuracy target was not met; output was rolled back to the best measured candidate."
            )
        if contract_issues:
            warnings.append(
                f"{len(contract_issues)} output-contract violation(s) remain in the delivered files: "
                + "; ".join(f"{issue.area}" for issue in contract_issues)
            )
        return {
            "files": dict(files),
            "review": self._merge_issues(review, contract_issues) if review else review,
            "last_pixel_mismatch": (
                state.get("best_pixel_mismatch") if use_best else state.get("last_pixel_mismatch")
            ),
            "viewport_metrics": viewport_metrics,
            "responsive_audit": responsive,
            "visual_diagnostics": best_diagnostics,
            "geometry_diagnostics": delivered("best_geometry_diagnostics", "geometry_diagnostics"),
            "contract_issues": contract_issues,
            "render_image": delivered("best_render_image", "render_image"),
            "render_png": render_png,
            "diff_image": diff_image,
            "accuracy_achieved": achieved,
            "termination_reason": reason,
            "workflow_warnings": warnings,
            "force_finalize": False,
        }

    async def run(self, initial_state: WorkflowState) -> WorkflowState:
        recursion_limit = self.settings.max_review_iterations * 3 + 8
        return await self.graph.ainvoke(initial_state, {"recursion_limit": recursion_limit})
