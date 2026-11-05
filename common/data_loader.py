"""YAML test-data loader with a small, explicit placeholder vocabulary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"

PLACEHOLDERS = {
    "LONG_101": "测" * 101,
    "LONG_51": "作" * 51,
    "KEYWORD_51": "a" * 51,
    "VALID_ISBN_10": "7115000001",
    "VALID_ISBN_13": "9787115000001",
}


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        for key, replacement in PLACEHOLDERS.items():
            value = value.replace("${" + key + "}", replacement)
        return value
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    return value


def load_data(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _expand(document)
