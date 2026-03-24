"""Unit tests for the ChromaDB entity store (uses an isolated temp DB)."""
import pytest
import tempfile
import os

# Patch the chroma persist dir before importing the module
@pytest.fixture(autouse=True)
def isolated_chroma(tmp_path, monkeypatch):
    monkeypatch.setenv("CHROMA_PERSIST_DIR", str(tmp_path / "chroma"))
    # Re-import settings and reset the client singleton
    import memory.chroma_client as cc
    cc._client = None
    yield
    cc._client = None


from memory.schemas import EntityDoc, WorldRuleDoc, SceneArchiveDoc
from memory import (
    upsert_entity, get_entity, list_entities, query_entities,
    upsert_world_rule, get_world_rules,
    archive_scene, query_scene_archive,
)


NOVEL_ID = "test-novel-001"


def make_entity(**kwargs) -> EntityDoc:
    defaults = dict(
        entity_type="character",
        name="Elena",
        novel_id=NOVEL_ID,
        description="A young archivist with curious eyes.",
    )
    defaults.update(kwargs)
    return EntityDoc(**defaults)


def test_upsert_and_get_entity():
    entity = make_entity()
    upsert_entity(entity)
    retrieved = get_entity(entity.entity_id)
    assert retrieved is not None
    assert retrieved.name == "Elena"
    assert retrieved.novel_id == NOVEL_ID


def test_list_entities_by_type():
    upsert_entity(make_entity(name="Elena", entity_type="character"))
    upsert_entity(make_entity(name="Silvermere Forest", entity_type="location"))
    chars = list_entities(NOVEL_ID, entity_type="character")
    locs = list_entities(NOVEL_ID, entity_type="location")
    assert any(e.name == "Elena" for e in chars)
    assert any(e.name == "Silvermere Forest" for e in locs)


def test_upsert_updates_version():
    entity = make_entity()
    upsert_entity(entity)
    entity.version = 2
    entity.description = "Updated description."
    upsert_entity(entity)
    retrieved = get_entity(entity.entity_id)
    assert retrieved.version == 2
    assert "Updated" in retrieved.description


def test_upsert_and_get_world_rule():
    rule = WorldRuleDoc(
        novel_id=NOVEL_ID,
        description="Magic requires rare crystals.",
        severity="absolute",
        category="magic",
    )
    upsert_world_rule(rule)
    rules = get_world_rules(NOVEL_ID, severity="absolute")
    assert any("crystals" in r.description for r in rules)


def test_archive_and_query_scene():
    import json
    from datetime import datetime, timezone
    doc = SceneArchiveDoc(
        novel_id=NOVEL_ID,
        scene_number=1,
        summary="Elena finds a glowing map in her grandmother's attic.",
        characters_present="Elena",
        location="Attic",
        plot_events=json.dumps(["Found map"]),
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    archive_scene(doc)
    results = query_scene_archive(NOVEL_ID, "map attic Elena", k=3)
    assert len(results) >= 1
    assert any("map" in r.summary for r in results)
