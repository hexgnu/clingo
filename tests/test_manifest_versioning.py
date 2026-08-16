"""Test Manifest schema versioning and backward compatibility."""

import json
from pathlib import Path
import pytest

from compli.models import Manifest, Action, OpenItem, SCHEMA_VERSION


def test_manifest_has_schema_version():
    """Manifest includes schema_version field."""
    manifest = Manifest(
        site="test_site",
        generated_from={"doc": "EIGuide", "version": "6.0"},
        actions=[],
        undetermined_after_plan=[],
    )

    assert hasattr(manifest, "schema_version")
    assert manifest.schema_version == SCHEMA_VERSION


def test_manifest_serialization_includes_version():
    """JSON serialization includes schema_version."""
    manifest = Manifest(
        site="test_site",
        generated_from={"doc": "EIGuide", "version": "6.0"},
        actions=[],
    )

    json_str = manifest.model_dump_json()
    data = json.loads(json_str)

    assert "schema_version" in data
    assert data["schema_version"] == SCHEMA_VERSION


def test_load_manifest_without_version():
    """Loading old manifest without schema_version should default to current version."""
    # Simulate old manifest JSON without schema_version
    old_manifest_json = json.dumps({
        "site": "old_site",
        "generated_from": {"doc": "EIGuide", "version": "5.0"},
        "actions": [],
        "undetermined_after_plan": [],
    })

    manifest = Manifest.model_validate_json(old_manifest_json)

    # Should default to current schema version
    assert manifest.schema_version == SCHEMA_VERSION
    assert manifest.site == "old_site"


def test_load_manifest_with_explicit_version():
    """Loading manifest with explicit schema_version preserves it."""
    manifest_json = json.dumps({
        "schema_version": 1,
        "site": "versioned_site",
        "generated_from": {"doc": "EIGuide", "version": "6.0"},
        "actions": [],
        "undetermined_after_plan": [],
    })

    manifest = Manifest.model_validate_json(manifest_json)

    assert manifest.schema_version == 1
    assert manifest.site == "versioned_site"


def test_manifest_with_actions_preserves_version():
    """Manifest with actions maintains schema version."""
    action = Action(
        id="test_action",
        kind="photo",
        target="test_target",
        cost=10,
        instruction="Test instruction",
        discharges=[],
        citations=[],
        acceptance={},
    )

    manifest = Manifest(
        site="test_site",
        generated_from={"doc": "EIGuide"},
        actions=[action],
    )

    assert manifest.schema_version == SCHEMA_VERSION
    assert len(manifest.actions) == 1


def test_manifest_roundtrip_preserves_version():
    """Serialize and deserialize preserves schema_version."""
    original = Manifest(
        site="roundtrip_test",
        generated_from={"doc": "Test"},
        actions=[],
    )

    # Serialize
    json_str = original.model_dump_json()

    # Deserialize
    loaded = Manifest.model_validate_json(json_str)

    assert loaded.schema_version == original.schema_version
    assert loaded.site == original.site


def test_manifest_with_open_items():
    """Manifest with undetermined items maintains version."""
    open_item = OpenItem(
        rule="R1",
        subject="test_subject",
        observable="test_obs",
        reason="Cannot be settled",
    )

    manifest = Manifest(
        site="test_site",
        generated_from={"doc": "Test"},
        undetermined_after_plan=[open_item],
    )

    assert manifest.schema_version == SCHEMA_VERSION
    assert len(manifest.undetermined_after_plan) == 1
