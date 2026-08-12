"""Typed records passed between pipeline stages.

Three layers, deliberately kept separate:

``Clause``    verbatim text lifted from the PDF plus provenance. Generated, never hand-edited.
``Rule``      structured interpretation of a clause. LLM-produced, human-reviewed.
``Manifest``  the evidence-capture plan the solver emits. The public interface.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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


class Reference(BaseModel):
    """Cross-references a clause makes to other parts of the document."""

    tables: list[str] = Field(default_factory=list)
    figures: list[str] = Field(default_factory=list)
    clauses: list[str] = Field(default_factory=list)
    external: list[str] = Field(default_factory=list)  # e.g. "NEC", "NFPA 70"


class Clause(BaseModel):
    """One numbered clause, verbatim, with enough provenance to cite it."""

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
    """

    name: str  # "cell_number_legible" — becomes an ASP constant
    kind: ObsKind
    target: str  # "each cell in the string"
    method: str  # "slow pan, cell face legible"
    instrument: str | None = None
    accepts: str = ""


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
    """The evidence-capture plan. This is the documented public interface."""

    site: str
    generated_from: dict[str, object]
    actions: list[Action] = Field(default_factory=list)
    undetermined_after_plan: list[OpenItem] = Field(default_factory=list)


class Observation(BaseModel):
    """A captured fact about the site, fed back into the reasoner."""

    subject: str
    observable: str
    value: bool
    action: str | None = None
    note: str | None = None


class Verdict(BaseModel):
    """Per-clause compliance outcome. Three states, never two."""

    rule: str
    subject: str
    status: Literal["satisfied", "violated", "undetermined"]
    citation: Citation | None = None
    missing: list[str] = Field(default_factory=list)
