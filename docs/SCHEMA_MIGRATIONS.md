# Schema Versioning and Migration Guide

## Overview

All persistent Pydantic models (`Clause`, `Rule`) include a `schema_version` field to track compatibility.

**Current Version:** 1 (defined in `src/compli/models.py::SCHEMA_VERSION`)

## When to Increment Version

Increment `SCHEMA_VERSION` when making **breaking changes** to persisted models:

### Breaking Changes (require version bump):
- Renaming fields
- Adding required fields with no default
- Changing field types incompatibly (e.g., `str` → `int`)
- Removing fields that existing data relies on
- Changing semantic meaning of existing fields

### Non-Breaking Changes (no version bump needed):
- Adding optional fields with defaults
- Removing fields that were always optional
- Widening types (e.g., `int` → `str | int`)
- Adding new models that don't affect existing ones

## Migration Process

### 1. Before Changing Schema

```bash
# Back up critical data files
cp data/clauses.jsonl data/clauses.jsonl.backup
cp data/rules.jsonl data/rules.jsonl.backup
```

### 2. Update Schema Version

```python
# src/compli/models.py
SCHEMA_VERSION = 2  # Increment from 1

class Rule(BaseModel):
    schema_version: int = Field(default=SCHEMA_VERSION)
    # ... make your changes
```

### 3. Write Migration Function

```python
# src/compli/migrate.py (create if needed)
from compli.models import Rule, SCHEMA_VERSION
from compli.store import read_jsonl, write_jsonl

def migrate_rules_v1_to_v2(old_path, new_path):
    """Migrate rules from schema version 1 to 2."""
    rules = read_jsonl(old_path, Rule)

    for rule in rules:
        if rule.schema_version == 1:
            # Apply migration logic
            # Example: rule.new_field = derive_from_old_field(rule)
            rule.schema_version = 2

    write_jsonl(new_path, rules)
    print(f"Migrated {len(rules)} rules to version 2")
```

### 4. Test Migration

```bash
# Test on backup data
uv run python -c "from compli.migrate import migrate_rules_v1_to_v2; \
                  migrate_rules_v1_to_v2('data/rules.jsonl.backup', 'data/rules.jsonl.migrated')"

# Verify migrated data
uv run pytest tests/  # Should all pass with migrated data
```

### 5. Document the Change

Add entry to this file:

```markdown
## Version 2 (2026-08-14)

**Breaking Changes:**
- Renamed `citation_span` → `source_citation` for clarity
- Added required `confidence_score: float` field

**Migration:**
```python
rule.source_citation = rule.citation_span
rule.confidence_score = 0.8  # Default for existing rules
```
```

## Version History

### Version 1 (Initial)
- First versioned schema
- Models: `Clause`, `Rule`, `Observable`, `Reference`
- Hand-reviewed rules in `data/rules.jsonl`

## Rollback Procedure

If migration fails or introduces bugs:

```bash
# Restore from backup
cp data/rules.jsonl.backup data/rules.jsonl

# Revert code changes
git revert <commit-hash>

# Verify
uv run pytest tests/
```

## Validation on Load

The system validates schema versions when loading JSONL files. If version mismatch detected:

```python
# Future enhancement: automatic migration on load
def read_jsonl_with_migration(path, model):
    records = read_jsonl(path, model)
    current_version = SCHEMA_VERSION

    for record in records:
        if record.schema_version < current_version:
            print(f"Warning: {path} contains v{record.schema_version} data, current schema is v{current_version}")
            # Could auto-migrate here in the future

    return records
```

## Best Practices

1. **Always backup before migration** - especially `data/rules.jsonl` (hand-reviewed)
2. **Test migration on copy first** - never run on production data directly
3. **Version migrations together** - if changing both Clause and Rule, increment once
4. **Document semantic changes** - even if technically compatible, note meaning shifts
5. **Keep old versions loadable** - Pydantic tolerates extra fields, so v2 can load v1 data
