"""Error codes and structured error reporting for machine-readable output."""

from __future__ import annotations

from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    """Machine-readable error codes for automation."""

    # File errors (1xx)
    FILE_NOT_FOUND = "E101"
    FILE_EMPTY = "E102"
    FILE_INVALID = "E103"

    # Site validation errors (2xx)
    SITE_MISSING_DECLARATION = "E201"
    SITE_INVALID_PREDICATE = "E202"
    SITE_TYPE_MISMATCH = "E203"
    SITE_POOLING_ERROR = "E204"

    # Solver errors (3xx)
    SOLVER_UNSAT = "E301"
    SOLVER_NO_MODELS = "E302"
    SOLVER_GROUNDING_FAILED = "E303"
    SOLVER_EXECUTION_FAILED = "E304"

    # Compilation errors (4xx)
    COMPILE_SYNTAX_ERROR = "E401"
    COMPILE_EXEMPTION_FAILED = "E402"
    COMPILE_CITATION_INVALID = "E403"

    # Observation errors (5xx)
    OBS_UNKNOWN_OBSERVABLE = "E501"
    OBS_VALIDATION_FAILED = "E502"

    # Verdict errors (6xx)
    VERDICT_VIOLATIONS_FOUND = "E601"
    VERDICT_UNDETERMINED = "E602"


class StructuredError:
    """Structured error for machine-readable output."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        file_path: str | None = None,
        line: int | None = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}
        self.file_path = file_path
        self.line = line

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.details:
            d["details"] = self.details
        if self.file_path:
            d["file"] = self.file_path
        if self.line is not None:
            d["line"] = self.line
        return d

    def __str__(self) -> str:
        """Human-readable error message."""
        parts = [f"[{self.code.value}] {self.message}"]
        if self.file_path:
            location = self.file_path
            if self.line is not None:
                location += f":{self.line}"
            parts.append(f"  at {location}")
        if self.details:
            for key, value in self.details.items():
                parts.append(f"  {key}: {value}")
        return "\n".join(parts)
