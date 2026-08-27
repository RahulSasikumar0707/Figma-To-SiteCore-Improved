from __future__ import annotations

import json
import re
from typing import Any, Literal

from figma_to_sitecore.domain.models import ReviewIssue

# HTML comments must be stripped before scanning: a commented-out example is not
# a violation, and a commented-out <link> is not a satisfied requirement.
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_STYLE_BLOCK = re.compile(r"<style\b", re.I)
_INLINE_STYLE = re.compile(r"<([a-z][\w:-]*)\b[^>]*?\sstyle\s*=\s*[\"'][^\"']*[\"']", re.I)
_LINK_TAG = re.compile(r"<link\b[^>]*>", re.I)
_HREF = re.compile(r"\bhref\s*=\s*[\"']([^\"']+)[\"']", re.I)
_REL_STYLESHEET = re.compile(r"\brel\s*=\s*[\"']?[^\"'>]*stylesheet", re.I)
_SCRIPT_SRC = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)
_ASSET_REF = re.compile(r"\b(?:src|poster)\s*=\s*[\"'](assets/[^\"']+)[\"']", re.I)
_CSS_ASSET_REF = re.compile(r"url\(\s*[\"']?((?:\.\./)*assets/[^\"')]+)[\"']?\s*\)", re.I)
_IMG_TAG = re.compile(r"<img\b[^>]*>", re.I)
_ALT_ATTR = re.compile(r"\balt\s*=\s*[\"'][^\"']*[\"']", re.I)
_VIEWPORT_META = re.compile(r"<meta\b[^>]*\bname\s*=\s*[\"']viewport[\"']", re.I)
_CSS_IMPORT = re.compile(r"@import\b", re.I)
_MEDIA_QUERY = re.compile(r"@media\b", re.I)
_DATA_CSS_URI = re.compile(r"data:text/css", re.I)
_FIGMA_HOOK = re.compile(r"""\bdata-figma-id\s*=\s*["']([^"']*)["']""", re.I)

# Runtime style injection is inline/internal CSS with extra steps.
_JS_STYLE_INJECTION = (
    (re.compile(r"createElement\(\s*[\"'`]style[\"'`]\s*\)", re.I), "document.createElement('style')"),
    (re.compile(r"\.cssText\s*=", re.I), "style.cssText assignment"),
    (re.compile(r"setAttribute\(\s*[\"'`]style[\"'`]", re.I), "setAttribute('style', …)"),
    (re.compile(r"insertRule\s*\(", re.I), "CSSStyleSheet.insertRule"),
    (re.compile(r"adoptedStyleSheets", re.I), "document.adoptedStyleSheets"),
)
_JS_INLINE_STYLE_PROPERTY = re.compile(r"\.style\.[A-Za-z$_][\w$]*\s*=(?!=)")

# A class named after the pixel offset it applies (.x279, .mt-1273, .w826) encodes
# one measurement of one breakpoint into the selector and cannot be reused.
_COORDINATE_CLASS = re.compile(r"\.(?:[a-z]{0,3}-?)(?:x|y|w|h|mt|ml|mr|mb|top|left)?\d{3,4}\b", re.I)
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.S)
_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_DECL_HEIGHT = re.compile(r"(?<![\w-])height\s*:\s*([0-9.]+)px", re.I)
_DECL_OVERFLOW_HIDDEN = re.compile(r"overflow(?:-y)?\s*:\s*(?:hidden|clip)\b", re.I)

_REQUIRED_FILES = ("index.html", "css/styles.css", "js/script.js", "component-map.json")


def _strip_comments(markup: str) -> str:
    return _COMMENT.sub(" ", markup)


def _strip_js_comments(source: str) -> str:
    """Remove JS comments so prose like "no jQuery" is not read as code.

    A small hand-rolled scanner rather than a regex: it has to know when it is
    inside a string or template literal, otherwise a URL's ``//`` truncates the
    rest of the line.
    """
    output: list[str] = []
    index = 0
    length = len(source)
    quote: str | None = None
    while index < length:
        character = source[index]
        if quote:
            output.append(character)
            if character == "\\" and index + 1 < length:
                output.append(source[index + 1])
                index += 2
                continue
            if character == quote:
                quote = None
            index += 1
            continue
        if character in "\"'`":
            quote = character
            output.append(character)
            index += 1
            continue
        if source.startswith("//", index):
            end = source.find("\n", index)
            index = length if end < 0 else end
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            index = length if end < 0 else end + 2
            output.append(" ")
            continue
        output.append(character)
        index += 1
    return "".join(output)


def _stylesheet_hrefs(markup: str) -> list[str]:
    hrefs: list[str] = []
    for tag in _LINK_TAG.findall(markup):
        if not _REL_STYLESHEET.search(tag):
            continue
        match = _HREF.search(tag)
        if match:
            hrefs.append(match.group(1).strip())
    return hrefs


Severity = Literal["critical", "major", "minor"]


def _issue(severity: Severity, area: str, description: str, fix: str) -> ReviewIssue:
    return ReviewIssue(severity=severity, area=area, description=description, fix=fix)


def _check_no_embedded_css(html: str) -> list[ReviewIssue]:
    """Requirement: every style rule lives in a linked stylesheet."""
    issues: list[ReviewIssue] = []
    inline = _INLINE_STYLE.findall(html)
    if inline:
        sample = ", ".join(f"<{tag}>" for tag in dict.fromkeys(inline[:6]))
        issues.append(
            _issue(
                "critical",
                "css/inline",
                f"index.html contains {len(inline)} inline style attribute(s) on {sample}. "
                "Inline CSS is forbidden.",
                "Delete every style=\"…\" attribute and move the declarations into a class "
                "rule in css/styles.css.",
            )
        )
    if _STYLE_BLOCK.search(html):
        issues.append(
            _issue(
                "critical",
                "css/internal",
                "index.html contains a <style> block. Internal CSS is forbidden.",
                "Delete the <style> element and move every rule into css/styles.css.",
            )
        )
    if _DATA_CSS_URI.search(html):
        issues.append(
            _issue(
                "critical",
                "css/internal",
                "index.html links a data:text/css stylesheet, which is embedded CSS.",
                "Serve the rules from css/styles.css instead.",
            )
        )
    return issues


def _check_stylesheet_wiring(html: str, *, eds_native_available: bool) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    hrefs = _stylesheet_hrefs(html)
    lowered = [href.lower() for href in hrefs]

    def has(fragment: str) -> bool:
        return any(fragment in href for href in lowered)

    if not has("bootstrap"):
        issues.append(
            _issue(
                "critical",
                "css/bootstrap",
                "No Bootstrap stylesheet is linked; the output cannot be a Bootstrap page.",
                "Link the Bootstrap 5 stylesheet in <head> before the project stylesheets.",
            )
        )
    for required in ("css/tokens.css", "css/styles.css"):
        if required not in lowered:
            issues.append(
                _issue(
                    "critical",
                    "css/wiring",
                    f"{required} is not linked from index.html.",
                    f'Add <link href="{required}" rel="stylesheet" /> in <head>.',
                )
            )
    if eds_native_available and not has("eds-native.css"):
        issues.append(
            _issue(
                "major",
                "css/eds",
                "css/eds-native.css exists in the output but is not linked.",
                'Link css/eds-native.css after Bootstrap and before css/styles.css.',
            )
        )
    if "css/styles.css" in lowered and lowered[-1] != "css/styles.css":
        issues.append(
            _issue(
                "major",
                "css/cascade",
                f"css/styles.css is not the last stylesheet (order: {', '.join(hrefs)}). "
                "Component overrides will lose to Bootstrap and EDS.",
                "Move the css/styles.css <link> below every other stylesheet link.",
            )
        )
    if not _VIEWPORT_META.search(html):
        issues.append(
            _issue(
                "critical",
                "responsive/viewport",
                "The responsive viewport meta tag is missing; the page cannot adapt on mobile.",
                'Add <meta name="viewport" content="width=device-width, initial-scale=1.0" /> to <head>.',
            )
        )
    return issues


def _check_scripts(html: str, javascript: str) -> list[ReviewIssue]:
    javascript = _strip_js_comments(javascript)
    issues: list[ReviewIssue] = []
    sources = [source.lower() for source in _SCRIPT_SRC.findall(html)]
    if not any("bootstrap" in source for source in sources):
        issues.append(
            _issue(
                "major",
                "bootstrap/js",
                "The Bootstrap bundle script is not included, so data-bs-* behaviour will not work.",
                "Add the Bootstrap 5 bundle <script> before </body>.",
            )
        )
    if "js/script.js" not in sources:
        issues.append(
            _issue(
                "major",
                "js/wiring",
                "js/script.js is not referenced from index.html.",
                'Add <script src="js/script.js"></script> before </body>.',
            )
        )
    if re.search(r"\$\(|jQuery", javascript):
        issues.append(
            _issue("major", "js/jquery", "js/script.js uses jQuery.", "Rewrite the behaviour with the DOM API.")
        )
    for pattern, label in _JS_STYLE_INJECTION:
        if pattern.search(javascript):
            issues.append(
                _issue(
                    "critical",
                    "css/internal",
                    f"js/script.js injects CSS at runtime via {label}, which reintroduces internal CSS.",
                    "Declare the rule in css/styles.css and toggle a class from JavaScript instead.",
                )
            )
    if _JS_INLINE_STYLE_PROPERTY.search(javascript):
        issues.append(
            _issue(
                "major",
                "css/inline",
                "js/script.js assigns element.style.* properties, which writes inline CSS into the DOM.",
                "Move the declarations into css/styles.css and toggle a class with classList instead.",
            )
        )
    return issues


def _check_geometry_hooks(html: str, known_ids: set[str]) -> list[ReviewIssue]:
    """The geometry audit is blind unless the hooks carry real Figma node ids.

    A layer name looks plausible in the markup but matches nothing, so the whole
    per-element measurement silently degrades to a single page-height number.
    """
    if not known_ids:
        return []
    hooks = [value.strip() for value in _FIGMA_HOOK.findall(html)]
    if not hooks:
        return [
            _issue(
                "major",
                "geometry/hooks",
                "No data-figma-id attributes were emitted, so no element can be measured "
                "against its Figma box.",
                "Add data-figma-id=\"<node id>\" to every top-level section, card, media block, "
                "the header and the footer, using the id field from the design spec.",
            )
        ]
    unknown = [value for value in dict.fromkeys(hooks) if value not in known_ids]
    if unknown:
        return [
            _issue(
                "major",
                "geometry/hooks",
                f"{len(unknown)} of {len(set(hooks))} data-figma-id value(s) are not Figma node ids "
                f"and cannot be measured: " + ", ".join(repr(value) for value in unknown[:6]),
                "Use the literal id field from the design spec (for example 68226:5173), "
                "not the layer name.",
            )
        ]
    return []


def _check_css(styles: str) -> list[ReviewIssue]:
    issues: list[ReviewIssue] = []
    if not styles.strip():
        issues.append(
            _issue(
                "critical",
                "css/missing",
                "css/styles.css is empty, so no component styling exists.",
                "Write the complete component stylesheet.",
            )
        )
        return issues
    if _CSS_IMPORT.search(styles):
        issues.append(
            _issue(
                "major",
                "css/import",
                "css/styles.css uses @import, which serializes CSS downloads and hides dependencies.",
                "Remove @import and link the stylesheet from index.html instead.",
            )
        )
    if not _MEDIA_QUERY.search(styles):
        issues.append(
            _issue(
                "critical",
                "responsive/breakpoints",
                "css/styles.css contains no @media rule, so the layout cannot be responsive.",
                "Author mobile-first base rules plus min-width breakpoints for tablet and desktop.",
            )
        )
    return issues


def _clipping_rules(styles: str) -> list[str]:
    """Selectors that pair a fixed pixel height with a hidden overflow.

    Together those two declarations cut content off instead of letting the box
    grow, which is how a layout is forced to match a Figma height. It survives
    only while the copy and the fonts never change.
    """
    found: list[str] = []
    for selector, body in _RULE.findall(_CSS_COMMENT.sub(" ", styles)):
        if _DECL_HEIGHT.search(body) and _DECL_OVERFLOW_HIDDEN.search(body):
            cleaned = " ".join(selector.split())
            if cleaned and not cleaned.startswith("@"):
                found.append(cleaned)
    return found


def _check_css_maintainability(styles: str) -> list[ReviewIssue]:
    styles = _CSS_COMMENT.sub(" ", styles)
    issues: list[ReviewIssue] = []
    clipping = _clipping_rules(styles)
    if clipping:
        issues.append(
            _issue(
                "major",
                "css/clipping",
                f"{len(clipping)} rule(s) combine a fixed pixel height with a hidden overflow, "
                "so content is cut off rather than allowed to grow: "
                + ", ".join(clipping[:6]),
                "Let the box size to its content and reproduce the design height with padding "
                "and spacing. A Sitecore component receives content of varying length.",
            )
        )
    named = sorted(
        {
            " ".join(selector.split())
            for selector, _ in _RULE.findall(styles)
            if _COORDINATE_CLASS.search(selector)
        }
    )
    if named:
        issues.append(
            _issue(
                "minor",
                "css/naming",
                f"{len(named)} selector(s) are named after a pixel measurement: "
                + ", ".join(named[:6]),
                "Name classes for the role they play, not the offset they happen to apply, "
                "so the rule survives a design change.",
            )
        )
    return issues


def _check_assets(html: str, styles: str, asset_manifest: list[dict[str, Any]]) -> list[ReviewIssue]:
    known = {str(asset.get("file", "")).replace("\\", "/").lower() for asset in asset_manifest}
    if not known:
        return []
    referenced: set[str] = {path.replace("\\", "/") for path in _ASSET_REF.findall(html)}
    referenced |= {
        re.sub(r"^(?:\.\./)+", "", path).replace("\\", "/") for path in _CSS_ASSET_REF.findall(styles)
    }
    invented = sorted(path for path in referenced if path.lower() not in known)
    issues: list[ReviewIssue] = []
    if invented:
        issues.append(
            _issue(
                "critical",
                "assets/missing",
                "These asset paths do not exist and will render as broken images: "
                + ", ".join(invented[:8]),
                "Use only the exact file paths listed in the asset manifest.",
            )
        )
    unused = sorted(path for path in known if path not in {item.lower() for item in referenced})
    if unused:
        issues.append(
            _issue(
                "major",
                "assets/unused",
                f"{len(unused)} exported asset(s) are never referenced, so part of the design is missing: "
                + ", ".join(unused[:8]),
                "Place every exported asset in the markup, or explain why the design does not show it.",
            )
        )
    missing_alt = [tag for tag in _IMG_TAG.findall(html) if not _ALT_ATTR.search(tag)]
    if missing_alt:
        issues.append(
            _issue(
                "minor",
                "assets/alt",
                f"{len(missing_alt)} <img> element(s) have no alt attribute.",
                'Add descriptive alt text, or alt="" for purely decorative images.',
            )
        )
    return issues


def _check_eds_mapping(
    html: str,
    component_map_json: str,
    components: list[dict[str, Any]],
) -> list[ReviewIssue]:
    """Requirement: the markup really uses the EDS components it claims to use."""
    try:
        parsed = json.loads(component_map_json or "null")
    except json.JSONDecodeError:
        return [
            _issue(
                "major",
                "eds/component-map",
                "component-map.json is not valid JSON, so the EDS mapping cannot be verified.",
                'Emit {"mappings":[{"designSection":…,"edsComponent":…,"modifiers":[…],'
                '"confidence":…,"notes":…}]}.',
            )
        ]
    if not isinstance(parsed, dict) or not isinstance(parsed.get("mappings"), list):
        return [
            _issue(
                "major",
                "eds/component-map",
                "component-map.json has no mappings array.",
                'Emit {"mappings":[…]} listing every design section and its EDS component.',
            )
        ]

    by_name = {
        str(component.get("name") or component.get("folder") or "").lower(): component
        for component in components
    }
    issues: list[ReviewIssue] = []
    unknown: list[str] = []
    unused_classes: list[str] = []
    lowered_html = html.lower()
    for mapping in parsed["mappings"]:
        if not isinstance(mapping, dict):
            continue
        name = str(mapping.get("edsComponent") or "").strip()
        if not name:
            continue
        component = by_name.get(name.lower())
        if component is None:
            unknown.append(name)
            continue
        classes = [str(value) for value in (component.get("edsClasses") or []) if str(value).strip()]
        specific = [value for value in classes if value.lower() != "eds-native"]
        if specific and not any(f"{value.lower()}" in lowered_html for value in specific):
            unused_classes.append(f"{name} ({'/'.join(specific)})")
    if unknown:
        issues.append(
            _issue(
                "major",
                "eds/unknown-component",
                "component-map.json names components that are not in the EDS catalog: "
                + ", ".join(dict.fromkeys(unknown)),
                "Map each section to a component from the supplied EDS catalog, or drop the mapping.",
            )
        )
    if unused_classes:
        issues.append(
            _issue(
                "major",
                "eds/classes",
                "These mapped EDS components contribute no EDS class to the markup: "
                + ", ".join(unused_classes[:6]),
                "Apply the component's canonical EDS classes and inner structure in index.html.",
            )
        )
    return issues


def validate_generated_output(
    files: dict[str, str],
    *,
    asset_manifest: list[dict[str, Any]] | None = None,
    components: list[dict[str, Any]] | None = None,
    eds_native_available: bool = False,
    known_figma_ids: set[str] | None = None,
) -> list[ReviewIssue]:
    """Check the hard, machine-verifiable half of the delivery contract.

    These are the requirements that must not depend on a model's judgement:
    externalized CSS, working Bootstrap/EDS wiring, real asset paths, and a
    responsive stylesheet. Findings are returned as review issues so the
    refinement loop repairs them exactly like model-reported defects.
    """
    issues: list[ReviewIssue] = []
    missing = [name for name in _REQUIRED_FILES if not (files.get(name) or "").strip()]
    if missing:
        issues.append(
            _issue(
                "critical",
                "output/files",
                f"Missing generated file(s): {', '.join(missing)}.",
                "Return every required file complete in its own ===FILE: …=== block.",
            )
        )
    raw_html = files.get("index.html") or ""
    html = _strip_comments(raw_html)
    styles = files.get("css/styles.css") or ""
    javascript = files.get("js/script.js") or ""
    if html.strip():
        issues.extend(_check_no_embedded_css(html))
        issues.extend(_check_stylesheet_wiring(html, eds_native_available=eds_native_available))
        issues.extend(_check_scripts(html, javascript))
        issues.extend(_check_assets(html, styles, asset_manifest or []))
        issues.extend(
            _check_eds_mapping(html, files.get("component-map.json") or "", components or [])
        )
        issues.extend(_check_geometry_hooks(html, known_figma_ids or set()))
    issues.extend(_check_css(styles))
    issues.extend(_check_css_maintainability(styles))
    return issues


def contract_report(issues: list[ReviewIssue]) -> str:
    if not issues:
        return "All automated output-contract checks passed."
    return "\n".join(f"- [{issue.severity}] {issue.area}: {issue.description} → {issue.fix}" for issue in issues)
