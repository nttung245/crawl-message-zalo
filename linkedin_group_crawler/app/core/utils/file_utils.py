"""Filesystem helper utilities."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def ensure_directory(path: Path) -> Path:
    """Ensure a directory exists and return it."""

    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json_file(path: Path, data: Any) -> Path:
    """Save JSON data to a file path."""

    ensure_directory(path.parent)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_json_file_overwrite(path: Path, data: Any) -> Path:
    """Ghi đè JSON tại đúng ``path`` — không đổi tên file đích; ghi file tạm rồi ``replace`` (atomic)."""

    ensure_directory(path.parent)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, path)
    except BaseException:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise
    return path


def save_text_file(path: Path, content: str) -> Path:
    """Save text content to a file path."""

    ensure_directory(path.parent)
    path.write_text(content, encoding="utf-8")
    return path
