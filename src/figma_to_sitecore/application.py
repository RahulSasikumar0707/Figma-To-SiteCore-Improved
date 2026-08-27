from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from figma_to_sitecore.config import Settings
from figma_to_sitecore.domain.models import (
    GenerationContext,
    ImagePayload,
    ViewportReference,
    WorkflowState,
)
from figma_to_sitecore.eds.manifest import load_eds_manifest
from figma_to_sitecore.eds.matcher import match_sections, shortlisted_components
from figma_to_sitecore.eds.storybook import hydrate_storybook_snippets, scan_storybook_components
from figma_to_sitecore.figma.assets import download_assets, download_reference_screenshot
from figma_to_sitecore.figma.client import FigmaRestClient
from figma_to_sitecore.figma.mcp import FigmaMcpClient, is_figma_remote_url
from figma_to_sitecore.figma.normalizer import (
    compact_spec,
    geometry_index,
    normalize_design,
    text_inventory,
)
from figma_to_sitecore.generation.agents import GeneratorAgent, ReviewerAgent, create_anthropic_model
from figma_to_sitecore.output.writer import (
    copy_eds_native_css,
    find_eds_native_css,
    write_report,
)
from figma_to_sitecore.tokens.builder import build_design_tokens
from figma_to_sitecore.utils.files import next_output_dir, write_file
from figma_to_sitecore.utils.images import fit_image_payload
from figma_to_sitecore.utils.logging import log
from figma_to_sitecore.workflow.graph import ConversionGraph


class AccuracyTargetNotMet(RuntimeError):
    def __init__(self, output_dir: Path, mismatch: float | None, reason: str) -> None:
        measured = f"; best mismatch {mismatch:.6f}%" if mismatch is not None else ""
        super().__init__(
            f"Strict accuracy target was not met ({reason}{measured}). "
            f"Best candidate and report were preserved in {output_dir}."
        )
        self.output_dir = output_dir


class StorybookUnavailable(RuntimeError):
    def __init__(self, base: str, manifest_path: Path) -> None:
        super().__init__(
            f"Storybook at {base} returned no EDS markup, so {manifest_path.name} was left untouched. "
            "Rebuild the manifest from the corporate network."
        )


class ConversionApplication:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def rebuild_manifest(self) -> Path:
        components = await scan_storybook_components(self.settings.eds_storybook_base)
        # Off-network every page answers HTTP 403 and the scan still yields one empty
        # shell per known component; writing those would destroy the curated catalog.
        if not any(component.get("snippet") or component.get("edsClasses") for component in components):
            raise StorybookUnavailable(self.settings.eds_storybook_base, self.settings.manifest_path)
        document = {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "source": "EDS Storybook scan",
            "componentCount": len(components),
            "components": components,
        }
        write_file(self.settings.manifest_path, json.dumps(document, indent=2) + "\n")
        log.info("Rebuilt %s with %s components", self.settings.manifest_path, len(components))
        return self.settings.manifest_path

    async def convert(self, *, skip_review: bool = False) -> Path:
        if self.settings.strict_accuracy:
            await self._validate_strict_runtime(
                skip_review=skip_review,
                visual_diff=self.settings.visual_diff,
            )
        warnings: list[str] = []
        mcp: FigmaMcpClient | None = None
        mcp_context = None
        figma_variables = None
        mcp_screenshot = None

        try:
            if self.settings.figma_source != "rest":
                if is_figma_remote_url(self.settings.figma_mcp_url):
                    message = (
                        "https://mcp.figma.com/mcp requires Figma OAuth through a supported MCP host and "
                        "cannot use FIGMA_TOKEN directly. Set FIGMA_MCP_URL=http://127.0.0.1:3845/mcp "
                        "after enabling Figma Desktop MCP, or set FIGMA_SOURCE=rest."
                    )
                    if self.settings.figma_source == "mcp":
                        raise RuntimeError(message)
                    warnings.append(message + " Continuing with REST.")
                    log.warning(warnings[-1])
                else:
                    mcp = await FigmaMcpClient.try_connect(self.settings.figma_mcp_url)
                    if mcp:
                        mcp_context = await mcp.get_design_context(self.settings.node_id)
                        figma_variables = await mcp.get_variable_definitions(self.settings.node_id)
                        mcp_screenshot = await mcp.get_screenshot(self.settings.node_id)
                    elif self.settings.figma_source == "mcp":
                        raise RuntimeError("FIGMA_SOURCE=mcp but Figma Desktop MCP is not reachable")

            async with FigmaRestClient(self.settings.figma_access_token) as rest:
                requested_node_ids = list(
                    dict.fromkeys([self.settings.node_id, *self.settings.reference_nodes.values()])
                )
                log.info("Fetching Figma node%s %s", "s" if len(requested_node_ids) > 1 else "", ", ".join(requested_node_ids))
                nodes = await rest.get_nodes(self.settings.figma_file_key, requested_node_ids)
                entry = nodes.get(self.settings.node_id) or {}
                document = entry.get("document")
                if not document:
                    raise RuntimeError(
                        f"Node {self.settings.node_id} was not found in file {self.settings.figma_file_key}"
                    )
                design_name = document.get("name", self.settings.node_id)
                design = normalize_design(document)
                if not design["root"]:
                    raise RuntimeError(f"Figma node {self.settings.node_id} ({design_name!r}) is hidden")

                designs_by_node: dict[str, dict[str, Any]] = {self.settings.node_id: design}
                requested_references = dict(self.settings.reference_nodes)
                primary_width = round((design.get("rootSize") or {}).get("w", 1440))
                if self.settings.node_id not in requested_references.values():
                    conflicting_node = requested_references.get(primary_width)
                    if conflicting_node and conflicting_node != self.settings.node_id:
                        message = (
                            f"Primary node {self.settings.node_id} and reference node {conflicting_node} "
                            f"both claim the {primary_width}px viewport. Use one ground-truth frame per width."
                        )
                        if self.settings.strict_accuracy:
                            raise RuntimeError(message)
                        warnings.append(message + " Keeping the configured reference.")
                    else:
                        requested_references[primary_width] = self.settings.node_id
                for configured_width, node_id in sorted(requested_references.items()):
                    if node_id in designs_by_node:
                        continue
                    reference_document = (nodes.get(node_id) or {}).get("document")
                    if not reference_document:
                        message = f"Responsive reference node {node_id} ({configured_width}px) was not found."
                        if self.settings.strict_accuracy:
                            raise RuntimeError(message)
                        warnings.append(message)
                        continue
                    reference_design = normalize_design(reference_document)
                    if not reference_design["root"]:
                        message = f"Responsive reference node {node_id} ({configured_width}px) is hidden."
                        if self.settings.strict_accuracy:
                            raise RuntimeError(message)
                        warnings.append(message)
                        continue
                    designs_by_node[node_id] = reference_design

                output_dir = next_output_dir(
                    self.settings.resolved_output_root,
                    self.settings.output_prefix,
                )
                log.info("Output directory: %s", output_dir)
                combined_assets: list[dict[str, Any]] = []
                seen_assets: set[tuple[Any, ...]] = set()
                for variant in designs_by_node.values():
                    for asset in variant["assets"]:
                        identity = (asset.get("nodeId"), asset.get("imageRef"), asset.get("export"))
                        if identity in seen_assets:
                            continue
                        seen_assets.add(identity)
                        combined_assets.append(asset)
                asset_manifest = await download_assets(
                    rest,
                    self.settings.figma_file_key,
                    combined_assets,
                    output_dir,
                )
                reference: dict[str, Any] = {"png": None, "jpg": None, "pngScale": 1}
                viewport_references: list[ViewportReference] = []
                for configured_width, node_id in sorted(requested_references.items()):
                    reference_variant = designs_by_node.get(node_id)
                    if not reference_variant:
                        continue
                    root_size = reference_variant.get("rootSize") or {}
                    actual_width = float(root_size.get("w", configured_width))
                    actual_height = float(root_size.get("h", 900))
                    if round(actual_width) != configured_width:
                        message = (
                            f"Reference node {node_id} is {actual_width:g}px wide, not the configured "
                            f"{configured_width}px; using the Figma width."
                        )
                        if self.settings.strict_accuracy:
                            raise RuntimeError(message)
                        warnings.append(message)
                    viewport_name = f"{round(actual_width)}px"
                    try:
                        downloaded = await download_reference_screenshot(
                            rest,
                            self.settings.figma_file_key,
                            node_id,
                            root_size,
                            output_dir,
                            relative_path=f"reference/viewports/{viewport_name}/figma-design.png",
                        )
                    except Exception as exc:
                        message = f"Reference screenshot unavailable for {viewport_name}: {exc}"
                        if self.settings.strict_accuracy:
                            raise RuntimeError(message) from exc
                        warnings.append(message)
                        continue
                    if not downloaded.get("png"):
                        message = f"Figma returned no PNG reference for {viewport_name}."
                        if self.settings.strict_accuracy:
                            raise RuntimeError(message)
                        warnings.append(message)
                        continue
                    # Previews are model-bound; the lossless PNG stays untouched
                    # for the pixel diff even when the preview must be shrunk.
                    preview = fit_image_payload(
                        ImagePayload(downloaded["jpg"], "image/jpeg")
                        if downloaded.get("jpg")
                        else ImagePayload(downloaded["png"], "image/png"),
                        label=f"Figma reference preview {viewport_name}",
                    )
                    viewport_references.append(
                        ViewportReference(
                            name=viewport_name,
                            node_id=node_id,
                            width=actual_width,
                            height=actual_height,
                            scale=float(downloaded.get("renderScale", downloaded.get("pngScale", 1))),
                            png=downloaded["png"],
                            preview=preview,
                        )
                    )
                    if node_id == self.settings.node_id:
                        reference = downloaded
                        write_file(output_dir / "reference" / "figma-design.png", downloaded["png"])

            tokens_css, _ = build_design_tokens(
                design["tokens"],
                figma_variables if isinstance(figma_variables, dict) else None,
            )
            write_file(output_dir / "css" / "tokens.css", tokens_css)

            native_css = find_eds_native_css(self.settings)
            if native_css:
                copy_eds_native_css(native_css, output_dir)
            else:
                warnings.append(
                    "eds-native.css was not found; generated styles.css must carry complete component styling."
                )

            components, curated = await load_eds_manifest(
                self.settings.manifest_path,
                self.settings.eds_storybook_base,
            )
            # The Storybook host is reachable only from the corporate network, so a
            # usable curated manifest is taken as-is: re-fetching it off-network only
            # produces a wall of HTTP 403 warnings. Opt back in with a refresh.
            if not curated:
                if not any(component.get("snippet") or component.get("edsClasses") for component in components):
                    warnings.append(
                        f"Storybook crawl of {self.settings.eds_storybook_base} returned no EDS markup; "
                        f"component grounding is unavailable. Supply {self.settings.manifest_path.name} "
                        "or run on the corporate network."
                    )
            elif self.settings.eds_storybook_refresh:
                try:
                    await hydrate_storybook_snippets(components, self.settings.eds_storybook_base)
                except Exception as exc:
                    warnings.append(f"Storybook refresh failed ({exc}); using curated snippets.")
            else:
                log.info(
                    "Skipping Storybook fetch; set EDS_STORYBOOK_REFRESH=true or pass --refresh-storybook to re-fetch snippets"
                )
            matches = match_sections(design["root"], components)
            shortlist = shortlisted_components(matches, components)
            responsive_specs = []
            for configured_width, node_id in sorted(requested_references.items()):
                if node_id == self.settings.node_id:
                    continue
                responsive_variant = designs_by_node.get(node_id)
                if not responsive_variant:
                    continue
                variant_width = round((responsive_variant.get("rootSize") or {}).get("w", configured_width))
                responsive_specs.append(
                    {
                        "width": variant_width,
                        "nodeId": node_id,
                        "spec": compact_spec(responsive_variant["root"], 50_000),
                    }
                )

            # One index per ground-truth frame so every measured viewport can be
            # compared against the Figma boxes that actually belong to it.
            geometry_indexes = {
                node_id: geometry_index(variant["root"])
                for node_id, variant in designs_by_node.items()
            }
            copy_deck = text_inventory(design["root"])
            log.info(
                "Design copy deck: %s text runs; geometry index: %s measurable nodes",
                len(copy_deck),
                len(geometry_indexes.get(self.settings.node_id) or {}),
            )
            context = GenerationContext(
                design_name=design_name,
                root_size=design["rootSize"],
                spec_json=compact_spec(design["root"], 140_000),
                spec_json_small=compact_spec(design["root"], 60_000),
                tokens_css=tokens_css,
                asset_manifest=asset_manifest,
                all_components=components,
                matches=matches,
                shortlist=shortlist,
                mcp_design_context=mcp_context,
                bootstrap_css_url=self.settings.bootstrap_css_url,
                bootstrap_js_url=self.settings.bootstrap_js_url,
                eds_native_available=native_css is not None,
                responsive_specs=responsive_specs,
                text_inventory_json=json.dumps(copy_deck, ensure_ascii=False, indent=1),
                geometry_indexes=geometry_indexes,
            )
            generator_model = create_anthropic_model(
                api_key=self.settings.generator_key,
                model=self.settings.anthropic_model,
                max_tokens=self.settings.llm_max_tokens,
                reasoning_effort=self.settings.llm_reasoning_effort,
            )
            reviewer_model = create_anthropic_model(
                api_key=self.settings.reviewer_key,
                model=self.settings.anthropic_model,
                max_tokens=self.settings.llm_reviewer_max_tokens,
                reasoning_effort=self.settings.llm_reasoning_effort,
            )
            reference_image = fit_image_payload(
                ImagePayload(reference["jpg"], "image/jpeg")
                if reference.get("jpg")
                else ImagePayload(reference["png"], "image/png")
                if reference.get("png")
                else ImagePayload(mcp_screenshot, "image/png")
                if mcp_screenshot
                else None,
                label="Figma design reference preview",
            )
            graph = ConversionGraph(
                generator=GeneratorAgent(generator_model, output_dir),
                reviewer=ReviewerAgent(reviewer_model),
                settings=self.settings,
                output_dir=output_dir,
                skip_review=skip_review,
            )
            state: WorkflowState = await graph.run(
                {
                    "context": context,
                    "files": {},
                    "review": None,
                    "iterations": [],
                    "iteration": 0,
                    "last_pixel_mismatch": None,
                    "reference_image": reference_image,
                    "reference_png": reference.get("png"),
                    "reference_scale": reference.get("renderScale", reference.get("pngScale", 1)),
                    "viewport_references": viewport_references,
                    "workflow_warnings": [],
                    "no_improvement_count": 0,
                }
            )
            component_map = self._component_map(state["files"], warnings)
            final_review = state.get("review")
            warnings.extend(state.get("workflow_warnings", []))
            accuracy_achieved = bool(state.get("accuracy_achieved"))
            visual_diagnostics = state.get("visual_diagnostics") or {}
            aggregate = visual_diagnostics.get("aggregate") or {}
            accuracy = {
                "mode": self.settings.accuracy_mode,
                "targetMismatchPct": self.settings.pixel_mismatch_target,
                "diffThreshold": self.settings.effective_pixel_diff_threshold,
                "converged": accuracy_achieved,
                "exact": bool(aggregate.get("exact")),
                "visualVerified": bool(aggregate.get("verified")),
                "stable": bool(aggregate.get("stable")),
                "stopReason": state.get("termination_reason"),
                "bestIteration": state.get("best_iteration"),
                "viewports": state.get("viewport_metrics", []),
                "responsiveAudit": state.get("responsive_audit", []),
                "geometry": state.get("geometry_diagnostics"),
            }
            contract_issues = state.get("contract_issues") or []
            report = {
                "design": {
                    "name": design_name,
                    "fileKey": self.settings.figma_file_key,
                    "nodeId": self.settings.node_id,
                    "source": "MCP + REST" if mcp else "REST",
                },
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "finalScore": final_review.score if final_review else None,
                "threshold": self.settings.match_threshold,
                "pixelMismatchPct": state.get("last_pixel_mismatch"),
                "iterations": state.get("iterations", []),
                "status": "accepted" if accuracy_achieved else "best-effort",
                "accuracy": accuracy,
                "contract": {
                    "passed": not contract_issues,
                    "violations": [issue.model_dump() for issue in contract_issues],
                },
                "componentMap": component_map,
                "assets": asset_manifest,
                "warnings": warnings,
                "remainingIssues": [issue.model_dump() for issue in final_review.issues] if final_review else [],
            }
            write_report(output_dir, report)
            if self.settings.strict_accuracy and not accuracy_achieved:
                raise AccuracyTargetNotMet(
                    output_dir,
                    state.get("last_pixel_mismatch"),
                    str(state.get("termination_reason") or "target_not_met"),
                )
            return output_dir
        finally:
            if mcp:
                await mcp.close()

    @staticmethod
    def _component_map(files: dict[str, str], warnings: list[str]) -> dict[str, Any] | None:
        try:
            component_map = json.loads(files.get("component-map.json", "null"))
            if not isinstance(component_map, dict) or not isinstance(component_map.get("mappings"), list):
                return None
            component_map["mappings"] = [item for item in component_map["mappings"] if isinstance(item, dict)]
            return component_map
        except json.JSONDecodeError:
            warnings.append("The generated component-map.json was invalid JSON.")
            return None

    @staticmethod
    async def _validate_strict_runtime(*, skip_review: bool, visual_diff: bool) -> None:
        if skip_review:
            raise RuntimeError("Strict accuracy requires the review/refinement loop.")
        if not visual_diff:
            raise RuntimeError("Strict accuracy requires visual diff rendering.")
        missing: list[str] = []
        try:
            import PIL  # noqa: F401
        except ImportError:
            missing.append("Pillow")
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            missing.append("Playwright")
        if missing:
            raise RuntimeError(
                "Strict accuracy requires the visual dependencies: "
                f"{', '.join(missing)}. Install with python -m pip install -e \".[visual]\"."
            )
        try:
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=True)
                await browser.close()
        except Exception as exc:
            raise RuntimeError(
                "Playwright Chromium could not launch for strict visual verification. "
                "Run `python -m playwright install chromium` and install any reported "
                "system browser dependencies."
            ) from exc
