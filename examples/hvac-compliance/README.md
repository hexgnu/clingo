# HVAC Compliance Example

This example demonstrates compliance verification for HVAC systems using the HVAC CITS 115 standard.

## Files

- `docs/HVAC CITS 115.pdf` - Source compliance document
- `rules.jsonl` - 9 extracted rules (LLM-generated, reviewed)
- `sites/datacenter01.lp` - Example site with HVAC equipment

## Quick Start

### 1. Compile rules to ASP

```bash
cd ../..  # Back to repo root
uv run compli compile --chapter HVAC --rules-file examples/hvac-compliance/rules.jsonl
```

This generates `rules/chapter_hvac.lp`.

### 2. Generate inspection plan

```bash
uv run compli plan --site examples/hvac-compliance/sites/datacenter01.lp --chapter HVAC
```

You'll see the optimal plan for collecting evidence.

### 3. Run interactive inspection

```bash
uv run compli inspect --site examples/hvac-compliance/sites/datacenter01.lp --chapter HVAC
```

Answer the prompts to verify each requirement.

## The 9 Rules

From HVAC CITS 115, the LLM extracted:

1. **HVAC.1** - Vents unobstructed (2 observables: internal + external photos)
2. **HVAC.2** - 30-36 inch clearance maintained
3. **HVAC.3** - Side vents and panels accessible
4. **HVAC.4** - Area clear of equipment/materials
5. **HVAC.5** - Blocked airflow addressed (process-only, no observables)
6. **HVAC.6** - Controller IP enabled and accessible (2 observables: network + IP screenshots)
7. **HVAC.7** - IP address valid and in range
8. **HVAC.8** - System status active and alarm-free
9. **HVAC.9** - Screenshots clear and unmodified

## Expected Output

Running `plan` should show ~6-8 capture actions covering the 9 requirements across the 5 pieces of equipment.

Running `inspect` will prompt for photos/screenshots of vents and controller screens.

## Customizing

Edit `sites/datacenter01.lp` to match your actual datacenter:
- Add more vents: `hvac_vent(intake_b).`
- Add units: `hvac_unit(crac_03).`
- Add controllers: `hvac_controller(ctrl_zone2).`

The plan will automatically adapt to your inventory.
