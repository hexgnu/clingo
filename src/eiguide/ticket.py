"""The inbound contract: a ticket from someone else's system.

Samsung's NMS, OneVizion, and a state 811 centre all speak their own vocabulary, on their
own schedule, with their own idea of how sure they are. None of them are going to write
ASP. This module is the boundary: JSON in, facts out, with two rules that matter more than
the schema itself.

**Provenance survives.** Every fact carries the system that asserted it, how confident that
system was, and when it was last touched. The trust layer needs all three to decide whether
a row is good enough to act on, and none of them can be recovered later if they are dropped
at the door.

**Nothing is silently discarded.** A vendor alarm code the knowledge base has never seen is
the dangerous case: drop it and the ticket comes back "no explanation covers the reported
symptoms", which reads as a confident negative rather than an admission that we did not
understand the input. Unrecognized codes are passed through as facts so the solver can see
them, refuse to declare the ticket solved, and say so.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel, Field

# ASP constants: lowercase, word characters only.
_SAFE = re.compile(r"[^a-z0-9_]")


def asp_id(value: str) -> str:
    """Coerce an external identifier into a legal ASP constant."""
    slug = _SAFE.sub("_", value.strip().lower()).strip("_")
    slug = re.sub(r"_+", "_", slug) or "unknown"
    return slug if slug[0].isalpha() else f"x_{slug}"


def asp_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class InboundAlarm(BaseModel):
    """An alarm exactly as the originating system worded it."""

    code: str  # vendor code, e.g. "LOS-A1" — deliberately NOT normalized here
    raised_day: int | None = None
    severity: str | None = None
    detail: str | None = None


class SourceFact(BaseModel):
    """Something a system of record claims about the asset.

    ``confidence`` and ``as_of_day`` are what let a stale or shaky row be treated as
    unverified rather than as truth. A source that cannot supply them should say so
    explicitly rather than defaulting to certainty.
    """

    source: str
    fact: str
    confidence: int = Field(ge=0, le=100)
    as_of_day: int
    negated: bool = False
    """True when this source asserts the fact is NOT so. Two sources disagreeing is more
    informative than either alone, and the trust layer treats it as evidence of an
    unreliable record."""


class Ticket(BaseModel):
    """The unit of work handed to the solver."""

    ticket_id: str
    source: str  # the system that raised it, e.g. "samsung_nms"
    kind: str = "alarm"  # alarm | dig_notice | maintenance
    received_day: int
    asset_id: str
    asset_vendor_ref: str | None = None
    alarms: list[InboundAlarm] = Field(default_factory=list)
    facts: list[SourceFact] = Field(default_factory=list)
    stale_after_days: int = 90
    min_confidence: int = 80

    @classmethod
    def load(cls, path: Path) -> Ticket:
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def to_asp(self) -> str:
        """Render the ticket as facts, preserving vendor wording verbatim.

        Alarm codes stay as strings in their original form. Translating them here would
        put the vendor mapping in Python, where adding a new alarm type means a code
        change; leaving it to the knowledge base keeps it data, and keeps unmapped codes
        visible to the reasoner rather than to a stack trace.
        """
        tid = asp_id(self.ticket_id)
        asset = asp_id(self.asset_id)
        src = asp_id(self.source)
        lines = [
            f"% ingested from {self.source}: {self.ticket_id}",
            f"ticket({tid}).",
            f"ticket_kind({tid}, {asp_id(self.kind)}).",
            f"asset({asset}).",
            f"ticket_asset({tid}, {asset}).",
            f"today({self.received_day}).",
            f"stale_after({self.stale_after_days}).",
            f"min_confidence({self.min_confidence}).",
        ]
        for alarm in self.alarms:
            lines.append(f"raw_alarm({src}, {asp_str(alarm.code)}).")
            if alarm.severity:
                lines.append(f"alarm_severity({asp_str(alarm.code)}, {asp_id(alarm.severity)}).")
        for fact in self.facts:
            term = f"neg({asp_id(fact.fact)})" if fact.negated else asp_id(fact.fact)
            lines.append(
                f"claim({asp_id(fact.source)}, {term}, {fact.confidence}, {fact.as_of_day})."
            )
        return "\n".join(lines)


class TriageResult(BaseModel):
    """What goes back to the originating system.

    Deliberately shaped so an unsolved ticket is as actionable as a solved one: the caller
    gets the reason it is open and the cheapest work that would close it, not an empty
    answer.
    """

    ticket_id: str
    solved: bool
    candidates: list[str] = Field(default_factory=list)
    provisional: list[str] = Field(default_factory=list)
    eliminated: list[str] = Field(default_factory=list)
    next_tests: list[str] = Field(default_factory=list)
    verify_records: list[str] = Field(default_factory=list)
    unrecognized_codes: list[str] = Field(default_factory=list)
    indistinguishable: list[tuple[str, str]] = Field(default_factory=list)
    open_reasons: list[str] = Field(default_factory=list)
    recommended: list[str] = Field(default_factory=list)
    truck_roll: bool = False
    plan_cost: int = 0

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), indent=2)
