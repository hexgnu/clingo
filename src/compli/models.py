"""Typed records passed between pipeline stages.

Three layers, deliberately kept separate:

``Clause``    verbatim text lifted from the PDF plus provenance. Generated, never hand-edited.
``Rule``      structured interpretation of a clause. LLM-produced, human-reviewed.
``Manifest``  the evidence-capture plan the solver emits. The public interface.

Schema versioning: All persistent models include a schema_version field.
Increment when making breaking changes. Migration guide in docs/SCHEMA_MIGRATIONS.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, ValidationInfo

# Current schema version for all persistent models
# Increment this when making breaking changes to Clause, Rule, etc.
SCHEMA_VERSION = 1

Modality = Literal["shall", "must", "should", "imperative", "descriptive"]
"""How binding a clause is.

``imperative`` matters more than it looks: many real obligations in this document are written
as bare commands ("Designate all batteries with black ink...") with no modal verb at all.
Segmenting on the word "shall" alone silently drops them.
"""

Verifiability = Literal["observable", "measurable", "documentary", "process_only"]
"""How a clause could be discharged in the field.

``observable``   someone can see it (a label, a tag, a routing path)
``measurable``   needs an instrument (multimeter, torque wrench, tape)
``documentary``  needs a record to exist and be produced (a fuse record book)
``process_only`` an obligation on a workflow, not on the physical plant; no capture can settle it
"""

ObsKind = Literal["photo", "video", "measurement", "document"]
EvidenceKind = Literal["observation", "test_result", "claim", "alarm", "measurement"]
SourceType = Literal["human", "system", "sensor"]


class Reference(BaseModel):
    """Cross-references a clause makes to other parts of the document."""

    tables: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)
    clauses: list[str] = Field(default_factory=list)
    external: list[str] = Field(default_factory=list)  # e.g. "NEC", "NFPA 70"


class Clause(BaseModel):
    """One numbered clause, verbatim, with enough provenance to cite it."""

    schema_version: int = Field(default=SCHEMA_VERSION)
    id: str  # "D.6.6"
    chapter: str  # "D"
    chapter_title: str  # "Equipment and Cable Designations"
    section: str  # "6.0"
    section_title: str  # "DC Power"
    clause: str  # "6.6"
    page: int  # 0-based PDF page index
    page_label: str  # "D-4"
    text: str
    modality: Modality
    refs: Reference = Field(default_factory=Reference)
    codes: dict[str, object] = Field(default_factory=dict)
    """Machine-usable tokens found in the prose: quantities, verbatim label literals,
    gauges, designators, cross-references, carve-outs. See ``entities.Codes``."""
    duplicate_label: bool = False
    """True when the source document reused this clause number. The id carries a suffix so
    the clause stays addressable; the flag records that the standard itself is ambiguous."""
    doc: str = "EIGuide"
    doc_version: str = "6.0"


class Figure(BaseModel):
    """A captioned figure or table. Used as reference imagery during capture."""

    id: str  # "D1"
    kind: str = "figure"
    chapter: str = ""
    caption: str = ""
    page: int = 0
    page_label: str = ""
    image_path: str | None = None


class TableData(BaseModel):
    """A table recovered as rows. Numeric limits here become rule parameters."""

    page: int
    page_label: str
    chapter: str = ""
    rows: list[list[str]] = Field(default_factory=list)


class Observable(BaseModel):
    """A single thing that must be observed to help settle a clause.

    ``accepts`` holds a machine-checkable acceptance predicate. Nothing evaluates it today;
    it is the seam where computer-vision verification plugs in later without reshaping
    the schema.

    DECISION (Code Review): Keep the field for now as a documented seam for future
    vision verification. README.md:289-291 explicitly states this is where computer
    vision will plug in. Removing it would require re-authoring 32 acceptance criteria
    in data/rules.jsonl. Alternative considered was implementing vision now, but that's
    a separate project requiring vision model integration.
    """

    name: str  # "cell_number_legible" — becomes an ASP constant
    kind: ObsKind
    target: str  # "each cell in the string"
    method: str  # "slow pan, cell face legible"
    instrument: str | None = None
    accepts: str = ""  # Machine-checkable criterion - currently displayed to human, future: evaluated by vision model


RuleKind = Literal["obligation", "exemption", "definition"]
"""Not every clause imposes a duty.

``exemption`` clauses carve out an obligation stated elsewhere ("leads internal to the
relay rack do not require 145C tags"). They must be captured, because dropping one makes
the reasoner demand evidence that the standard explicitly does not require — but they are
realized as guards in the applicability of the rule they modify, not as duties of their
own. ``definition`` clauses fix vocabulary. Neither emits an obligation.
"""


class Rule(BaseModel):
    """A clause interpreted as something a solver can reason with."""

    schema_version: int = Field(default=SCHEMA_VERSION)
    id: str  # "D.6.6a" — a clause may yield more than one rule
    clause_id: str  # "D.6.6" — the clause this came from
    kind: RuleKind = "obligation"
    subject_type: str  # "battery_cell" — human-readable class name
    subject_term: str  # "cell(S,C)" — the ASP term the rule quantifies over
    applicability: list[str] = Field(default_factory=list)  # ASP body literals
    predicate: str  # "has_label"
    params: dict[str, str | float | int | bool] = Field(default_factory=dict)
    modality: Modality
    verifiability: Verifiability
    observables: list[Observable] = Field(default_factory=list)
    citation_span: str  # MUST be a verbatim substring of the source clause
    confidence: float = 0.0
    notes: str | None = None
    reviewed: bool = False

    @field_validator("citation_span")
    @classmethod
    def validate_citation_span(cls, v: str, info: ValidationInfo) -> str:
        """Validate that citation_span is a verbatim substring of the source clause.

        This ensures traceability: every rule must point back to exact text in the
        standard, and that text must actually exist in the source document.
        """
        # Note: We can't validate against clause text here because clause isn't available
        # during model instantiation. This validator exists to document the constraint
        # and provide a hook for runtime validation during compile/review.
        # The actual check happens in cli.py:review() command.
        if not v:
            raise ValueError("citation_span cannot be empty - must be verbatim quote from source clause")
        return v

    modifies: list[str] = Field(default_factory=list)
    """For an exemption: the rule ids it carves out. Recorded so the link survives review."""

    @property
    def field_verifiable(self) -> bool:
        return self.kind == "obligation" and self.verifiability in ("observable", "measurable")


class Discharge(BaseModel):
    """What a capture action settles."""

    rule: str
    subjects: list[str]
    observables: list[str]


class Citation(BaseModel):
    page_label: str
    text: str


class Action(BaseModel):
    """One physical thing the tech does at the site."""

    id: str
    kind: ObsKind
    target: str
    cost: int
    instruction: str
    discharges: list[Discharge] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    acceptance: dict[str, str] = Field(default_factory=dict)
    """Observable name -> the criterion that decides pass/fail. This is what an inspector
    reads, and the same string a vision model would be asked to evaluate."""


class OpenItem(BaseModel):
    """An applicable clause no available action can settle."""

    rule: str
    subject: str
    observable: str
    reason: str


class Manifest(BaseModel):
    """The evidence-capture plan. This is the documented public interface.

    Schema versioning: Increment schema_version when making breaking changes.
    See docs/SCHEMA_MIGRATIONS.md for migration guidance.
    """

    schema_version: int = Field(default=SCHEMA_VERSION)
    site: str
    generated_from: dict[str, object]
    actions: list[Action] = Field(default_factory=list)
    undetermined_after_plan: list[OpenItem] = Field(default_factory=list)


class EvidenceSource(BaseModel):
    """Provenance: who or what produced this evidence."""
    schema_version: int = Field(default=SCHEMA_VERSION)
    type: SourceType  # human, system, sensor
    id: str  # inspector_alice, samsung_nms, pdu_01
    system: str | None = None  # System name for automated sources


class Evidence(BaseModel):
    """Unified evidence model with identity, provenance, and temporal ordering.

    This is the bridge between compliance inspection and ticket triage - both systems
    can express evidence in this form. Replaces anonymous obs/3 and test_result/2.

    Design: DESIGN.md §1 "The largest structural change outstanding"
    """
    schema_version: int = Field(default=SCHEMA_VERSION)

    # Identity
    id: str  # evidence_1, evidence_2 - globally unique within session

    # Classification
    kind: EvidenceKind  # observation, test_result, claim, alarm, measurement

    # What was observed
    subject: str  # ASP term: cell(bs1,7), node(core01), link(uplink_3)
    property: str  # cell_number_legible, link_status, power_state
    value: str | float | bool  # Result: pass/fail, up/down, numeric reading

    # Provenance
    source: EvidenceSource
    timestamp: int  # Unix epoch seconds OR sequence number for relative ordering

    # Quality
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)

    # Optional enrichment
    method: str | None = None  # How obtained: photo, ping_test, snmp_poll
    notes: str | None = None

    # Correlation (for multi-evidence events like alarm storms)
    incident_id: str | None = None  # Groups related evidence

    def to_asp(self) -> str:
        """Render as ASP evidence/8 fact."""
        from .compile import quote

        # Format value based on type
        if isinstance(self.value, bool):
            val = "true" if self.value else "false"
        elif isinstance(self.value, str):
            val = quote(self.value)
        elif isinstance(self.value, int):
            val = str(self.value)
        elif isinstance(self.value, float):
            # ASP doesn't handle floats well - convert to fraction or int
            if self.value.is_integer():
                val = str(int(self.value))
            else:
                # Convert to fraction: 120.5 -> 241/2
                from fractions import Fraction
                frac = Fraction(self.value).limit_denominator(1000)
                val = f"{frac.numerator}/{frac.denominator}"
        else:
            val = str(self.value)

        # Format source as compound term
        src_system = f", {quote(self.source.system)}" if self.source.system else ""
        src = f"source({self.source.type}, {quote(self.source.id)}{src_system})"

        # Property is typically an atom, but could be complex - make it safe
        # Convert underscores to atoms, keep others as-is if valid ASP terms
        prop = self.property if self.property.isidentifier() and self.property.islower() else quote(self.property)

        # Format confidence as integer ratio if it's 1.0, otherwise as fraction
        # ASP doesn't like floating point decimals in some contexts
        if self.confidence == 1.0:
            conf = "1"
        elif self.confidence == 0.0:
            conf = "0"
        else:
            # Use fraction notation: 0.95 -> 95/100
            conf = f"{int(self.confidence * 100)}/100"

        return (
            f"evidence({self.id}, {self.kind}, {self.subject}, "
            f"{prop}, {val}, {src}, {self.timestamp}, {conf})."
        )


class Observation(BaseModel):
    """Legacy observation model - backward compatible with existing code.

    New code should use Evidence directly. This exists for gradual migration.
    """

    subject: str
    observable: str
    value: bool
    action: str | None = None
    note: str | None = None

    def to_evidence(self, evidence_id: str, source: EvidenceSource, timestamp: int | None = None) -> Evidence:
        """Convert legacy Observation to new Evidence model.

        Args:
            evidence_id: Unique ID for this evidence (e.g., "evidence_1")
            source: Who/what produced this observation
            timestamp: Unix epoch seconds (defaults to current time)
        """
        import time
        return Evidence(
            id=evidence_id,
            kind="observation",
            subject=self.subject,
            property=self.observable,
            value=self.value,
            source=source,
            timestamp=timestamp or int(time.time()),
            method=self.action,
            notes=self.note,
            confidence=1.0  # Legacy observations assumed fully confident
        )


class Verdict(BaseModel):
    """Per-clause compliance outcome. Three states, never two."""

    rule: str
    subject: str
    status: Literal["satisfied", "violated", "undetermined"]
    citation: Citation | None = None
    missing: list[str] = Field(default_factory=list)
