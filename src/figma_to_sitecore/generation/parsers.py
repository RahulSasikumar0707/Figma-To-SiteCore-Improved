from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

FILE_DELIMITER = re.compile(r"^[^\S\n]*={3,}[^\S\n]*FILE:[^\S\n]*(.+?)[^\S\n]*={3,}[^\S\n]*$", re.I | re.M)
END_DELIMITER = re.compile(r"^[^\S\n]*={3,}[^\S\n]*END[^\S\n]*={3,}[^\S\n]*$", re.I | re.M)


def parse_generated_files(text: str, *, truncated: bool = False) -> dict[str, str]:
    end_match = END_DELIMITER.search(text)
    saw_end = bool(end_match)
    if end_match:
        text = text[: end_match.start()]
    matches = list(FILE_DELIMITER.finditer(text))
    files: dict[str, str] = {}
    for index, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if truncated and not saw_end and index == len(matches) - 1:
            continue
        content = text[start:end].strip()
        fence = re.fullmatch(r"```[a-z0-9_-]*\n([\s\S]*?)\n```", content, re.I)
        if fence:
            content = fence.group(1)
        files[name] = content + "\n"
    return files


def parse_json_loose(text: str) -> dict[str, Any]:
    fences = re.findall(r"```(json)?[^\S\n]*\n?([\s\S]*?)```", text, re.I)
    candidates = [body for label, body in sorted(fences, key=lambda item: bool(item[0]), reverse=True)] + [text]
    empty_fallback: dict[str, Any] | None = None
    for candidate in candidates:
        for object_text in _balanced_objects(candidate):
            try:
                parsed = json.loads(object_text)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed:
                return parsed
            if isinstance(parsed, dict) and empty_fallback is None:
                empty_fallback = parsed
    if empty_fallback is not None:
        return empty_fallback
    raise ValueError("No JSON object found in model response")


def _balanced_objects(text: str) -> Iterator[str]:
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start < 0:
            return
        depth = 0
        in_string = False
        escaped = False
        end = -1
        for cursor in range(start, len(text)):
            character = text[cursor]
            if escaped:
                escaped = False
                continue
            if character == "\\" and in_string:
                escaped = True
                continue
            if character == '"':
                in_string = not in_string
            elif not in_string:
                if character == "{":
                    depth += 1
                elif character == "}":
                    depth -= 1
                    if depth == 0:
                        end = cursor
                        break
        if end < 0:
            return
        yield text[start : end + 1]
        index = end + 1

