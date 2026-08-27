from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from pydantic import ValidationError

from figma_to_sitecore.application import (
    AccuracyTargetNotMet,
    ConversionApplication,
    StorybookUnavailable,
)
from figma_to_sitecore.config import Settings
from figma_to_sitecore.figma.client import FigmaApiError
from figma_to_sitecore.utils.logging import configure_logging, log


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="figma-sitecore",
        description="Convert a Figma node to Sitecore EDS using LangChain/LangGraph.",
    )
    parser.add_argument("--file-key", "--file", dest="file_key", help="Figma file key")
    parser.add_argument("--node", dest="node_id", help="Figma node id (12:34 or 12-34)")
    parser.add_argument("--source", choices=("auto", "mcp", "rest"), help="Figma source preference")
    parser.add_argument("--output-root", type=Path, help="Directory that receives Output_N folders")
    parser.add_argument("--skip-review", action="store_true", help="Generate once without the review graph loop")
    parser.add_argument("--no-visual-diff", action="store_true", help="Disable Playwright rendering and pixel diff")
    parser.add_argument(
        "--accuracy",
        choices=("standard", "strict"),
        help="Use strict decoded-pixel convergence or the standard reviewer gate",
    )
    parser.add_argument(
        "--pixel-target",
        type=float,
        help="Maximum allowed worst-viewport pixel mismatch percentage (strict default: 0)",
    )
    parser.add_argument(
        "--reference",
        action="append",
        default=[],
        metavar="WIDTH=NODE_ID",
        help="Add a Figma reference frame for an exact responsive viewport; repeat as needed",
    )
    parser.add_argument("--manifest-only", action="store_true", help="Rebuild eds-manifest.json and exit")
    parser.add_argument(
        "--refresh-storybook",
        action="store_true",
        help="Re-fetch EDS snippets from Storybook even when eds-manifest.json exists (corporate network only)",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser


async def _run(args: argparse.Namespace) -> int:
    try:
        base_settings = Settings(project_root=Path.cwd())
    except ValidationError as exc:
        log.error("Invalid configuration: %s", exc)
        return 2
    reference_nodes = dict(base_settings.figma_reference_nodes)
    for reference in args.reference:
        try:
            width, node_id = reference.split("=", 1)
            parsed_width = int(width.strip())
        except (TypeError, ValueError):
            log.error("Invalid --reference %r; expected WIDTH=NODE_ID", reference)
            return 2
        if parsed_width < 320:
            log.error("Invalid --reference %r; width must be at least 320px", reference)
            return 2
        if not node_id.strip():
            log.error("Invalid --reference %r; node id is empty", reference)
            return 2
        reference_nodes[str(parsed_width)] = node_id.strip()
    updates = {
        key: value
        for key, value in {
            "figma_file_key": args.file_key,
            "figma_node_id": args.node_id,
            "figma_source": args.source,
            "output_root": args.output_root,
            "visual_diff": False if args.no_visual_diff else None,
            "eds_storybook_refresh": True if args.refresh_storybook else None,
            "accuracy_mode": args.accuracy,
            "pixel_mismatch_target": args.pixel_target,
            "figma_reference_nodes": reference_nodes if args.reference else None,
        }.items()
        if value is not None
    }
    # Reconstruct rather than model_copy so numeric bounds and other Pydantic
    # validators also apply to CLI overrides.
    try:
        settings = Settings(project_root=Path.cwd(), **updates)
    except ValidationError as exc:
        log.error("Invalid command-line configuration: %s", exc)
        return 2
    errors = settings.validate_for_run(manifest_only=args.manifest_only, skip_review=args.skip_review)
    if errors:
        for error in errors:
            log.error(error)
        return 2
    application = ConversionApplication(settings)
    try:
        result = (
            await application.rebuild_manifest()
            if args.manifest_only
            else await application.convert(skip_review=args.skip_review)
        )
    except KeyboardInterrupt:
        log.warning("Cancelled")
        return 130
    except (FigmaApiError, StorybookUnavailable) as exc:
        log.error("%s", exc)
        return 1
    except AccuracyTargetNotMet as exc:
        log.error("%s", exc)
        return 3
    except Exception:
        log.exception("Conversion failed")
        return 1
    log.info("Done: %s", result)
    return 0


def main() -> None:
    args = build_parser().parse_args()
    configure_logging(args.verbose)
    sys.exit(asyncio.run(_run(args)))
