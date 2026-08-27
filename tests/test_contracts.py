from figma_to_sitecore.generation.contracts import (
    _strip_js_comments,
    contract_report,
    validate_generated_output,
)

_BOOTSTRAP_CSS = "https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css"
_BOOTSTRAP_JS = "https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"

_STYLES = "main{display:block}\n@media (min-width: 768px){main{display:flex}}\n"


def _html(body: str = "<main>hi</main>", head_extra: str = "") -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<link href="{_BOOTSTRAP_CSS}" rel="stylesheet" />
{head_extra}<link href="css/tokens.css" rel="stylesheet" />
<link href="css/styles.css" rel="stylesheet" />
</head>
<body>
{body}
<script src="{_BOOTSTRAP_JS}"></script>
<script src="js/script.js"></script>
</body>
</html>
"""


def _files(**overrides: str) -> dict[str, str]:
    files = {
        "index.html": _html(),
        "css/styles.css": _STYLES,
        "js/script.js": "(function(){})();\n",
        "component-map.json": '{"mappings":[]}\n',
    }
    files.update(overrides)
    return files


def _areas(files: dict[str, str], **kwargs) -> list[str]:
    return [issue.area for issue in validate_generated_output(files, **kwargs)]


def test_conforming_output_reports_nothing() -> None:
    issues = validate_generated_output(_files())
    assert issues == []
    assert contract_report(issues) == "All automated output-contract checks passed."


def test_inline_style_attribute_is_critical() -> None:
    files = _files(**{"index.html": _html('<main style="color:red">hi</main>')})
    issues = validate_generated_output(files)
    assert [issue.area for issue in issues] == ["css/inline"]
    assert issues[0].severity == "critical"


def test_internal_style_element_is_critical() -> None:
    files = _files(**{"index.html": _html("<style>main{color:red}</style><main>hi</main>")})
    assert "css/internal" in _areas(files)


def test_commented_out_markup_is_not_a_violation() -> None:
    """A commented example must not fail the build, and must not satisfy a requirement."""
    body = '<!-- <main style="color:red"></main> --><main>hi</main>'
    assert _areas(_files(**{"index.html": _html(body)})) == []

    commented_link = "<!-- <link href=\"css/styles.css\" rel=\"stylesheet\" /> -->\n"
    without_styles = _html().replace('<link href="css/styles.css" rel="stylesheet" />', commented_link)
    assert "css/wiring" in _areas(_files(**{"index.html": without_styles}))


def test_runtime_style_injection_counts_as_embedded_css() -> None:
    injected = "var s=document.createElement('style');document.head.appendChild(s);\n"
    assert "css/internal" in _areas(_files(**{"js/script.js": injected}))

    assert "css/inline" in _areas(_files(**{"js/script.js": "el.style.height = '0px';\n"}))
    # Reading a computed style, and equality comparisons, are not writes.
    assert _areas(_files(**{"js/script.js": "if (el.style.height === '0px') {}\n"})) == []


def test_prose_in_comments_does_not_trigger_the_jquery_check() -> None:
    assert _areas(_files(**{"js/script.js": "/* built without jQuery */\nvar a=1;\n"})) == []
    assert "js/jquery" in _areas(_files(**{"js/script.js": "$('.x').hide();\n"}))


def test_strip_js_comments_preserves_string_contents() -> None:
    source = '/* c */ var u = "http://a//b"; // trailing\nvar x = 1;'
    stripped = _strip_js_comments(source)
    assert '"http://a//b"' in stripped
    assert "trailing" not in stripped


def test_stylesheet_order_and_viewport_are_enforced() -> None:
    reordered = _html().replace(
        '<link href="css/tokens.css" rel="stylesheet" />\n<link href="css/styles.css" rel="stylesheet" />',
        '<link href="css/styles.css" rel="stylesheet" />\n<link href="css/tokens.css" rel="stylesheet" />',
    )
    assert "css/cascade" in _areas(_files(**{"index.html": reordered}))

    no_viewport = _html().replace(
        '<meta name="viewport" content="width=device-width, initial-scale=1.0" />\n', ""
    )
    assert "responsive/viewport" in _areas(_files(**{"index.html": no_viewport}))


def test_stylesheet_without_breakpoints_is_not_responsive() -> None:
    assert "responsive/breakpoints" in _areas(_files(**{"css/styles.css": "main{display:block}\n"}))
    assert "css/missing" in _areas(_files(**{"css/styles.css": "   \n"}))


def test_asset_paths_must_exist_and_be_used() -> None:
    manifest = [{"file": "assets/images/hero.png"}, {"file": "assets/icons/arrow.svg"}]
    body = '<img src="assets/images/hero.png" alt="Hero"><img src="assets/images/ghost.png" alt="">'
    areas = _areas(_files(**{"index.html": _html(body)}), asset_manifest=manifest)
    assert "assets/missing" in areas
    assert "assets/unused" in areas


def test_css_url_reference_counts_as_using_an_asset() -> None:
    manifest = [{"file": "assets/images/hero.png"}]
    styles = _STYLES + ".hero{background-image:url('../assets/images/hero.png')}\n"
    assert _areas(_files(**{"css/styles.css": styles}), asset_manifest=manifest) == []


def test_missing_alt_text_is_minor() -> None:
    manifest = [{"file": "assets/images/hero.png"}]
    body = '<img src="assets/images/hero.png">'
    issues = validate_generated_output(_files(**{"index.html": _html(body)}), asset_manifest=manifest)
    alt = [issue for issue in issues if issue.area == "assets/alt"]
    assert alt and alt[0].severity == "minor"


def test_mapped_eds_component_must_contribute_its_classes() -> None:
    components = [{"name": "hero-banner", "edsClasses": ["eds-native", "eds-hero-banner"]}]
    mapping = '{"mappings":[{"designSection":"Hero","edsComponent":"hero-banner"}]}'

    assert "eds/classes" in _areas(_files(**{"component-map.json": mapping}), components=components)

    used = _html('<div class="component eds-hero-banner">hi</div>')
    assert _areas(
        _files(**{"component-map.json": mapping, "index.html": used}),
        components=components,
    ) == []


def test_unknown_eds_component_is_reported() -> None:
    components = [{"name": "hero-banner", "edsClasses": ["eds-hero-banner"]}]
    mapping = '{"mappings":[{"designSection":"Hero","edsComponent":"invented-thing"}]}'
    assert "eds/unknown-component" in _areas(
        _files(**{"component-map.json": mapping}), components=components
    )


def test_invalid_component_map_json_is_reported() -> None:
    assert "eds/component-map" in _areas(_files(**{"component-map.json": "{not json"}))


def test_missing_required_file_is_reported() -> None:
    files = _files()
    files.pop("js/script.js")
    assert "output/files" in _areas(files)


def test_linked_eds_native_css_is_required_when_it_exists() -> None:
    assert "css/eds" in _areas(_files(), eds_native_available=True)
    with_eds = _html(head_extra='<link href="css/eds-native.css" rel="stylesheet" />\n')
    assert _areas(_files(**{"index.html": with_eds}), eds_native_available=True) == []


def test_geometry_hooks_must_carry_real_node_ids() -> None:
    """A layer-name hook looks right but matches nothing, blinding the audit."""
    known = {"1:2", "1:3"}

    named = _html('<section data-figma-id="Promo/hero banner">hi</section>')
    issues = validate_generated_output(_files(**{"index.html": named}), known_figma_ids=known)
    assert [issue.area for issue in issues] == ["geometry/hooks"]
    assert "Promo/hero banner" in issues[0].description

    real = _html('<section data-figma-id="1:2">hi</section>')
    assert _areas(_files(**{"index.html": real}), known_figma_ids=known) == []


def test_absent_geometry_hooks_are_reported() -> None:
    assert "geometry/hooks" in _areas(_files(), known_figma_ids={"1:2"})
    # With no design index there is nothing to validate against.
    assert _areas(_files()) == []


def test_fixed_height_with_hidden_overflow_is_flagged_as_clipping() -> None:
    styles = _STYLES + ".lv-footer{height:273.2px;overflow:hidden;}\n"
    issues = validate_generated_output(_files(**{"css/styles.css": styles}))
    assert [issue.area for issue in issues] == ["css/clipping"]
    assert ".lv-footer" in issues[0].description

    # Either declaration on its own is legitimate.
    assert _areas(_files(**{"css/styles.css": _STYLES + ".a{height:20px}\n"})) == []
    assert _areas(_files(**{"css/styles.css": _STYLES + ".a{overflow:hidden}\n"})) == []


def test_css_comments_are_not_read_as_selectors() -> None:
    styles = _STYLES + "/* footer exact */\n.lv-footer{height:12px;overflow:hidden;}\n"
    issues = validate_generated_output(_files(**{"css/styles.css": styles}))
    assert issues[0].description.count(".lv-footer") == 1
    assert "footer exact" not in issues[0].description


def test_classes_named_after_pixel_offsets_are_flagged() -> None:
    styles = _STYLES + ".x279{margin-left:279px}\n.x293{margin-left:293.2px}\n"
    issues = validate_generated_output(_files(**{"css/styles.css": styles}))
    assert [issue.area for issue in issues] == ["css/naming"]
    assert ".x279" in issues[0].description and ".x293" in issues[0].description


def test_ordinary_class_names_containing_digits_are_not_flagged() -> None:
    styles = _STYLES + ".h2-lead{font-size:38px}\n.col-md-6{width:50%}\n.br-30{border-radius:30px}\n"
    assert _areas(_files(**{"css/styles.css": styles})) == []
