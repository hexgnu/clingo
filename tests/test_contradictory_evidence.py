"""Test detection of contradictory evidence from multiple sources."""

from pathlib import Path
import clingo

from compli.models import Evidence, EvidenceSource

ROOT = Path(__file__).resolve().parent.parent


def test_conflicting_values_same_subject_same_property():
    """Two sources report different values for same subject/property."""
    ev1 = Evidence(
        id="evidence_1",
        kind="observation",
        subject="cell(bs1,7)",
        property="cell_number_legible",
        value=True,
        source=EvidenceSource(type="human", id="inspector_a"),
        timestamp=1000,
    )

    ev2 = Evidence(
        id="evidence_2",
        kind="observation",
        subject="cell(bs1,7)",
        property="cell_number_legible",
        value=False,
        source=EvidenceSource(type="human", id="inspector_b"),
        timestamp=1001,
    )

    # Generate ASP facts
    facts = ev1.to_asp() + "\n" + ev2.to_asp()

    # Load evidence ontology
    ctl = clingo.Control()
    ctl.load(str(ROOT / "ontology" / "evidence.lp"))
    ctl.add("base", [], facts)
    ctl.ground([("base", [])])

    # Check for conflicts
    conflicts = []
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            for atom in model.symbols(shown=True):
                if atom.name == "conflicting_evidence":
                    conflicts.append((str(atom.arguments[0]), str(atom.arguments[1])))

    # Should detect the conflict
    assert len(conflicts) >= 1
    assert ("evidence_1", "evidence_2") in conflicts or ("evidence_2", "evidence_1") in conflicts


def test_different_subjects_no_conflict():
    """Different subjects with different values - no conflict."""
    ev1 = Evidence(
        id="evidence_1",
        kind="observation",
        subject="cell(bs1,1)",
        property="labeled",
        value=True,
        source=EvidenceSource(type="human", id="inspector"),
        timestamp=1000,
    )

    ev2 = Evidence(
        id="evidence_2",
        kind="observation",
        subject="cell(bs1,2)",
        property="labeled",
        value=False,
        source=EvidenceSource(type="human", id="inspector"),
        timestamp=1001,
    )

    facts = ev1.to_asp() + "\n" + ev2.to_asp()

    ctl = clingo.Control()
    ctl.load(str(ROOT / "ontology" / "evidence.lp"))
    ctl.add("base", [], facts)
    ctl.ground([("base", [])])

    conflicts = []
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            for atom in model.symbols(shown=True):
                if atom.name == "conflicting_evidence":
                    conflicts.append((str(atom.arguments[0]), str(atom.arguments[1])))

    # No conflict - different subjects
    assert len(conflicts) == 0


def test_different_properties_no_conflict():
    """Same subject, different properties - no conflict."""
    ev1 = Evidence(
        id="evidence_1",
        kind="observation",
        subject="cell(bs1,7)",
        property="cell_number_legible",
        value=True,
        source=EvidenceSource(type="human", id="inspector"),
        timestamp=1000,
    )

    ev2 = Evidence(
        id="evidence_2",
        kind="observation",
        subject="cell(bs1,7)",
        property="cell_polarity_marked",
        value=False,
        source=EvidenceSource(type="human", id="inspector"),
        timestamp=1001,
    )

    facts = ev1.to_asp() + "\n" + ev2.to_asp()

    ctl = clingo.Control()
    ctl.load(str(ROOT / "ontology" / "evidence.lp"))
    ctl.add("base", [], facts)
    ctl.ground([("base", [])])

    conflicts = []
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            for atom in model.symbols(shown=True):
                if atom.name == "conflicting_evidence":
                    conflicts.append(str(atom))

    # No conflict - different properties
    assert len(conflicts) == 0


def test_three_way_conflict():
    """Three sources, three different values."""
    ev1 = Evidence(
        id="evidence_1",
        kind="measurement",
        subject="voltage(pdu_01, outlet_3)",
        property="voltage_reading",
        value=120,
        source=EvidenceSource(type="sensor", id="meter_a"),
        timestamp=1000,
    )

    ev2 = Evidence(
        id="evidence_2",
        kind="measurement",
        subject="voltage(pdu_01, outlet_3)",
        property="voltage_reading",
        value=119,
        source=EvidenceSource(type="sensor", id="meter_b"),
        timestamp=1001,
    )

    ev3 = Evidence(
        id="evidence_3",
        kind="measurement",
        subject="voltage(pdu_01, outlet_3)",
        property="voltage_reading",
        value=121,
        source=EvidenceSource(type="sensor", id="meter_c"),
        timestamp=1002,
    )

    facts = ev1.to_asp() + "\n" + ev2.to_asp() + "\n" + ev3.to_asp()

    ctl = clingo.Control()
    ctl.load(str(ROOT / "ontology" / "evidence.lp"))
    ctl.add("base", [], facts)
    ctl.ground([("base", [])])

    conflicts = []
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            for atom in model.symbols(shown=True):
                if atom.name == "conflicting_evidence":
                    e1, e2 = str(atom.arguments[0]), str(atom.arguments[1])
                    conflicts.append((e1, e2))

    # Should have 3 conflict pairs: (1,2), (1,3), (2,3)
    assert len(conflicts) >= 3


def test_same_value_no_conflict():
    """Two sources agree - no conflict."""
    ev1 = Evidence(
        id="evidence_1",
        kind="observation",
        subject="node(core01)",
        property="power_state",
        value="on",
        source=EvidenceSource(type="human", id="inspector_a"),
        timestamp=1000,
    )

    ev2 = Evidence(
        id="evidence_2",
        kind="observation",
        subject="node(core01)",
        property="power_state",
        value="on",
        source=EvidenceSource(type="system", id="monitoring"),
        timestamp=1001,
    )

    facts = ev1.to_asp() + "\n" + ev2.to_asp()

    ctl = clingo.Control()
    ctl.load(str(ROOT / "ontology" / "evidence.lp"))
    ctl.add("base", [], facts)
    ctl.ground([("base", [])])

    conflicts = []
    with ctl.solve(yield_=True) as handle:
        for model in handle:
            for atom in model.symbols(shown=True):
                if atom.name == "conflicting_evidence":
                    conflicts.append(str(atom))

    # No conflict - same value
    assert len(conflicts) == 0
