"""JSONL persistence for the artifacts passed between stages.

One record per line, so a partially-written run is still readable and a reviewer can diff
two extraction runs with ordinary text tools.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterable
from pathlib import Path

from pydantic import BaseModel


def write_jsonl(path: Path, records: Iterable[BaseModel]) -> int:
    """Write records to JSONL file using atomic write pattern.

    Writes to a temporary file first, then renames to final path. This ensures
    partial writes don't leave corrupted files - either the full file is written
    or the original remains unchanged.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    # Write to temp file in same directory (required for atomic rename)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as tmp:
        tmp_path = Path(tmp.name)
        try:
            n = 0
            for record in records:
                tmp.write(record.model_dump_json() + "\n")
                n += 1
            tmp.flush()  # Ensure all data written to disk

            # Atomic rename (overwrites destination on Unix)
            tmp_path.replace(path)
            return n
        except Exception:
            # Clean up temp file on failure
            tmp_path.unlink(missing_ok=True)
            raise


def read_jsonl[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        return []
    out: list[T] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(model.model_validate_json(line))
    return out


def write_json(path: Path, record: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.model_dump(), indent=2) + "\n", encoding="utf-8")
