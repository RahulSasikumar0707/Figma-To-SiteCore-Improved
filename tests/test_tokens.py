from figma_to_sitecore.tokens.builder import build_design_tokens


def test_build_design_tokens_and_escape_variable_values() -> None:
    css, token_map = build_design_tokens(
        {
            "palette": [{"hex": "#ffffff", "count": 3}],
            "fontFamilies": ["Inter"],
            "textStyles": [{"size": 16, "lineHeight": 24}],
            "spacingScale": [8],
            "radii": [4],
            "shadows": ["0px 2px 4px 0px #00000033"],
        },
        {"unsafe": "red;} body { display:none"},
    )
    assert "--fig-color-primary: #ffffff" in css
    assert '--fig-var-unsafe: "red;} body { display:none";' in css
    assert token_map["colors"]["#ffffff"] == "--fig-color-primary"

