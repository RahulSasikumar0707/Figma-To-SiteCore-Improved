from figma_to_sitecore.figma.normalizer import (
    compact_spec,
    geometry_index,
    normalize_design,
    rgba_to_hex,
    text_inventory,
)


def test_rgba_to_hex_includes_alpha() -> None:
    assert rgba_to_hex({"r": 1, "g": 0.5, "b": 0, "a": 0.5}) == "#ff800080"


def test_normalizer_extracts_layout_text_and_assets() -> None:
    design = normalize_design(
        {
            "id": "1:1",
            "name": "Page",
            "type": "FRAME",
            "layoutMode": "VERTICAL",
            "itemSpacing": 24,
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 1440, "height": 900},
            "children": [
                {
                    "id": "1:2",
                    "name": "Title",
                    "type": "TEXT",
                    "characters": "Hello",
                    "style": {"fontFamily": "Inter", "fontSize": 32, "fontWeight": 700, "lineHeightPx": 40},
                    "fills": [{"type": "SOLID", "color": {"r": 0, "g": 0, "b": 0}}],
                    "absoluteBoundingBox": {"x": 10, "y": 10, "width": 100, "height": 40},
                },
                {
                    "id": "1:3",
                    "name": "Photo",
                    "type": "RECTANGLE",
                    "fills": [{"type": "IMAGE", "imageRef": "ref-1", "scaleMode": "FILL"}],
                    "absoluteBoundingBox": {"x": 10, "y": 60, "width": 400, "height": 250},
                },
                {
                    "id": "1:4",
                    "name": "Arrow icon",
                    "type": "VECTOR",
                    "absoluteBoundingBox": {"x": 20, "y": 320, "width": 24, "height": 24},
                },
            ],
        }
    )
    assert design["root"]["layout"]["mode"] == "column"
    assert design["root"]["children"][0]["text"]["content"] == "Hello"
    assert {asset["kind"] for asset in design["assets"]} == {"image", "icon"}
    assert design["tokens"]["fontFamilies"] == ["Inter"]
    assert 24 in design["tokens"]["spacingScale"]
    assert design["root"]["children"][0]["id"] == "1:2"
    assert design["root"]["children"][0]["abs"] == {"x": 10.0, "y": 10.0}
    assert len(compact_spec(design["root"], 100_000)) <= 100_000


def test_compact_spec_sheds_depth_before_exceeding_its_budget() -> None:
    node: dict = {
        "id": "1:40",
        "name": "Leaf",
        "type": "FRAME",
        "absoluteBoundingBox": {"x": 0, "y": 0, "width": 10, "height": 10},
    }
    for level in range(39, 0, -1):
        node = {
            "id": f"1:{level}",
            "name": f"Level {level}",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 10, "height": 10},
            "children": [node],
        }
    root = normalize_design(node)["root"]
    clipped = compact_spec(root, 1_000)
    assert "descendant nodes omitted" in clipped
    assert len(clipped) <= 1_000


def test_compact_spec_never_truncates_design_copy() -> None:
    """Shortened copy reads as finished copy, so the model invents the rest."""
    body = "Important safety information. " * 60
    design = normalize_design(
        {
            "id": "1:1",
            "name": "Page",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 0, "y": 0, "width": 600, "height": 400},
            "children": [
                {
                    "id": "1:2",
                    "name": "ISI",
                    "type": "TEXT",
                    "characters": body,
                    "style": {"fontFamily": "Inter", "fontSize": 14},
                    "absoluteBoundingBox": {"x": 0, "y": 0, "width": 600, "height": 400},
                }
            ],
        }
    )
    assert body in compact_spec(design["root"], 50)
    inventory = text_inventory(design["root"])
    assert [item["content"] for item in inventory] == [body]
    assert inventory[0]["id"] == "1:2"


def test_geometry_index_maps_node_ids_to_absolute_boxes() -> None:
    design = normalize_design(
        {
            "id": "1:1",
            "name": "Page",
            "type": "FRAME",
            "absoluteBoundingBox": {"x": 100, "y": 200, "width": 1440, "height": 900},
            "children": [
                {
                    "id": "1:2",
                    "name": "Hero",
                    "type": "FRAME",
                    "absoluteBoundingBox": {"x": 100, "y": 300, "width": 1440, "height": 400},
                },
                {
                    "id": "1:3",
                    "name": "Hairline",
                    "type": "RECTANGLE",
                    "absoluteBoundingBox": {"x": 100, "y": 700, "width": 1440, "height": 1},
                },
            ],
        }
    )
    index = geometry_index(design["root"])
    assert index["1:2"] == {
        "id": "1:2",
        "name": "Hero",
        "type": "FRAME",
        "x": 0.0,
        "y": 100.0,
        "w": 1440.0,
        "h": 400.0,
    }
    # Hairlines carry no layout signal and would only add noise.
    assert "1:3" not in index


def test_hidden_root_normalizes_to_none() -> None:
    result = normalize_design({"id": "1", "name": "Hidden", "type": "FRAME", "visible": False})
    assert result["root"] is None
