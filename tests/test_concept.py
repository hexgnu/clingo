"""The end-to-end concept: declarative statements in, capture plan out.

Chapter D could always be dismissed as a ruleset tuned until it worked. Chapter H is the
control: a second chapter added as **data only**, exercising paths Chapter D never touches
-- new subject types, a measurement modality, thresholds that vary by conductor gauge, and
a sweep group that is not a battery string.

If the concept is real, all of that works with no change to any Python. These tests assert
that, and the site validator tests assert the pipeline notices when its input is wrong.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eiguide import compile as compile_mod
from eiguide import reason, validate
from eiguide.models import Rule
from eiguide.store import read_jsonl

ROOT = Path(__file__).resolve().parent.parent
ONTOLOGY = [ROOT / "ontology" / "core.lp", ROOT / "ontology" / "domain.lp"]
SITE_H = ROOT / "sites" / "den02.lp"


def _executable_source(path: Path) -> str:
    """A module's code with comments and string literals removed.

    Documentation legitimately cites domain examples -- ``validate.py`` explains the
    pooling bug using a real cable-rack fact, and that is exactly what a reader needs.
    Only executable code can make the pipeline chapter-specific, so the check tokenizes
    rather than pattern-matching lines, which would flag every explanatory docstring.
    """
    import io
    import tokenize

    kept = []
    with path.open("rb") as fh:
        for tok in tokenize.tokenize(io.BytesIO(fh.read()).readline):
            if tok.type not in (tokenize.COMMENT, tokenize.STRING):
                kept.append(tok.string)
    return " ".join(kept)


@pytest.fixture(scope="module")
def chapter_h(tmp_path_factory, clause_index):
    rules = read_jsonl(ROOT / "data" / "golden" / "chapter_h.jsonl", Rule)
    source = compile_mod.compile_rules(rules, clause_index, "H", "EIGuide", "6.0")
    path = tmp_path_factory.mktemp("rules_h") / "chapter_h.lp"
    path.write_text(source, encoding="utf-8")
    return path


@pytest.fixture(scope="module")
def model_h(chapter_h):
    return reason.solve(ONTOLOGY + [chapter_h, SITE_H], "")


class TestSecondChapterIsDataOnly:
    """Chapter H introduces four subject types the Python has never heard of."""

    def test_new_subject_types_produce_a_plan(self, model_h):
        targets = {str(a.arguments[0]) for a in model_h.do}
        assert {"rk1", "rk2"} <= targets, "cable racks produced no actions"
        assert any(t.startswith("pc") for t in targets), "power cables produced no actions"
        assert {"rect1", "pdb1"} <= targets, "power bays produced no actions"

    def test_sweep_generalizes_beyond_battery_strings(self, model_h):
        """The load-bearing claim.

        The sweep tier was written for battery strings. A cable rack is a different kind of
        thing entirely, declared the same way. If sweeps only ever fire for batteries, the
        optimization was fitted to one case rather than being general.
        """
        chosen = [str(a) for a in model_h.do]
        assert any(a.startswith("sweep(rk1") for a in chosen), (
            f"no rack sweep chosen; the group model does not generalize: {chosen}"
        )
        # And it must actually cover the cables, not just exist.
        swept = {s for aid, _, s, _ in model_h.closes if aid.startswith("sweep(rk1")}
        assert len(swept) >= 8, f"rack sweep covered only {swept}"

    def test_one_clause_yields_different_thresholds_per_subject(self, model_h):
        """H.10.7 sets 2 feet for 1/0-and-smaller and 3 feet for 2/0-and-larger.

        Same clause, different limit, selected by a site fact about the conductor. A
        checklist would have to state both and leave the inspector to choose.
        """
        small = {s for r, s in model_h.undetermined if r == "H.10.7a"}
        large = {s for r, s in model_h.undetermined if r == "H.10.7b"}
        assert small == {"pc1", "pc2"}, small
        assert large == {"pc3", "pc9"}, large
        assert not (small & large), "a cable is subject to both thresholds"

    def test_measurements_never_bundle_into_a_sweep(self, model_h):
        """A tape-measure reading cannot be taken for eight cables in one pass.

        `bundleable` excludes measurement precisely so the optimizer cannot claim a
        physically impossible saving. This is the test that the cost model is not just
        minimizing a number detached from reality.
        """
        measured = {
            s for aid, _, s, o in model_h.closes if o.startswith("unsupported_span")
        }
        for aid, _, _, o in model_h.closes:
            if o.startswith("unsupported_span") or o == "letter_height_half_inch":
                assert aid.startswith("capture("), (
                    f"measurement {o} was bundled into {aid}, which cannot be done"
                )
        assert measured, "no measurements in the plan at all"

    def test_conditional_applicability_from_a_single_fact(self, model_h):
        """H.10.5 (exposed ends) applies only to pc8, the one cable with an exposed end."""
        exposed = {s for r, s in model_h.undetermined if r == "H.10.5"}
        assert exposed == {"pc8"}, exposed

    def test_the_pipeline_knows_nothing_about_either_chapter(self):
        """No pipeline module may mention domain vocabulary.

        The stronger form of "no Python was needed". A git diff only shows that nothing
        changed on one occasion; this shows the pipeline *cannot* be chapter-specific,
        because the words simply are not in it. If a subject type, predicate or clause id
        ever appears in the Python, the next chapter will need code and the concept fails.

        ``prove.py`` is excluded: it builds synthetic sites on purpose, and is a
        demonstration harness rather than part of the pipeline.
        """
        pipeline = [
            ROOT / "src" / "eiguide" / name
            for name in (
                "extract.py", "layout.py", "compile.py", "reason.py",
                "models.py", "validate.py", "cli.py", "entities.py", "store.py",
            )
        ]
        domain_terms = [
            "battery_string", "battery_lead", "cable_rack", "power_cable", "fuse_panel",
            "fuse_record_book", "power_bay", "distribution_circuit", "on_rack",
            "internal_to_rack", "short_visible_run", "misc_bay_mounted", "ground_cable",
            "tr_cell", "145c", "D.6.", "H.10.", "H.11.",
        ]
        offenders = []
        for path in pipeline:
            code = _executable_source(path)
            for term in domain_terms:
                if term in code:
                    offenders.append(f"{path.name}: {term}")
        assert not offenders, (
            f"pipeline code contains domain vocabulary, so it is not chapter-agnostic: "
            f"{offenders}"
        )


class TestSiteValidation:
    """A site fact that matches nothing produces a plan that looks complete and is not."""

    def test_pooling_across_arguments_is_caught(self):
        """`f(a;b, c)` yields `f(a)` and `f(b,c)`, not two `f/2` facts.

        This silently dropped seven of nine cables from a real plan during development.
        """
        found = validate.pooled_atoms("on_rack(pc1;pc2;pc3, rk1).")
        assert found and "on_rack" in found[0]

    def test_single_argument_pooling_is_not_flagged(self):
        """`power_cable(a;b)` does expand as expected, so warning about it is noise."""
        assert validate.pooled_atoms("power_cable(pc1;pc2;pc3).") == []

    def test_wrong_arity_is_caught(self, tmp_path):
        site = tmp_path / "bad.lp"
        site.write_text("on_rack(pc1).\ncable_rack(rk1).\n")
        problems = validate.validate_site(site, ONTOLOGY)
        assert any("on_rack/1" in p for p in problems), problems

    def test_typo_is_caught(self, tmp_path):
        site = tmp_path / "typo.lp"
        site.write_text("power_cabel(pc1).\n")
        problems = validate.validate_site(site, ONTOLOGY)
        assert any("power_cabel" in p for p in problems), problems

    def test_the_real_sites_are_clean(self, chapter_h, chapter_d_program):
        for site, program in (
            (ROOT / "sites" / "den01.lp", chapter_d_program),
            (SITE_H, chapter_h),
        ):
            problems = validate.validate_site(site, ONTOLOGY + [program])
            assert problems == [], f"{site.name}: {problems}"


def test_both_chapters_reason_together(chapter_h, chapter_d_program):
    """Chapters compose. Running D and H over one site must not interfere."""
    model = reason.solve(ONTOLOGY + [chapter_d_program, chapter_h, SITE_H], "")
    rules = {r for r, _ in model.undetermined}
    assert any(r.startswith("D.") for r in rules), "chapter D vanished"
    assert any(r.startswith("H.") for r in rules), "chapter H vanished"
    # And the plan still closes everything closable.
    closed = {(r, s, o) for _, r, s, o in model.closes}
    unreachable = {(r, s, o) for r, s, o in model.unreachable}
    for gap in model.gap:
        assert gap in closed or gap in unreachable
