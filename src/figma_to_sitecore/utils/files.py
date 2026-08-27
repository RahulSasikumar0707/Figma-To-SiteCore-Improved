from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def write_file(path: Path, data: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")
    return path


def next_output_dir(root: Path, prefix: str = "Output") -> Path:
    """Atomically create and return the next ``<prefix>_<n>`` directory."""
    root.mkdir(parents=True, exist_ok=True)
    highest = 0
    marker = f"{prefix}_"
    for entry in root.iterdir():
        suffix = entry.name[len(marker) :] if entry.is_dir() and entry.name.startswith(marker) else ""
        if suffix.isdigit():
            highest = max(highest, int(suffix))

    number = highest + 1
    while True:
        candidate = root / f"{prefix}_{number}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            number += 1


def safe_file_name(name: str | None, extension: str, taken: set[str] | None = None) -> str:
    taken = taken if taken is not None else set()
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "asset").lower()).strip("-")[:60] or "asset"
    candidate = f"{base}.{extension}"
    number = 2
    while candidate in taken:
        candidate = f"{base}-{number}.{extension}"
        number += 1
    taken.add(candidate)
    return candidate


def read_json_if_exists(path: Path) -> Any | None:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return None
    return json.loads(raw)
