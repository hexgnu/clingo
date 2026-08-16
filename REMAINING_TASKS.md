# Remaining 9 Tasks - Quick Wins

## Easy Wins (Can do quickly)

### #11: Two-pass solver coordination tests
- Test that when Stage 1 (coverage) fails, Stage 2 (discrimination) doesn't run
- Test error messages bubble up correctly
- **Effort**: 30 min - just need integration test

### #12: Contradictory evidence tests
- Expand beyond single pattern to multiple conflicts
- Test: same subject, different sources, conflicting values
- **Effort**: 20 min - evidence layer makes this trivial

### #28: Threshold comparator directionality
- Verify >= vs > in threshold tests
- Ensure "at threshold" edge cases work correctly
- **Effort**: 15 min - add edge case to existing tests

### #30: Manifest schema versioning
- Add schema_version to Manifest model
- Add backward compat tests for loading old manifests
- **Effort**: 20 min - same pattern as Clause/Rule versioning

### #31: Citation span validation on load
- Currently only checked in review command
- Add validation when loading rules.jsonl for plan/inspect
- **Effort**: 15 min - call existing validator

### #41: Knowledge base integrity tests
- Test observables/2 matches Observable names
- Test rules reference valid domain predicates
- **Effort**: 30 min - parse ASP, cross-check

## Harder (Design decisions needed)

### #7: Checkpoint/resume
- **Issue**: Conflicts with "no partial state" design
- **Decision needed**: Allow partial state? Or just save full session?
- **Options**:
  1. Save full observations.jsonl after each action (simple)
  2. Add session state file with cursor position
  3. Don't implement - just use verify with saved obs
- **Recommendation**: Option 1 - auto-save observations.jsonl

### #14: Semantic exemption verification
- Currently string-match citation spans
- Would need ASP analysis to verify exemption actually modifies rule
- **Complexity**: High - requires ASP parsing + applicability checking
- **Recommendation**: Defer - current approach works, this is nice-to-have

## Already Done (Need to verify)

### #2: Pipeline unification ✅
- **Status**: Foundation complete (see EVIDENCE_UNIFICATION.md)
- Evidence model exists, generates dual format
- Ready for triage.py integration
- Mark as complete (foundation ready)

## Summary

**Quick wins (6 tasks): ~2 hours**
- #11, #12, #28, #30, #31, #41

**Design decisions (2 tasks): Need user input**
- #7: Checkpoint strategy?
- #14: Worth the complexity?

**Already done (1 task): Just verify**
- #2: Foundation complete ✅

**Total: 9 tasks remaining**
