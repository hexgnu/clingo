"""Test structured error reporting."""

import json
from compli.errors import ErrorCode, StructuredError


def test_error_code_values():
    """Error codes are stable strings."""
    assert ErrorCode.FILE_NOT_FOUND.value == "E101"
    assert ErrorCode.SOLVER_UNSAT.value == "E301"
    assert ErrorCode.VERDICT_VIOLATIONS_FOUND.value == "E601"


def test_structured_error_to_dict():
    """Structured error serializes to JSON."""
    err = StructuredError(
        code=ErrorCode.SITE_INVALID_PREDICATE,
        message="Unknown predicate in site file",
        details={"predicate": "unknown_fact/2", "expected": "cell/2"},
        file_path="sites/test.lp",
        line=42,
    )

    d = err.to_dict()
    assert d["code"] == "E202"
    assert d["message"] == "Unknown predicate in site file"
    assert d["details"]["predicate"] == "unknown_fact/2"
    assert d["file"] == "sites/test.lp"
    assert d["line"] == 42

    # Should be JSON serializable
    json_str = json.dumps(d)
    assert "E202" in json_str


def test_structured_error_str():
    """Structured error has human-readable string."""
    err = StructuredError(
        code=ErrorCode.SOLVER_UNSAT,
        message="Constraints are unsatisfiable",
        details={"reason": "contradictory facts"},
        file_path="sites/broken.lp",
    )

    s = str(err)
    assert "[E301]" in s
    assert "unsatisfiable" in s
    assert "sites/broken.lp" in s
    assert "reason:" in s


def test_minimal_error():
    """Error works with just code and message."""
    err = StructuredError(
        code=ErrorCode.FILE_EMPTY,
        message="File is empty",
    )

    d = err.to_dict()
    assert d["code"] == "E102"
    assert d["message"] == "File is empty"
    assert "file" not in d
    assert "line" not in d
    assert "details" not in d
