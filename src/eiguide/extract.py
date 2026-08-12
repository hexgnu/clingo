"""Stage 1: PDF -> verbatim clauses with provenance.

This module is deliberately thin. The hard work is done by two document-agnostic layers:

* ``layout.analyze``  recovers paragraphs, labels, headings and tables from any paginated
  standard by inferring its conventions rather than being told them;
* ``entities.extract_codes``  pulls quantities, literals, designators and references out of
  requirement prose using patterns that describe the genre, not this document.

What is left here is assembly and naming: grouping paragraphs under their headings, giving
each clause a stable id, and classifying how binding it is. No interpretation of *meaning*
happens at this stage -- that is the structuring stage's job.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path

import pymupdf

from . import layout
from .entities import extract_codes
from .models import Clause, Figure, Modality, Reference, TableData

# A caption line introducing a figure or table. Generic across technical documents.
CAPTION_RE = re.compile(r"^(?P<kind>Figure|Table|Exhibit|Diagram)\s+(?P<id>[A-Z]?\d+[a-z]?)\s*[:.\-]\s*(?P<caption>.+)$", re.IGNORECASE)

# Base-form verbs that open a bare imperative obligation. This list is the one piece of
# genuine English-language knowledge in the module; it is domain-flavoured but not
# document-specific, and unrecognized verbs degrade to "descriptive" rather than being lost.
IMPERATIVE_VERBS = frozenset(
    ["designate", "label", "place", "provide", "install", "stamp", "use", "mark", "attach", "apply", "ensure", "verify", "record", "route", "secure", "tag", "identify", "remove", "replace", "maintain", "locate", "terminate", "connect", "support", "bond", "ground", "cover", "seal", "torque", "avoid", "keep", "run", "mount", "fasten", "insulate", "protect", "separate", "arrange", "prepare", "submit", "obtain", "follow", "refer", "check", "test", "inspect", "document", "report", "store", "dispose"]
)


def classify_modality(text: str) -> Modality:
    """Determine how binding a clause is.

    Precedence matters: a clause containing both "shall" and "should" is binding. Clauses
    with no modal verb at all are still obligations when written as commands -- in this
    document that pattern accounts for a large share of the real requirements, so treating
    "shall" as the only marker of obligation would silently drop them.
    """
    lowered = text.lower()
    if re.search(r"\bshall\b", lowered):
        return "shall"
    if re.search(r"\bmust\b", lowered):
        return "must"
    if re.search(r"\b(?:is|are)\s+required\b", lowered):
        return "must"
    # A clause that opens with a command is binding, and outranks a "should" appearing in
    # a later sentence -- "Designate all batteries... The last cell should have..." is an
    # obligation with an advisory aside, not advice.
    first = re.match(r"^([A-Za-z]+)\b", text)
    if first and first.group(1).lower() in IMPERATIVE_VERBS:
        return "imperative"
    if re.search(r"\bshould\b", lowered):
        return "should"
    return "descriptive"


def _section_of(label: str) -> str:
    """The parent of a dotted label: "6.6" -> "6", "2.3.1" -> "2.3"."""
    parts = label.split(".")
    return ".".join(parts[:-1]) if len(parts) > 1 else label


def _chapter_of(page_label: str) -> str:
    """The alpha prefix of a qualified locator: "D-4" -> "D".

    Documents that number pages plainly get a single synthetic chapter, which keeps the
    rest of the pipeline uniform.
    """
    m = re.match(r"^([A-Za-z]{1,3})-", page_label)
    return m.group(1).upper() if m else "-"


def extract(
    pdf_path: Path, doc_name: str = "EIGuide", doc_version: str = "6.0"
) -> tuple[list[Clause], list[Figure], list[TableData], list[str]]:
    """Recover every numbered clause, captioned figure and table from the document.

    Returns the artifacts plus any warnings about the source document itself -- currently
    repeated clause numbers, which are the standard's own defects rather than parsing
    failures, but which callers must know about.
    """
    doc = pymupdf.open(pdf_path)
    warnings: list[str] = []
    try:
        lay = layout.analyze(doc)
        chapter_titles = _chapter_titles(lay)

        clauses: list[Clause] = []
        figures: list[Figure] = []

        section_titles: dict[tuple[str, str], str] = {}
        pending: Clause | None = None

        for para in lay.paragraphs:
            chapter = _chapter_of(para.page_label)

            caption = CAPTION_RE.match(para.text)
            if caption:
                figures.append(
                    Figure(
                        id=caption.group("id"),
                        kind=caption.group("kind").lower(),
                        chapter=chapter,
                        caption=caption.group("caption").strip(),
                        page=para.page,
                        page_label=para.page_label,
                    )
                )
                pending = None
                continue

            if para.label is None:
                # Unlabelled prose continues the clause above it.
                if pending is not None and _continues(pending, para, chapter):
                    pending.text = f"{pending.text} {para.text}".strip()
                continue

            if para.is_heading:
                section_titles[(chapter, para.label)] = para.text
                pending = None
                continue

            section = _section_of(para.label)
            clause = Clause(
                id=f"{chapter}.{para.label}",
                chapter=chapter,
                chapter_title=chapter_titles.get(chapter, ""),
                section=section,
                section_title=section_titles.get((chapter, f"{section}.0"))
                or section_titles.get((chapter, section), ""),
                clause=para.label,
                page=para.page,
                page_label=para.page_label,
                text=para.text,
                modality="descriptive",  # finalized below, once continuations are merged
                doc=doc_name,
                doc_version=doc_version,
            )
            clauses.append(clause)
            pending = clause

        # Text repairs run over the whole corpus before anything is derived from it:
        # hyphenation needs the document's own vocabulary, and modality must be judged on
        # the finished text, not on a fragment that stopped at a page break.
        for clause in clauses:
            clause.text = _tidy(clause.text)
        _repair_hyphenation(clauses)
        collisions = _disambiguate_labels(clauses)
        if collisions:
            warnings.extend(collisions)

        for clause in clauses:
            clause.modality = classify_modality(clause.text)
            codes = extract_codes(clause.text)
            clause.codes = codes.as_dict()
            clause.refs = Reference(
                tables=codes.tables,
                figures=codes.figures,
                clauses=codes.clauses,
                external=codes.standards,
            )

        tables = [
            TableData(page=t.page, page_label=t.page_label, chapter=_chapter_of(t.page_label), rows=t.rows)
            for t in lay.tables
        ]
        return clauses, figures, tables, warnings
    finally:
        doc.close()


TERMINAL = (".", ":", ";", "!", "?")


def _continues(pending: Clause, para: layout.Paragraph, chapter: str) -> bool:
    """Whether an unlabelled paragraph carries on the clause above it.

    Within a page this is unambiguous. Across a page break it is a judgement call, and
    refusing to cross was losing the tail of roughly one clause in fifteen -- a clause that
    ends "...on the same termi-" is plainly unfinished. Requiring the pending text to lack
    terminal punctuation keeps stray captions and callouts on the next page from being
    glued on, while letting genuine continuations through.
    """
    if pending.chapter != chapter:
        return False
    if pending.page_label == para.page_label:
        return True
    return not pending.text.rstrip().rstrip("\xad").endswith(TERMINAL)


HYPHEN_BREAK_RE = re.compile(r"([A-Za-z]{2,})-\s+([a-z]{2,})")


def _repair_hyphenation(clauses: list[Clause]) -> None:
    """Rejoin words split across a line break by an ordinary hyphen.

    The document breaks words two ways. A soft hyphen (U+00AD) is unambiguous and handled
    in ``_tidy``. An ASCII hyphen is not: it appears both in "applica- ble", where the word
    continues, and in "whole- document", where the hyphen is real. Guessing wrong either
    corrupts a term or fuses two.

    The document resolves its own ambiguity. If the joined form occurs anywhere else in the
    corpus as a single word, the break was soft; otherwise the hyphen is genuine and only
    the stray space is removed. No external lexicon is needed.
    """
    vocabulary: set[str] = set()
    for clause in clauses:
        vocabulary.update(re.findall(r"[a-z]{3,}", clause.text.lower()))

    def rejoin(m: re.Match[str]) -> str:
        head, tail = m.group(1), m.group(2)
        if (head + tail).lower() in vocabulary:
            return head + tail
        return f"{head}-{tail}"

    for clause in clauses:
        clause.text = HYPHEN_BREAK_RE.sub(rejoin, clause.text)


def _disambiguate_labels(clauses: list[Clause]) -> list[str]:
    """Give every clause a unique id, even when the source document repeats one.

    Chapter K really does number three consecutive clauses "2.2" -- a typo in the standard,
    not a parsing error. Left alone it is silently destructive: every lookup keyed by
    clause id keeps one record and drops the rest, so two genuine requirements disappear
    from citations without a trace. Suffixing keeps them addressable and reports the
    collision rather than hiding it.
    """
    seen: dict[str, int] = {}
    collisions: list[str] = []
    for clause in clauses:
        base = clause.id
        if base not in seen:
            seen[base] = 1
            continue
        seen[base] += 1
        clause.id = f"{base}#{seen[base]}"
        clause.duplicate_label = True
        collisions.append(f"{base} repeated on page {clause.page_label} -> {clause.id}")
    return collisions


def _tidy(text: str) -> str:
    """Repair line-wrap artifacts and normalize punctuation.

    PDFs break words across lines with a soft hyphen (U+00AD). Joining without removing it
    yields "cus tomer", which corrupts the term for every downstream consumer.
    """
    text = text.replace("­ ", "").replace("­", "")
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip()


def _chapter_titles(lay: layout.Layout) -> dict[str, str]:
    """Name each chapter from the running header carried on its own pages.

    The header line that ends in the page locator ("Equipment and Cable Designations D-4")
    names the chapter. Reading it out of the chrome works even when the table of contents
    is formatted differently, abbreviates, or is missing entirely -- and it self-corrects,
    because the most frequent such line across a chapter's pages wins.
    """
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for lines in lay.chrome_by_page.values():
        for line in lines:
            m = re.match(r"^(?P<title>.+?)\s+(?P<ch>[A-Za-z]{1,3})-(?P<n>\d{1,3})\s*$", line)
            if not m:
                continue
            title = m.group("title").strip()
            # Reject the copyright notice and other prose that happens to end in a locator.
            if len(title) > 60 or title.lower().startswith(("©", "®", "copyright")):
                continue
            votes[m.group("ch").upper()][title] += 1
    return {ch: counter.most_common(1)[0][0] for ch, counter in votes.items() if counter}
