# Compliance Inspection Example

Battery site compliance inspection using Chapter D (DC Power) requirements.

## Quick Start

From the **repo root**:

```bash
# View the plan (what needs to be inspected)
uv run compli plan --site examples/compliance/den01.lp --rules-file examples/compliance/rules.jsonl

# Interactive inspection (step through observations)
uv run compli inspect --site examples/compliance/den01.lp --rules-file examples/compliance/rules.jsonl
```

## What's Happening

The solver:
1. Reads site topology (`den01.lp`) - battery strings, cells, cables
2. Loads rules (compiled from `rules.jsonl`) - Chapter D requirements  
3. Generates optimal plan - cheapest actions to close all compliance gaps

**Three-valued logic:**
- ✅ `satisfied` - evidence shows compliant
- ❌ `violated` - evidence shows non-compliant  
- ❓ `undetermined` - not checked yet

The plan optimizes: one sweep down a 24-cell battery string settles all cells at once, cheaper than 24 individual inspections.

## Files

- `chapter_d6.jsonl` - Structured rules from Chapter D.6
- `rules.jsonl` - Full rule set
- `den01.lp`, `den02.lp`, `den03.lp` - Example battery sites
