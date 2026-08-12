"""Generic extraction of the machine-usable bits of requirement prose.

These patterns describe how technical standards are written in general, not how this one
document is written. They pull out the pieces that become rule parameters and acceptance
criteria downstream:

* **quantities** -- the thresholds a measurement gets compared against
* **literals** -- text that must appear verbatim on a label or tag
* **designators** -- part, gauge and product codes
* **references** -- pointers to tables, figures, other clauses, external standards

Anything matched here is a *candidate*. The structuring stage decides what it means.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Spelled-out numbers appear constantly in this genre ("two (2) feet"), usually alongside
# the digit form. Matching the digit form is enough; the words are redundant.
UNITS = (
    r"inch(?:es)?|in\.|feet|foot|ft\.?|yards?|miles?|"
    r"millimet(?:er|re)s?|mm|centimet(?:er|re)s?|cm|met(?:er|re)s?|m\b|"
    r"pounds?|lbs?\.?|ounces?|oz\.?|kilograms?|kg|"
    r"volts?|V\b|amp(?:ere)?s?|A\b|watts?|W\b|ohms?|"
    r"degrees?|deg\.?|°|percent|%|"
    r"in-?lbs?|foot-?pounds?|ft-?lbs?|newton-?met(?:er|re)s?|N-?m|"
    r"hours?|minutes?|seconds?|days?|years?|"
    r"AWG|kcmil|MCM|gauge"
)

WORD_NUMBERS = {
    "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "fifteen": "15", "eighteen": "18", "twenty": "20", "twentyfour": "24", "thirty": "30",
    "thirtysix": "36", "forty": "40", "fifty": "50", "sixty": "60", "ninety": "90",
    "one-half": "0.5", "half": "0.5", "quarter": "0.25", "one-quarter": "0.25",
}
_WORDS = "|".join(sorted(WORD_NUMBERS, key=len, reverse=True))

# Technical prose writes thresholds three ways, and all three carry real limits:
#   "no more than two (2) feet"   digits parenthesised beside the word
#   "18 inches"                   bare digits
#   "no less than two inches"     words only -- the digit form is simply absent
# Allowing only the bare-digit form silently drops the first and third, which between them
# cover most of the numeric limits in this document.
QUANTITY_RE = re.compile(
    rf"(?P<value>\d+(?:\.\d+)?(?:\s*[-/]\s*\d+(?:\.\d+)?)?|[¼½¾⅓⅔⅛⅜⅝⅞]|\b(?:{_WORDS})\b)"
    rf"\s*\)?\s*(?P<unit>{UNITS})\b",
    re.IGNORECASE,
)

# Comparators that turn a quantity into a threshold rather than a description.
COMPARATOR_RE = re.compile(
    r"\b(no\s+(?:more|less|greater)\s+than|not\s+(?:more|less|greater)\s+than|"
    r"at\s+least|at\s+most|greater\s+than|less\s+than|minimum(?:\s+of)?|maximum(?:\s+of)?|"
    r"exceed(?:ing|s)?|within|up\s+to)\b",
    re.IGNORECASE,
)

# Text that must appear verbatim on a label, tag or plate. For a labeling standard this is
# the single most directly checkable thing in the whole clause.
LITERAL_RE = re.compile(r"[\"“]([^\"“”]{2,60})[\"”]")

# Wire gauges: "1/0", "2/0", "#6 AWG", "600 kcmil".
#
# A bare "#12" is NOT sufficient on its own -- this document also writes "cell #1" and
# "block #3", which are position numbers. Requiring either an unambiguous form (n/0,
# kcmil, MCM) or explicit conductor context keeps position numbers out of the gauge list,
# where they would otherwise be handed to the structuring stage as wire sizes.
GAUGE_RE = re.compile(
    r"(?<![\w/])(?:"
    r"\d{1,3}/0"
    r"|\d{3,4}\s*(?:kcmil|MCM)"
    r"|#\s?\d{1,3}\s*AWG"
    r"|(?<=\b)(?:AWG)\s*#?\s?\d{1,3}"
    r"|(?:wire|cable|conductor|cord|lacing|lead)\s+#\s?\d{1,3}"
    r")(?![\w/])",
    re.IGNORECASE,
)

# Position/item numbers ("cell #1"). Kept separate from gauges because they mean something
# completely different, but still worth surfacing -- ordinal labeling is itself a
# requirement in labeling standards.
ITEM_NUMBER_RE = re.compile(r"(?<![\w/])#\s?\d{1,3}(?!\s*(?:AWG|kcmil|MCM))(?![\w/])", re.IGNORECASE)

# Product, part and form designators: "145c", "+48VA", "C25.001", "L3-RFI", "OSX".
DESIGNATOR_RE = re.compile(
    r"\b(?:[A-Z]{1,4}-[A-Z0-9]{2,8}|[A-Z]\d{2}\.\d{3}|[+-]\d{2,3}[A-Z]{1,3}|\d{2,3}[a-cA-C]\b)\b"
)

TABLE_REF_RE = re.compile(r"\bTables?\s+((?:[A-Z]?\d+[a-z]?)(?:\s*(?:,|and|&|through|-)\s*[A-Z]?\d+[a-z]?)*)")
FIGURE_REF_RE = re.compile(r"\bFigures?\s+((?:[A-Z]?\d+[a-z]?)(?:\s*(?:,|and|&|through|-)\s*[A-Z]?\d+[a-z]?)*)")
CLAUSE_REF_RE = re.compile(r"\b(?:Section|Clause|Paragraph|Chapter)s?\s+([A-Z]?\d+(?:\.\d+)*)")
STANDARD_RE = re.compile(
    r"\b(NEC|NFPA(?:\s+\d+[A-Z]?)?|NESC|UL(?:\s+\d+)?|OSHA|IEEE(?:\s+\d+)?|ANSI(?:\s+[\w.-]+)?|"
    r"ASTM(?:\s+[\w-]+)?|Telcordia|GR-\d+(?:-CORE)?|ETSI|IEC(?:\s+\d+)?|ISO(?:\s+\d+)?)\b"
)

ID_TOKEN_RE = re.compile(r"[A-Z]?\d+[a-z]?")

# Negations and carve-outs. A rule that drops these inverts or over-applies the obligation,
# which is the most dangerous failure mode in the whole pipeline, so they are surfaced
# explicitly for the structuring stage and the human reviewer.
EXCEPTION_RE = re.compile(
    r"\b(except|unless|other\s+than|with\s+the\s+exception\s+of|does\s+not\s+apply|"
    r"do(?:es)?\s+not\s+require|not\s+required|if\s+no\s+other|where\s+possible|"
    r"if\s+applicable|when\s+applicable|as\s+required)\b",
    re.IGNORECASE,
)
NEGATION_RE = re.compile(r"\b(shall\s+not|must\s+not|may\s+not|do\s+not|never|no\s+\w+\s+shall)\b", re.IGNORECASE)


@dataclass
class Quantity:
    value: str
    unit: str
    comparator: str | None = None
    span: str = ""


@dataclass
class Codes:
    """The structured residue of a paragraph of requirement prose."""

    quantities: list[Quantity] = field(default_factory=list)
    literals: list[str] = field(default_factory=list)
    gauges: list[str] = field(default_factory=list)
    item_numbers: list[str] = field(default_factory=list)
    designators: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    clauses: list[str] = field(default_factory=list)
    standards: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    negated: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "quantities": [
                {"value": q.value, "unit": q.unit, "comparator": q.comparator, "span": q.span}
                for q in self.quantities
            ],
            "literals": self.literals,
            "gauges": self.gauges,
            "item_numbers": self.item_numbers,
            "designators": self.designators,
            "tables": self.tables,
            "figures": self.figures,
            "clauses": self.clauses,
            "standards": self.standards,
            "exceptions": self.exceptions,
            "negated": self.negated,
        }


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(i.strip() for i in items if i.strip()))


def _expand_refs(pattern: re.Pattern[str], text: str) -> list[str]:
    out: list[str] = []
    for m in pattern.finditer(text):
        out.extend(ID_TOKEN_RE.findall(m.group(1)))
    return _dedupe(out)


def extract_codes(text: str) -> Codes:
    """Pull every machine-usable token out of one paragraph."""
    codes = Codes()

    for m in QUANTITY_RE.finditer(text):
        # Look back a short distance for a comparator, so "no more than two (2) feet"
        # yields a threshold rather than a bare measurement.
        window = text[max(0, m.start() - 40):m.start()]
        comp = COMPARATOR_RE.findall(window)
        raw = re.sub(r"\s+", "", m.group("value"))
        codes.quantities.append(
            Quantity(
                # Normalize to digits so a threshold compares the same however it was written.
                value=WORD_NUMBERS.get(raw.lower(), raw),
                unit=m.group("unit").lower().rstrip("."),
                comparator=comp[-1].lower() if comp else None,
                span=m.group(0),
            )
        )

    # "two (2) feet" can match as both the word and the digit form; keep one per threshold.
    seen: set[tuple[str, str]] = set()
    deduped: list[Quantity] = []
    for q in codes.quantities:
        if (q.value, q.unit) not in seen:
            seen.add((q.value, q.unit))
            deduped.append(q)
    codes.quantities = deduped

    codes.literals = _dedupe(LITERAL_RE.findall(text))
    codes.gauges = _dedupe(m.group(0) for m in GAUGE_RE.finditer(text))
    codes.item_numbers = _dedupe(m.group(0) for m in ITEM_NUMBER_RE.finditer(text))
    codes.designators = _dedupe(DESIGNATOR_RE.findall(text))
    codes.tables = _expand_refs(TABLE_REF_RE, text)
    codes.figures = _expand_refs(FIGURE_REF_RE, text)
    codes.clauses = _dedupe(CLAUSE_REF_RE.findall(text))
    codes.standards = _dedupe(m.group(1) for m in STANDARD_RE.finditer(text))
    codes.exceptions = _dedupe(m.group(1).lower() for m in EXCEPTION_RE.finditer(text))
    codes.negated = bool(NEGATION_RE.search(text))
    return codes
