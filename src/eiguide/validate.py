"""Catch site files that are wrong in ways clingo will not complain about.

Site facts are hand-written, and ASP fails silently on the most common mistakes. Writing

    on_rack(pc1;pc2;pc3, rk1).

looks like it asserts three cables on a rack. It actually asserts ``on_rack(pc1)``,
``on_rack(pc2)`` and ``on_rack(pc3, rk1)`` -- the ``;`` splits the whole atom, not the
argument -- so two cables silently vanish from the plan. Clingo reports nothing, because
``on_rack/1`` is a perfectly legal predicate that simply appears in no rule.

That is exactly the failure mode this project exists to prevent, arriving through the back
door: a plan that looks complete and is not. A site fact whose signature appears nowhere in
the program can never affect any verdict, so it is always either a typo or dead weight.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

COMMENT_RE = re.compile(r"%.*?$", re.MULTILINE)
DEFINED_RE = re.compile(r"#defined\s+([a-z_][A-Za-z0-9_]*)\s*/\s*(\d+)")
ATOM_START_RE = re.compile(r"(?<![A-Za-z0-9_])([a-z_][A-Za-z0-9_]*)\s*\(")


def _strip(text: str) -> str:
    return COMMENT_RE.sub("", text)


def _scan(text: str, open_paren: int) -> tuple[int, bool, int]:
    """Inspect the atom whose '(' is at ``open_paren``.

    Returns (arity, uses_pooling, end_index). Pooling matters because ``;`` at argument
    level splits the atom rather than the argument, so ``f(a;b, c)`` yields ``f(a)`` and
    ``f(b,c)`` -- different predicates, no error.
    """
    depth = 0
    args = 1
    pooled = False
    for i in range(open_paren, len(text)):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return args, pooled, i
        elif depth == 1 and ch == ",":
            args += 1
        elif depth == 1 and ch == ";":
            pooled = True
    return args, pooled, len(text) - 1


def signatures(text: str) -> set[tuple[str, int]]:
    """Every (predicate, arity) mentioned in a chunk of ASP source."""
    text = _strip(text)
    found: set[tuple[str, int]] = set()
    for m in DEFINED_RE.finditer(text):
        found.add((m.group(1), int(m.group(2))))
    for m in ATOM_START_RE.finditer(text):
        arity, _, _ = _scan(text, m.end() - 1)
        found.add((m.group(1), arity))
    return found


def pooled_atoms(text: str) -> list[str]:
    """Atoms using ``;`` inside a multi-argument predicate.

    Harmless with one argument (``power_cable(a;b)`` does expand as expected). With more
    than one it silently produces mixed arities, so it is always worth flagging.
    """
    text = _strip(text)
    out = []
    for m in ATOM_START_RE.finditer(text):
        arity, pooled, end = _scan(text, m.end() - 1)
        if pooled and arity > 1:
            out.append(re.sub(r"\s+", " ", text[m.start() : end + 1]).strip())
    return out


def validate_site(site_file: Path, program_files: list[Path]) -> list[str]:
    """Report site facts that cannot possibly affect any verdict."""
    program: set[tuple[str, int]] = set()
    for path in program_files:
        program |= signatures(path.read_text(encoding="utf-8"))

    site_text = site_file.read_text(encoding="utf-8")
    problems: list[str] = []

    for atom in pooled_atoms(site_text):
        problems.append(
            f"{atom} uses ';' in a multi-argument predicate. This splits the atom, not the "
            f"argument, producing mixed arities -- write one fact per line instead."
        )

    by_name: dict[str, set[int]] = defaultdict(set)
    for name, arity in program:
        by_name[name].add(arity)

    for name, arity in sorted(signatures(site_text)):
        if name in ("site",):
            continue
        if (name, arity) in program:
            continue
        if name in by_name:
            expected = ", ".join(f"{name}/{a}" for a in sorted(by_name[name]))
            problems.append(
                f"{name}/{arity} is asserted but the rules only use {expected} -- "
                f"these facts match nothing and are silently ignored"
            )
        else:
            problems.append(
                f"{name}/{arity} appears in no rule or ontology declaration -- "
                f"either a typo or vocabulary the rules do not know about"
            )
    return problems
