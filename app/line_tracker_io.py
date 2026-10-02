from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text_atomic(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    temporary_path: str | None = None
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=encoding,
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary:
            temporary.write(text)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = temporary.name
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and os.path.exists(temporary_path):
            try:
                os.unlink(temporary_path)
            except OSError:
                pass
