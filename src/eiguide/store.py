"""JSONL persistence for the artifacts passed between stages.

One record per line, so a partially-written run is still readable and a reviewer can diff
two extraction runs with ordinary text tools.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterable
from pathlib import Path

from loguru import logger
from pydantic import BaseModel


def write_jsonl(path: Path, records: Iterable[BaseModel]) -> int:
    """Write records to JSONL file using atomic write pattern.

    Writes to a temporary file first, then renames to final path. This ensures
    partial writes don't leave corrupted files - either the full file is written
    or the original remains unchanged.
    """
    logger.debug(f"Writing JSONL to {path}")
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
        logger.debug(f"Writing to temporary file: {tmp_path}")
        try:
            n = 0
            for record in records:
                tmp.write(record.model_dump_json() + "\n")
                n += 1
                if n % 100 == 0:
                    logger.debug(f"Written {n} records...")
            tmp.flush()  # Ensure all data written to disk
            logger.debug(f"Flushed {n} records to disk")

            # Atomic rename (overwrites destination on Unix)
            tmp_path.replace(path)
            logger.debug(f"Atomically renamed {tmp_path} -> {path}")
            return n
        except Exception as e:
            # Clean up temp file on failure
            logger.error(f"Write failed, cleaning up temporary file: {e}")
            tmp_path.unlink(missing_ok=True)
            raise


def read_jsonl[T: BaseModel](path: Path, model: type[T]) -> list[T]:
    if not path.exists():
        logger.debug(f"JSONL file does not exist: {path}")
        return []
    logger.debug(f"Reading JSONL from {path}")
    out: list[T] = []
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                out.append(model.model_validate_json(line))
            if i % 100 == 0:
                logger.debug(f"Read {i} lines...")
    logger.debug(f"Loaded {len(out)} records from {path}")
    return out


def write_json(path: Path, record: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record.model_dump(), indent=2) + "\n", encoding="utf-8")
