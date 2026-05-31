from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


def _normalized_subject(subject: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", subject.lower()))


def write_file_atomic(path: Path, text: str) -> None:
    """Write *text* to *path* atomically via a temp-file rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        Path(tmp_name).replace(path)
    finally:
        tmp = Path(tmp_name)
        if tmp.exists():
            tmp.unlink()


def _write_json_atomic(path: Path, data: dict) -> None:
    write_file_atomic(path, json.dumps(data))
