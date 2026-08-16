# Ticket Triage Example

Fault diagnosis for datacenter outages using evidence-based reasoning.

## Files

- `*.json` - Example tickets (power outage, network issues)
- `datacenter_faults.lp` - Fault ontology and diagnostic rules
- `samsung_router.lp` - Router-specific knowledge
- `vendor_codes.lp` - Alarm code mappings
- `production_outage.md` - Narrative walkthrough
- `run.py` - Quick demo script

## Quick Start

```bash
# Run interactive demo
cd examples/diagnosis
uv run python run.py

# Or manually triage a ticket
uv run compli triage --ticket examples/diagnosis/den_demo.json
```

## What's Happening

The solver:
1. **Reads ticket** - alarms, symptoms, initial observations
2. **Enumerates faults** - what could explain these symptoms?
3. **Generates test plan** - cheapest tests to distinguish between hypotheses

Three-valued logic: `established` (confirmed), `refuted` (ruled out), `uncertain` (needs testing).
