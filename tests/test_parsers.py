from figma_to_sitecore.generation.parsers import parse_generated_files, parse_json_loose


def test_parse_generated_files() -> None:
    files = parse_generated_files(
        """===FILE: index.html===
```html
<main>Hello</main>
```
===FILE: css/styles.css===
body { color: red; }
===END===
ignored"""
    )
    assert files["index.html"] == "<main>Hello</main>\n"
    assert files["css/styles.css"].startswith("body")


def test_truncated_final_file_is_dropped() -> None:
    files = parse_generated_files("===FILE: index.html===\n<main>", truncated=True)
    assert files == {}


def test_parse_json_loose_skips_css_object() -> None:
    result = parse_json_loose('CSS: .x{} then ```json\n{"score": 99, "issues": []}\n```')
    assert result["score"] == 99

