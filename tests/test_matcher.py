from figma_to_sitecore.eds.matcher import match_sections, shortlisted_components


def test_matcher_prefers_hero_for_top_image_and_cta() -> None:
    root = {
        "name": "Page",
        "children": [
            {
                "name": "Hero",
                "frame": {"y": 0},
                "children": [
                    {"name": "Hero image", "asset": "a1"},
                    {"name": "CTA button", "text": {"content": "Start"}},
                ],
            }
        ],
    }
    components = [
        {"name": "hero-banner", "folder": "hero-banner", "keywords": ["hero"]},
        {"name": "card", "folder": "card", "keywords": ["card"]},
        {"name": "content-block", "folder": "content-block", "keywords": ["content"]},
    ]
    matches = match_sections(root, components)
    assert matches[0]["candidates"][0]["name"] == "hero-banner"
    assert any(item["name"] == "content-block" for item in shortlisted_components(matches, components))

