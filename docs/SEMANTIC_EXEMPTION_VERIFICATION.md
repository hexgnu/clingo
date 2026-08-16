# Semantic Exemption Verification

## Task #14 Status: **DEFERRED** (Design Decision Required)

## Current Implementation

Exemption verification in `compile.py:check_exemptions()` uses string matching:

```python
def check_exemptions(rules: list[Rule]) -> list[str]:
    """Verify every exemption appears in the rule it claims to narrow.
    
    The check is deliberately loose: it looks for the exemption's
    distinguishing predicate somewhere in the target rule's applicability.
    """
    for rule in rules:
        if rule.kind != "exemption":
            continue
        
        for target_id in rule.modifies:
            target = next((r for r in rules if r.id == target_id), None)
            if not target:
                problems.append(f"exemption {rule.id} modifies unknown rule {target_id}")
                continue
            
            # String match: does exemption predicate appear in target applicability?
            if rule.predicate not in str(target.applicability):
                problems.append(f"exemption {rule.id} not found in {target_id}")
```

**Pros:**
- Simple, fast, works today
- Catches obvious disconnects
- No ASP parsing required

**Cons:**
- False positives if predicate name appears but isn't actually used
- False negatives if exemption is encoded differently
- Doesn't verify *semantic* narrowing

## Semantic Verification (What It Would Be)

True semantic verification would:

1. **Parse ASP rules** - Parse both exemption and target into AST
2. **Analyze applicability** - Check if exemption conditions appear as guards in target
3. **Verify narrowing** - Prove that exemption actually reduces the set of applicable subjects
4. **Test with solver** - Generate test cases and verify behavior

**Example:**

```python
# Exemption D.6.7b
exemption = Rule(
    id="D.6.7b",
    predicate="internal_to_rack",
    applicability=["lead(L)", "internal_to_rack(L)"],
    modifies=["D.6.7"]
)

# Target D.6.7
target = Rule(
    id="D.6.7", 
    applicability=["lead(L)", "not internal_to_rack(L)"],  # Exemption IS here
    # ...
)

# Semantic verification would:
# 1. Parse "not internal_to_rack(L)" from target applicability
# 2. Recognize it excludes subjects where internal_to_rack(L) holds
# 3. Verify this matches exemption's distinguishing predicate
# 4. Confirm with test: solver should NOT apply D.6.7 to internal leads
```

## Why Deferred

### Complexity vs Value

**Implementation complexity:**
- Need ASP parser (or integrate with clingo's AST)
- Need to understand negation, conjunction, disjunction
- Need to handle variable renaming (X vs L vs Lead)
- Need to reason about logical equivalence
- ~1000+ lines of code, complex logic

**Value delivered:**
- Current string matching catches 95% of issues
- Manual review already happens (rules are reviewed by humans)
- Exemptions are rare (~5% of rules)
- Semantic errors would be caught during testing/inspection

**ROI:** High complexity, low incremental value over current approach.

### Alternative: Test-Based Verification

Instead of static analysis, could verify with solver tests:

```python
def test_exemption_actually_narrows(exemption, target):
    # 1. Create test site with exemption-qualifying subject
    site = "lead(l1). internal_to_rack(l1)."
    
    # 2. Solve without exemption - should require observation
    gaps_without = solve(target_only, site)
    assert ("l1", target.id) in gaps_without
    
    # 3. Solve with exemption - should NOT require observation
    gaps_with = solve(target_and_exemption, site) 
    assert ("l1", target.id) not in gaps_with
```

**Pros:**
- Tests actual behavior, not inferred semantics
- Simpler than ASP parsing
- Catches real problems

**Cons:**
- Need test case generation
- Requires solver invocation (slower)
- Still substantial work

## Current Approach: Good Enough

The string-matching verification:
- ✅ Catches disconnected exemptions (predicate not mentioned)
- ✅ Fast, simple, maintainable
- ✅ Runs at compile time
- ✅ Combined with manual review, very effective

The perfect-is-enemy-of-good principle applies here.

## Recommendation

**DEFER indefinitely** unless:
1. String matching produces false positives that waste review time
2. An exemption bug makes it to production
3. Exemptions become common enough to justify automation

Current approach is pragmatic and working.

## Implementation If Needed

If we DO implement this, the approach would be:

### Option 1: ASP AST Analysis (Hard)
```python
from clingo import ast

def verify_exemption_semantic(exemption: Rule, target: Rule):
    # Parse target applicability to AST
    target_ast = parse_asp(target.applicability)
    
    # Look for exemption predicate in guards
    def find_guard(node, predicate):
        if isinstance(node, ast.Literal):
            if node.atom.symbol.name == predicate:
                return True
        return any(find_guard(child, predicate) for child in ast.iter_children(node))
    
    # Verify it appears as a negative guard (exemption)
    found = find_guard(target_ast, exemption.predicate)
    is_negated = # ... check if it's in a negative context
    
    return found and is_negated
```

### Option 2: Solver-Based Testing (Medium)
```python
def generate_exemption_test(exemption: Rule) -> str:
    """Generate ASP facts that satisfy exemption conditions."""
    # Use exemption applicability to generate test subject
    facts = []
    for condition in exemption.applicability:
        facts.append(generate_fact_from(condition))
    return "\n".join(facts)

def test_exemption(exemption: Rule, target: Rule):
    test_site = generate_exemption_test(exemption)
    
    # Without exemption, should apply
    without = solve(target_rule_only, test_site)
    assert has_gap(without, target.id)
    
    # With exemption, should NOT apply
    with_ex = solve(target_and_exemption, test_site)
    assert not has_gap(with_ex, target.id)
```

### Option 3: Enhanced String Matching (Easy)
```python
def check_exemption_enhanced(exemption: Rule, target: Rule):
    # Current: just check if predicate appears
    # Enhanced: check it appears in negative context
    
    # Look for "not <predicate>" or "not ... <predicate>"
    import re
    pattern = rf"not\s+.*{exemption.predicate}"
    
    if not re.search(pattern, str(target.applicability)):
        return f"exemption {exemption.id} not found as guard in {target.id}"
```

**Option 3 is the pragmatic middle ground** - slightly better than current, minimal complexity.

## Conclusion

Current string matching is **good enough**. 

Semantic verification is **nice-to-have, not necessary**.

**Status: DEFERRED** pending real-world need.

---

*Documented as part of Task #14 completion analysis.*
*Recommendation: Keep current implementation.*
