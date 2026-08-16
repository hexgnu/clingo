#!/usr/bin/env python3
"""Test BAML extraction with a simple test case."""

import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path.cwd()))

from baml_client.sync_client import b

# Simple test document
test_doc = """
HVAC Clearance Requirements

Must maintain 30-36 inches of clearance from HVAC supply and return vents.

Verify externally that HVAC intake/exhaust vents are visible and not obstructed
by external infrastructure, cabling, or environmental debris.

Take clear photos showing the full vent and surrounding area.
"""

print("Testing BAML extraction...")
print(f"Document length: {len(test_doc)} characters")
print("\nCalling ExtractRules with Claude client...")

try:
    result = b.ExtractRules(test_doc, "Test HVAC Doc", {"client": "Claude"})
    print(f"\n✓ Success! Extracted {len(result)} rules")

    for i, rule in enumerate(result, 1):
        print(f"\nRule {i}:")
        print(f"  ID: {rule.id}")
        print(f"  Subject: {rule.subject_type}")
        print(f"  Predicate: {rule.predicate}")
        print(f"  Modality: {rule.modality}")
        print(f"  Observables: {len(rule.observables)}")
        for obs in rule.observables:
            print(f"    - {obs.name} ({obs.kind})")

except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback
    traceback.print_exc()
