"""Document-agnostic structure recovery.

Nothing in this module knows anything about the E&I Guidelines specifically. It recovers
structure from signals any paginated technical standard carries:

* running headers and footers **repeat**, so they can be found by counting rather than
  by hardcoding a line count or matching known strings;
* paragraphs are already delimited by the PDF's own text blocks;
* numbering schemes are **self-consistent**, so the dominant one can be inferred by
  scoring candidate families against the actual paragraph starts;
* tables are geometry, and the PDF layer can find them directly.

The document-specific knowledge lives in ``extract.py``, and is limited to naming things.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

# Candidate numbering families, tried against real paragraph starts and scored.
# The winner is whichever the document actually uses.
LABEL_FAMILIES: dict[str, re.Pattern[str]] = {
    "dotted": re.compile(r"^(\d{1,3}(?:\.\d{1,3})+)(?=[\s ]|$)"),
    "alpha_dotted": re.compile(r"^([A-Z](?:\.\d{1,3})+)(?=[\s ]|$)"),
    "integer": re.compile(r"^(\d{1,3})\.(?=\s)"),
    "alpha_paren": re.compile(r"^([a-z]\))(?=\s)"),
    "num_paren": re.compile(r"^(\(\d{1,3}\))(?=\s)"),
    "roman": re.compile(r"^((?:i{1,3}|iv|vi{0,3}|ix|xi{0,3})\.)(?=\s)", re.IGNORECASE),
}

# A locator in a running header: "D-4", "G-12", "4-7", or a bare page number.
LOCATOR_RE = re.compile(r"\b([A-Za-z]{1,3}-\d{1,3}|\d{1,4})\b")

_DIGITS = re.compile(r"\d+")
_WS = re.compile(r"\s+")

# Leader dots joining a heading to its page number. A near-universal marker of a
# table-of-contents entry, which must never be mistaken for the clause it points at.
TOC_LEADER_RE = re.compile(r"\.{4,}|(?:\.\s){4,}")


def is_toc_entry(line: str) -> bool:
    return bool(TOC_LEADER_RE.search(line))


def _mask(text: str) -> str:
    """Normalize a string so per-page variation collapses.

    A running header reads "Equipment and Cable Designations D-4" on one page and
    "... D-5" on the next. Masking digits makes the two compare equal, which is what
    lets repetition be detected by counting.
    """
    return _WS.sub(" ", _DIGITS.sub("#", text)).strip().lower()


@dataclass
class Paragraph:
    """One text block, in reading order, with its recovered label."""

    page: int
    page_label: str
    text: str
    bbox: tuple[float, float, float, float]
    label: str | None = None
    is_heading: bool = False


@dataclass
class Table:
    page: int
    page_label: str
    bbox: tuple[float, float, float, float]
    rows: list[list[str]] = field(default_factory=list)


@dataclass
class Layout:
    """Everything recovered from the document, before any domain interpretation."""

    paragraphs: list[Paragraph]
    tables: list[Table]
    label_family: str
    boilerplate: set[str]
    page_count: int
    chrome_by_page: dict[int, list[str]] = field(default_factory=dict)
    """Header/footer lines per page. Retained because a running header is the most
    reliable place to read a chapter's own title from."""


def detect_boilerplate(doc: pymupdf.Document, threshold: float = 0.35) -> set[str]:
    """Find repeated chrome by how often the same masked text recurs across pages.

    This catches boilerplate that moves around the page. It is a supplement to the
    geometric margin test in ``chrome_bands``, not a replacement: a running header that
    embeds the chapter title changes every chapter and so never repeats often enough to
    be caught by counting alone.
    """
    seen: Counter[str] = Counter()
    for pno in range(doc.page_count):
        # Count each distinct masked string once per page, so a phrase repeated several
        # times on one page does not look like boilerplate on its own.
        on_page = {
            _mask(line)
            for b in doc[pno].get_text("blocks")
            if b[6] == 0 and b[4].strip()
            for line in b[4].split("\n")
            if line.strip()
        }
        seen.update(on_page)
    cutoff = max(2, int(doc.page_count * threshold))
    return {text for text, n in seen.items() if n >= cutoff and text}


def chrome_bands(
    doc: pymupdf.Document, band: float = 0.09, page_frac: float = 0.5
) -> tuple[float, float]:
    """Locate the running header and footer bands geometrically.

    Chrome lives in the page margins at a stable height; content does not. Measuring where
    text actually sits, rather than assuming a fixed number of header lines, is what makes
    this work on a document whose header block is ordered differently from one chapter to
    the next.

    Returns ``(header_bottom, footer_top)`` as absolute y coordinates, or a degenerate
    range when the document has no consistent margins.
    """
    heights = [doc[p].rect.height for p in range(doc.page_count)] or [792.0]
    height = max(heights)
    head_limit, foot_limit = height * band, height * (1 - band)

    head_pages = foot_pages = 0
    for pno in range(doc.page_count):
        blocks = [b for b in doc[pno].get_text("blocks") if b[6] == 0 and b[4].strip()]
        if any(b[3] <= head_limit for b in blocks):
            head_pages += 1
        if any(b[1] >= foot_limit for b in blocks):
            foot_pages += 1

    cutoff = doc.page_count * page_frac
    return (
        head_limit if head_pages >= cutoff else -1.0,
        foot_limit if foot_pages >= cutoff else height + 1.0,
    )


def is_chrome(block, boilerplate: set[str], header_bottom: float, footer_top: float) -> bool:
    """True when a text block is a running header, footer, or other repeated furniture."""
    _, y0, _, y1, text, _, btype = block
    if btype != 0 or not text.strip():
        return True
    if y1 <= header_bottom or y0 >= footer_top:
        return True
    return _mask(text) in boilerplate


def infer_label_family(doc: pymupdf.Document, boilerplate: set[str]) -> str:
    """Pick the numbering scheme the document actually uses.

    Scored on how many content paragraphs start with each family. A document using
    "6.6" scores `dotted` highly; one using "(3)" scores `num_paren`. No family is
    assumed a priori.
    """
    scores: Counter[str] = Counter()
    header_bottom, footer_top = chrome_bands(doc)
    for pno in range(doc.page_count):
        for block in doc[pno].get_text("blocks", sort=True):
            if is_chrome(block, boilerplate, header_bottom, footer_top):
                continue
            # A block may open with a heading and continue into its first numbered item,
            # so score every line, not just the block's first.
            for line in block[4].split("\n"):
                line = line.strip()
                if not line or is_toc_entry(line):
                    continue
                for name, pattern in LABEL_FAMILIES.items():
                    if pattern.match(line):
                        scores[name] += 1
                        break
    if not scores:
        return "dotted"
    return scores.most_common(1)[0][0]


def page_locator(
    page: pymupdf.Page, boilerplate: set[str], header_bottom: float, footer_top: float
) -> str:
    """Recover the page's own locator (e.g. "D-4") from its running header or footer.

    Reads it out of the chrome, so it works for any document whose margins carry a
    section-qualified page number. Falls back to the PDF page number when there is none.
    """
    for block in page.get_text("blocks"):
        if not is_chrome(block, boilerplate, header_bottom, footer_top):
            continue
        for line in block[4].split("\n"):
            for hit in LOCATOR_RE.findall(line.strip()):
                if "-" in hit:  # qualified locators are far more informative
                    return hit
    return str(page.number + 1)


def _is_heading(body: str, label: str | None) -> bool:
    """A heading names a section; a clause states something.

    Headings are short, unpunctuated, and capitalized. The trailing-zero convention
    ("6.0 DC Power") is a strong extra signal where present, but is not required --
    documents that number headings 1, 2, 3 still work.
    """
    if not body:
        return False
    short_and_unpunctuated = len(body) <= 70 and not body.rstrip().endswith((".", ":", ";", ","))
    trailing_zero = bool(label and re.search(r"\.0+$", label))
    if not short_and_unpunctuated:
        return False
    return trailing_zero or body[:1].isupper()


def _split_labelled_lines(text: str, pattern: re.Pattern[str]) -> list[tuple[str | None, str]]:
    """Split a block into (label, body) pairs.

    Handles both layouts seen in the wild: the label inline with its body
    ("6.6  Designate all..."), and the label alone on its own line with the body beneath.
    """
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    out: list[tuple[str | None, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = pattern.match(line)
        if m:
            label = m.group(1)
            body = line[m.end():].strip()
            if not body and i + 1 < len(lines) and not pattern.match(lines[i + 1]):
                # Label alone on its line; the body is the next line.
                body = lines[i + 1]
                i += 1
            out.append((label, body))
        elif out:
            out[-1] = (out[-1][0], f"{out[-1][1]} {line}".strip())
        else:
            out.append((None, line))
        i += 1
    return out


def analyze(doc: pymupdf.Document) -> Layout:
    """Recover paragraphs, labels and tables from a paginated document."""
    boilerplate = detect_boilerplate(doc)
    header_bottom, footer_top = chrome_bands(doc)
    family = infer_label_family(doc, boilerplate)
    pattern = LABEL_FAMILIES[family]

    paragraphs: list[Paragraph] = []
    tables: list[Table] = []
    chrome_by_page: dict[int, list[str]] = {}

    for pno in range(doc.page_count):
        page = doc[pno]
        locator = page_locator(page, boilerplate, header_bottom, footer_top)
        chrome_by_page[pno] = [
            ln.strip()
            for block in page.get_text("blocks")
            if is_chrome(block, boilerplate, header_bottom, footer_top)
            for ln in block[4].split("\n")
            if ln.strip()
        ]

        # Tables are recovered as data. Their cells would otherwise be emitted as dozens
        # of stray blocks and get glued onto whatever clause preceded them.
        table_rects: list[pymupdf.Rect] = []
        try:
            found = page.find_tables()
        except Exception:
            found = None
        for tbl in found or []:
            rect = pymupdf.Rect(tbl.bbox)
            table_rects.append(rect)
            rows = [[(c or "").strip() for c in row] for row in tbl.extract()]
            tables.append(Table(page=pno, page_label=locator, bbox=tuple(rect), rows=rows))

        for block in page.get_text("blocks", sort=True):
            if is_chrome(block, boilerplate, header_bottom, footer_top):
                continue
            rect = pymupdf.Rect(block[:4])
            if any(rect in tr or abs(rect & tr) > 0.5 * abs(rect) for tr in table_rects):
                continue
            # Drop table-of-contents entries before they can be mistaken for clauses.
            text = "\n".join(
                ln for ln in block[4].split("\n") if ln.strip() and not is_toc_entry(ln)
            )
            if not text.strip():
                continue
            for label, body in _split_labelled_lines(text, pattern):
                if not body:
                    continue
                paragraphs.append(
                    Paragraph(
                        page=pno,
                        page_label=locator,
                        text=body,
                        bbox=tuple(rect),
                        label=label,
                        is_heading=_is_heading(body, label) if label else False,
                    )
                )

    return Layout(
        paragraphs=paragraphs,
        tables=tables,
        label_family=family,
        boilerplate=boilerplate,
        page_count=doc.page_count,
        chrome_by_page=chrome_by_page,
    )
