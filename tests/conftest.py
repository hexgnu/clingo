from __future__ import annotations

from pathlib import Path

import pytest

from compli.extract import extract
from compli.models import Rule
from compli.store import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "EIGuide-61[1].pdf"


@pytest.fixture(scope="session")
def extraction():
    """Parse the PDF once; it is the slowest thing in the suite."""
    if not PDF.exists():
        pytest.skip(f"source PDF not present at {PDF}")
    return extract(PDF)


@pytest.fixture(scope="session")
def clauses(extraction):
    return extraction[0]


@pytest.fixture(scope="session")
def source_warnings(extraction):
    return extraction[3]


@pytest.fixture(scope="session")
def clause_index(clauses):
    return {c.id: c for c in clauses}


@pytest.fixture(scope="session")
def golden_rules() -> list[Rule]:
    return read_jsonl(ROOT / "data" / "golden" / "chapter_d6.jsonl", Rule)


@pytest.fixture(scope="session")
def chapter_d_program(tmp_path_factory, clause_index, golden_rules) -> Path:
    """Compile the golden Chapter D rules once for the whole session."""
    from compli import compile as compile_mod

    source = compile_mod.compile_rules(golden_rules, clause_index, "D", "EIGuide", "6.0")
    path = tmp_path_factory.mktemp("rules") / "chapter_d.lp"
    path.write_text(source, encoding="utf-8")
    return path
