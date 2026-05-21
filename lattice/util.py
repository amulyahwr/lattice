from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path


def _normalized_subject(subject: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", subject.lower()))


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        Path(tmp_name).replace(path)
    finally:
        tmp = Path(tmp_name)
        if tmp.exists():
            tmp.unlink()
