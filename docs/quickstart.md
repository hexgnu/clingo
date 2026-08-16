# 5-Minute Quickstart

Get from PDF to compliance verdict in 5 minutes.

## Prerequisites

- Python 3.12 or later
- A compliance PDF (engineering standard, specification, etc.)
- Optional: API key for LLM extraction (ANTHROPIC_API_KEY or FIREWORKS_API_KEY)

## Installation

```bash
git clone <repo-url>
cd clingo
uv sync
```

Check your environment:
```bash
uv run eiguide doctor
```

---

## Two Paths: Quick Demo vs Your Own PDF

### Path A: Quick Demo (2 minutes)

Try the tool with example data to see how it works.

```bash
# 1. See what an inspection plan looks like
uv run eiguide plan --site sites/den01.lp

# Output: 8 capture actions close 71 gaps across 9 requirements
#   1. [video] Record continuous pass over bs1...
#   2. [photo] Photograph bs1. Must establish: cell number legible...
#   ...

# 2. Run an interactive inspection
uv run eiguide inspect --site sites/den01.lp

# You'll be prompted step-by-step through the inspection
# Answer 'p' (pass) or 'f' (fail) for each observation
# The plan adapts based on your answers
```

**What just happened?**

The solver:
1. Found all requirements that apply to this site (from Chapter D)
2. Computed the minimal evidence needed to prove compliance
3. Optimized the plan (one sweep of 24 cells vs 24 individual photos)
4. Re-solved after each answer to adapt the inspection

---

### Path B: Your Own PDF (5 minutes)

Verify compliance with your own engineering standard.

#### Step 1: Extract clauses from your PDF

**Option 1: Rule-based extraction** (fast, deterministic)
```bash
uv run eiguide extract my-standard.pdf
```

**Option 2: LLM extraction** (generates structured rules, needs API key)
```bash
# Set API key in .env file first
echo 'FIREWORKS_API_KEY=fw_your_key_here' > .env

uv run eiguide extract-llm my-standard.pdf
```

**Output**: Extracts clauses, figures, and tables → `data/clauses.jsonl`

#### Step 2: Review rules (LLM extraction only)

If you used LLM extraction, review the generated rules:
```bash
uv run eiguide review --rules-file data/rules.jsonl
```

This shows each extracted rule alongside its source clause. Accept or reject each one.

If you used basic extraction, you'll need to create rules manually (see `data/` for examples).

#### Step 3: Compile rules to ASP

```bash
uv run eiguide compile --chapter HVAC --rules-file data/rules.jsonl
```

Replace `HVAC` with your chapter identifier (e.g., D, POWER, SEC).

**Output**: `rules/chapter_hvac.lp` (or your chapter name)

#### Step 4: Create a site file

Describe what's installed at your site using simple facts:

Create `sites/my-site.lp`:
```prolog
% Site identity
site(mysite).

% HVAC equipment
hvac_vent(intake_vent_1).
hvac_vent(return_vent_1).
hvac_controller(hvac_ctrl_main).
```

**See examples/** for complete site file examples.

#### Step 5: Generate an inspection plan

```bash
uv run eiguide plan --site sites/my-site.lp --chapter HVAC
```

**Output**: Shows the optimal inspection plan
```
╭──────────────────── Evidence plan — my-site ───────────────────╮
│ 3 capture actions close 6 evidence gaps across 4 requirements  │
╰────────────────────────────────────────────────────────────────╯
1. [photo] HVAC intake and return vents...
2. [photo] HVAC controller IP address screen...
```

The plan is **read-only** - nothing is written to disk.

#### Step 6: Run the inspection

```bash
uv run eiguide inspect --site sites/my-site.lp --chapter HVAC
```

**Interactive walkthrough**:
- You'll be asked to perform each capture action
- Answer `p` (pass), `f` (fail), `s` (skip), or `q` (quit) for each observation
- The solver re-plans after every answer
- At the end, see your compliance verdict

**Output example**:
```
Rule       Requirement                        n   Outcome
HVAC.1     Vents unobstructed                 2   2/2 ok
HVAC.6     IP enabled and accessible          1   1/1 unchecked
HVAC.2     Clearance 30-36 inches             2   2/2 ok

0 violated · 1 undetermined · 3 satisfied
```

Undetermined means nobody checked yet - **not the same as compliant**.

---

## Understanding the Output

### Three-Valued Logic

Unlike normal rules engines, this tool uses **three states**:

| Status | Meaning | Color |
|--------|---------|-------|
| **satisfied** | Evidence proves it's met | Green ✓ |
| **violated** | Evidence proves it's NOT met | Red ✗ |
| **undetermined** | Nobody has looked yet | Yellow ? |

**Why this matters**: Normal rules say "not violated = compliant". That reports a site as clean when nothing has been checked. ASP keeps the third state, so the list of `undetermined` requirements IS your work list.

### Capture Actions

Three tiers, different costs:

| Type | Cost | When Used | Example |
|------|------|-----------|---------|
| **capture** | 5 | One specific observation | "Does cell 7 have a label?" |
| **survey** | 6 | Multiple observations on one subject | "Photograph fuse panel fp1" (settles 4 rules at once) |
| **sweep** | 10 | Same observation across a group | "Video sweep of battery string bs1" (settles 24 cells at once) |

The solver picks the **cheapest mix** that closes all gaps. At 1-2 cells, individual captures win. At 3+ cells, a sweep is cheaper.

---

## Batch Mode (CI/Automation)

For automated verification (e.g., in CI):

```bash
# Create observations file
cat > observations.jsonl <<EOF
{"subject": "hvac_vent(intake1)", "observable": "unobstructed", "value": true, "action": "photo_1"}
{"subject": "hvac_vent(exhaust1)", "observable": "unobstructed", "value": true, "action": "photo_1"}
EOF

# Run verification (exit code 0 = pass, 1 = fail/incomplete)
uv run eiguide verify --site sites/my-site.lp --observations observations.jsonl --chapter HVAC

# Optional: Write verdict as JSON
uv run eiguide verify --site sites/my-site.lp --observations observations.jsonl --chapter HVAC --json-output verdict.json
```

Exit codes:
- `0` - All requirements satisfied
- `1` - Violations found OR undetermined requirements remain
- `2` - Errors (missing files, invalid site, etc.)

---

## Diagnosis Mode (Bonus)

This tool also solves the **inverse problem**: given symptoms, what broke?

```bash
# Interactive ticket diagnosis
uv run eiguide work tickets/den_demo.json

# One-shot diagnosis
uv run eiguide triage tickets/den_demo.json
```

See main README.md for the full diagnosis walkthrough.

---

## Common Issues

### "Site file has validation errors"

ASP fails silently on typos. Common mistakes:

❌ **Wrong**: `hvac_vent(v1;v2).` 
- Creates `hvac_vent(v1)` and `v2` separately (wrong arity!)

✅ **Right**: `hvac_vent(v1). hvac_vent(v2).`

❌ **Wrong**: `hvac_controler(c1).` (typo)

✅ **Right**: `hvac_controller(c1).`

Run `eiguide doctor` to check your environment.

### "No rules found for chapter X"

You need to compile rules first:
```bash
uv run eiguide compile --chapter X --rules-file data/rules.jsonl
```

### "Clauses file not found"

You need to extract from PDF first:
```bash
uv run eiguide extract your-pdf.pdf
```

### "No API key found" (when using extract-llm)

Create a `.env` file:
```bash
echo 'FIREWORKS_API_KEY=fw_your_key_here' > .env
```

Or use basic extraction (no API key needed):
```bash
uv run eiguide extract your-pdf.pdf
```

---

## Next Steps

**Understand the approach**:
- Main README.md - Full documentation
- `ontology/` - See the domain predicates available

**See examples**:
- `examples/` - Complete working examples (coming soon)

**Advanced usage**:
- Custom rules: `data/` for examples
- Site file predicates: `ontology/domain.lp`
- Test the solver: `uv run eiguide prove`

---

## Cheat Sheet

```bash
# Environment check
uv run eiguide doctor

# Extract from PDF
uv run eiguide extract <pdf>              # Rule-based
uv run eiguide extract-llm <pdf>          # LLM-based (needs API key)

# Review LLM-extracted rules
uv run eiguide review --rules-file data/rules.jsonl

# Compile to ASP
uv run eiguide compile --chapter X --rules-file data/rules.jsonl

# Plan inspection
uv run eiguide plan --site sites/my.lp --chapter X

# Run inspection
uv run eiguide inspect --site sites/my.lp --chapter X

# Batch verification
uv run eiguide verify --site sites/my.lp --observations obs.jsonl --chapter X

# Test solver claims
uv run eiguide prove

# Diagnose ticket
uv run eiguide work tickets/demo.json
```

---

## What Makes This Different?

Three capabilities **only ASP provides**:

| Capability | Rule Engine | Datalog | ASP |
|------------|-------------|---------|-----|
| **Open-world reasoning** (unknown ≠ false) | ❌ | ❌ | ✅ |
| **Enumerate all minimal solutions** | ❌ | ❌ | ✅ |
| **Optimize over solutions** | ❌ | ❌ | ✅ |

See main README.md for the full explanation of why traditional rule engines and Datalog can't solve this problem.

---

**Questions?** See [README.md](../README.md) for the comprehensive guide.
