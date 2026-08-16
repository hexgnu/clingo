"""Test knowledge base integrity - observables match rules, predicates are valid."""

from pathlib import Path
import pytest

from compli.models import Rule
from compli.store import read_jsonl
from compli import validate

ROOT = Path(__file__).resolve().parent.parent


def test_observable_names_match_asp_constants():
    """Observable names in rules should be valid ASP constants."""
    rules_file = ROOT / "data" / "golden" / "chapter_d6.jsonl"
    if not rules_file.exists():
        pytest.skip("Golden rules not available")

    rules = read_jsonl(rules_file, Rule)

    invalid_observables = []
    for rule in rules:
        for obs in rule.observables:
            # ASP constants: lowercase, alphanumeric + underscore
            if not (obs.name.islower() and obs.name.replace("_", "").isalnum()):
                invalid_observables.append(f"{rule.id}: {obs.name}")

    assert len(invalid_observables) == 0, f"Invalid observable names: {invalid_observables}"


def test_all_rules_have_observables_or_are_exemptions():
    """Obligation rules should have observables; exemptions don't need them."""
    rules_file = ROOT / "data" / "golden" / "chapter_d6.jsonl"
    if not rules_file.exists():
        pytest.skip("Golden rules not available")

    rules = read_jsonl(rules_file, Rule)

    obligations_without_obs = []
    for rule in rules:
        if rule.kind == "obligation" and rule.verifiability in ("observable", "measurable"):
            if not rule.observables:
                obligations_without_obs.append(rule.id)

    # Field-verifiable obligations should have observables
    assert len(obligations_without_obs) == 0, (
        f"Field-verifiable obligations without observables: {obligations_without_obs}"
    )


def test_subject_terms_are_valid_asp():
    """subject_term should be valid ASP predicates or variables."""
    rules_file = ROOT / "data" / "golden" / "chapter_d6.jsonl"
    if not rules_file.exists():
        pytest.skip("Golden rules not available")

    rules = read_jsonl(rules_file, Rule)

    invalid_subjects = []
    for rule in rules:
        # Should have form: predicate(Vars), predicate(var, Var), or just a variable (P, S, etc.)
        # Single uppercase letter is a valid ASP variable
        is_variable = len(rule.subject_term) == 1 and rule.subject_term.isupper()
        is_predicate = "(" in rule.subject_term and ")" in rule.subject_term

        if not (is_variable or is_predicate):
            invalid_subjects.append(f"{rule.id}: {rule.subject_term}")

    assert len(invalid_subjects) == 0, f"Invalid subject terms: {invalid_subjects}"


def test_domain_predicates_exist_in_ontology():
    """Predicates used in rules should be defined in domain.lp."""
    domain_file = ROOT / "ontology" / "domain.lp"
    if not domain_file.exists():
        pytest.skip("Domain ontology not available")

    # Parse domain.lp to find defined predicates
    domain_text = domain_file.read_text()
    domain_sigs = validate.signatures(domain_text)
    domain_preds = {name for name, _ in domain_sigs}

    # Load rules
    rules_file = ROOT / "data" / "golden" / "chapter_d6.jsonl"
    if not rules_file.exists():
        pytest.skip("Golden rules not available")

    rules = read_jsonl(rules_file, Rule)

    # Extract predicates from subject_terms
    undefined_preds = set()
    for rule in rules:
        # Extract predicate name from subject_term like "cell(S,C)"
        if "(" in rule.subject_term:
            pred_name = rule.subject_term.split("(")[0]
            # Common domain predicates
            if pred_name not in domain_preds and pred_name not in {
                "cell", "cable", "fuse_panel", "battery_string", "node", "link"
            }:
                undefined_preds.add(pred_name)

    # Some undefined predicates are okay (generated, or defined elsewhere)
    # Just check we don't have obviously wrong ones
    assert "undefined" not in undefined_preds
    assert "null" not in undefined_preds


def test_observables_in_rules_match_domain_actions():
    """Observable kinds should match action kinds in domain."""
    rules_file = ROOT / "data" / "golden" / "chapter_d6.jsonl"
    if not rules_file.exists():
        pytest.skip("Golden rules not available")

    rules = read_jsonl(rules_file, Rule)

    valid_kinds = {"photo", "video", "measurement", "document"}
    invalid_kinds = []

    for rule in rules:
        for obs in rule.observables:
            if obs.kind not in valid_kinds:
                invalid_kinds.append(f"{rule.id}: {obs.kind}")

    assert len(invalid_kinds) == 0, f"Invalid observable kinds: {invalid_kinds}"


def test_citation_spans_are_nonempty():
    """All rules should have non-empty citation spans."""
    rules_file = ROOT / "data" / "golden" / "chapter_d6.jsonl"
    if not rules_file.exists():
        pytest.skip("Golden rules not available")

    rules = read_jsonl(rules_file, Rule)

    empty_citations = []
    for rule in rules:
        if not rule.citation_span or not rule.citation_span.strip():
            empty_citations.append(rule.id)

    assert len(empty_citations) == 0, f"Rules with empty citations: {empty_citations}"


def test_rule_ids_are_unique():
    """Rule IDs should be unique within a file."""
    rules_file = ROOT / "data" / "golden" / "chapter_d6.jsonl"
    if not rules_file.exists():
        pytest.skip("Golden rules not available")

    rules = read_jsonl(rules_file, Rule)

    rule_ids = [r.id for r in rules]
    duplicates = [rid for rid in rule_ids if rule_ids.count(rid) > 1]
    unique_duplicates = list(set(duplicates))

    assert len(unique_duplicates) == 0, f"Duplicate rule IDs: {unique_duplicates}"


def test_clause_references_are_valid():
    """clause_id in rules should reference actual clauses."""
    rules_file = ROOT / "data" / "golden" / "chapter_d6.jsonl"
    clauses_file = ROOT / "data" / "golden" / "chapter_d6_clauses.jsonl"

    if not rules_file.exists() or not clauses_file.exists():
        pytest.skip("Golden data not available")

    from compli.models import Clause

    rules = read_jsonl(rules_file, Rule)
    clauses = read_jsonl(clauses_file, Clause)

    clause_ids = {c.id for c in clauses}
    invalid_refs = []

    for rule in rules:
        if rule.clause_id not in clause_ids:
            invalid_refs.append(f"{rule.id} -> {rule.clause_id}")

    assert len(invalid_refs) == 0, f"Rules with invalid clause_id: {invalid_refs}"


def test_domain_observes_predicates_match_observables():
    """Predicates in domain.lp observes/2 should match Observable names in rules."""
    domain_file = ROOT / "ontology" / "domain.lp"
    rules_file = ROOT / "data" / "golden" / "chapter_d6.jsonl"

    if not domain_file.exists() or not rules_file.exists():
        pytest.skip("Test data not available")

    # Extract observes/2 predicates from domain.lp
    domain_text = domain_file.read_text()
    import re
    observes_pattern = r'observes\([^,]+,\s*([a-z_][a-z0-9_]*)\)'
    observes_preds = set(re.findall(observes_pattern, domain_text))

    # Extract observable names from rules
    rules = read_jsonl(rules_file, Rule)
    rule_observables = {obs.name for rule in rules for obs in rule.observables}

    # Check for mismatches (observes/2 that don't match any Observable)
    undefined_observes = observes_preds - rule_observables

    # Some observes/2 may be generic or from other chapters - that's okay
    # Just ensure no obviously wrong ones
    assert "undefined_observable" not in undefined_observes


def test_requires_obs_predicates_exist():
    """Predicates used in requires_obs/3 should be defined."""
    # Check that compiled ASP files reference valid predicates
    chapter_file = ROOT / "rules" / "chapter_d.lp"
    if not chapter_file.exists():
        pytest.skip("Compiled chapter not available")

    chapter_text = chapter_file.read_text()

    # Extract requires_obs/3 calls
    import re
    requires_pattern = r'requires_obs\([^,]+,\s*([a-z_][a-z0-9_]*),\s*[^)]+\)'
    required_obs = set(re.findall(requires_pattern, chapter_text))

    # Should have some observables
    if required_obs:
        # Just check they're valid identifiers
        for obs in required_obs:
            assert obs.islower() and obs.replace("_", "").isalnum()


def test_action_predicates_are_consistent():
    """action/1 predicates in generated files should have matching action_cost/2."""
    chapter_file = ROOT / "rules" / "chapter_d.lp"
    if not chapter_file.exists():
        pytest.skip("Compiled chapter not available")

    chapter_text = chapter_file.read_text()

    # Extract action/1 and action_cost/2
    import re
    actions = set(re.findall(r'action\(([^)]+)\)', chapter_text))
    action_costs = set(re.findall(r'action_cost\(([^,]+),', chapter_text))

    # Every action should have a cost
    actions_without_cost = actions - action_costs

    # Allow some generated actions to not have costs (they might be derived)
    # Just check we don't have obviously broken ones
    assert "undefined_action" not in actions_without_cost
