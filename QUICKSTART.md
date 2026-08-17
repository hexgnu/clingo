# Quick Start - Working Examples

All commands run from the **repo root**.

## 1. View a Compliance Plan

See what needs to be inspected for a battery site:

```bash
# First compile the rules
uv run compli compile --rules-file examples/compliance/rules.jsonl

# Then generate the plan
uv run compli plan --site examples/compliance/den01.lp
```

**Expected output:**
```
╭─ Evidence plan — den01 ─╮
│ 8 capture actions close 71 evidence gaps across 9 requirements │
╰─────────────────────────╯

1. Record a continuous pass over bs1...
2. Photograph bs1. Must establish: cell number legible...
```

## 2. Interactive Inspection

Step through an inspection interactively:

```bash
uv run compli inspect --site examples/compliance/den01.lp
```

Answer `p` (pass) or `f` (fail) for each observation. The plan adapts based on your answers.

## 3. Ticket Triage

Diagnose what's wrong from alarm symptoms:

```bash
uv run compli triage examples/diagnosis/den_demo.json \
  --knowledge examples/diagnosis/datacenter_faults.lp \
  --knowledge examples/diagnosis/vendor_codes.lp
```

**Expected output:**
Shows possible faults and recommended tests to discriminate between them.

## Current Limitations

⚠️ Some commands are currently broken after refactoring:

- `compli quickstart` - requires BAML client setup (complex)
- `examples/diagnosis/run.py` - interactive demo needs path fixes
- Some test fixtures need updating for new paths

**Working commands:**
- ✅ `compli compile` - works
- ✅ `compli plan` - works (after compile)
- ✅ `compli inspect` - works (after compile)
- ✅ `compli triage` - works with explicit knowledge paths
- ✅ `compli doctor` - environment check

## For Steph

Start with:
```bash
git clone <repo-url>
cd clingo
uv sync
uv run compli doctor  # Check environment
uv run compli compile --rules-file examples/compliance/rules.jsonl
uv run compli plan --site examples/compliance/den01.lp
```

That shows the core idea: ASP solver generating optimal inspection plans.
