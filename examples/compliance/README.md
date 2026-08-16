# Compliance Inspection Example

Battery site compliance inspection using Chapter D (DC Power) requirements.

## Files

- `chapter_d6.jsonl` - Structured rules extracted from EIGuide Chapter D.6
- `chapter_d6_clauses.jsonl` - Original clause text with provenance
- `rules.jsonl` - Full rule set
- `den01.lp`, `den02.lp`, `den03.lp` - Example battery site topologies

## Quick Start

```bash
# Generate inspection plan
uv run compli plan --site examples/compliance/den01.lp

# Interactive inspection
uv run compli inspect --site examples/compliance/den01.lp
```

## What's Happening

The solver reads:
1. **Site topology** (`den01.lp`) - what exists: battery strings, cells, cables
2. **Rules** (compiled from `rules.jsonl`) - what must be observed
3. **Generates plan** - cheapest set of actions to close all compliance gaps

Three-valued logic keeps `undetermined` separate from `satisfied` and `violated`.
