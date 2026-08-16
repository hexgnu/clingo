# Examples

Two example workflows showing ASP-based reasoning.

## [compliance/](compliance/)

**Problem:** "What must be TRUE?"  
**Domain:** Battery site compliance inspection  
**Input:** Engineering standard PDF  
**Output:** Evidence collection plan

```bash
uv run compli plan --site examples/compliance/den01.lp
```

## [diagnosis/](diagnosis/)

**Problem:** "What WENT WRONG?"  
**Domain:** Datacenter fault diagnosis  
**Input:** Alarm symptoms from outage  
**Output:** Test plan to confirm root cause

```bash
cd examples/diagnosis && uv run python run.py
```

## [hvac-compliance/](hvac-compliance/)

**Domain:** HVAC system compliance  
Smaller example showing PDF extraction → rules → inspection.

---

Both use the same three-valued logic (satisfied/violated/undetermined or established/refuted/uncertain) and the same optimization approach (minimize test cost to settle unknowns).
