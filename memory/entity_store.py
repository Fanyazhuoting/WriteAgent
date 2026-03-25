"""CRUD operations for all three ChromaDB collections."""
import json
from datetime import datetime, timezone

from .chroma_client import get_collection
from .schemas import EntityDoc, SceneArchiveDoc, WorldRuleDoc


def _where(conditions: dict) -> dict:
    """
    Build a ChromaDB `where` filter.
    Single condition → pass as-is.
    Multiple conditions → wrap with $and (ChromaDB requirement).
    """
    items = [{"novel_id" if k == "novel_id" else k: v} for k, v in conditions.items()]
    # Rebuild as proper ChromaDB equality operators
    clauses = [{k: {"$eq": v}} if not isinstance(v, dict) else {k: v}
               for k, v in conditions.items()]
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def _safe_n_results(col, n: int) -> int:
    """Return min(n, collection count) so query never asks for more than exists."""
    count = col.count()
    return max(1, min(n, count)) if count > 0 else 0


# ---------------------------------------------------------------------------
# World Entities
# ---------------------------------------------------------------------------

def upsert_entity(doc: EntityDoc) -> None:
    col = get_collection("world_entities")
    col.upsert(
        ids=[doc.entity_id],
        documents=[doc.description],   # only permanent description is embedded
        metadatas=[{
            "entity_id": doc.entity_id,
            "entity_type": doc.entity_type,
            "name": doc.name,
            "novel_id": doc.novel_id,
            "current_state": doc.current_state,
            "last_updated_scene": doc.last_updated_scene,
            "version": doc.version,
            "tags": doc.tags,
            "is_active": str(doc.is_active),
        }],
    )


def get_entity(entity_id: str) -> EntityDoc | None:
    col = get_collection("world_entities")
    result = col.get(ids=[entity_id], include=["documents", "metadatas"])
    if not result["ids"]:
        return None
    m = result["metadatas"][0]
    return EntityDoc(
        entity_id=m["entity_id"],
        entity_type=m["entity_type"],
        name=m["name"],
        novel_id=m["novel_id"],
        description=result["documents"][0],
        current_state=m.get("current_state", ""),
        last_updated_scene=int(m["last_updated_scene"]),
        version=int(m["version"]),
        tags=m.get("tags", ""),
        is_active=m["is_active"] == "True",
    )


def query_entities(
    novel_id: str,
    query_text: str,
    entity_type: str | None = None,
    k: int = 8,
) -> list[EntityDoc]:
    col = get_collection("world_entities")
    n = _safe_n_results(col, k)
    if n == 0:
        return []

    conditions: dict = {"novel_id": novel_id}
    if entity_type:
        conditions["entity_type"] = entity_type
    where = _where(conditions)

    result = col.query(
        query_texts=[query_text],
        n_results=n,
        where=where,
        include=["documents", "metadatas"],
    )
    docs = []
    for doc_text, meta in zip(result["documents"][0], result["metadatas"][0]):
        docs.append(EntityDoc(
            entity_id=meta["entity_id"],
            entity_type=meta["entity_type"],
            name=meta["name"],
            novel_id=meta["novel_id"],
            description=doc_text,
            current_state=meta.get("current_state", ""),
            last_updated_scene=int(meta["last_updated_scene"]),
            version=int(meta["version"]),
            tags=meta.get("tags", ""),
            is_active=meta["is_active"] == "True",
        ))
    return docs


def list_entities(novel_id: str, entity_type: str | None = None) -> list[EntityDoc]:
    col = get_collection("world_entities")
    conditions: dict = {"novel_id": novel_id}
    if entity_type:
        conditions["entity_type"] = entity_type
    where = _where(conditions)

    result = col.get(where=where, include=["documents", "metadatas"])
    docs = []
    for doc_text, meta in zip(result["documents"], result["metadatas"]):
        docs.append(EntityDoc(
            entity_id=meta["entity_id"],
            entity_type=meta["entity_type"],
            name=meta["name"],
            novel_id=meta["novel_id"],
            description=doc_text,
            current_state=meta.get("current_state", ""),
            last_updated_scene=int(meta["last_updated_scene"]),
            version=int(meta["version"]),
            tags=meta.get("tags", ""),
            is_active=meta["is_active"] == "True",
        ))
    return docs


# ---------------------------------------------------------------------------
# World Rules
# ---------------------------------------------------------------------------

def upsert_world_rule(doc: WorldRuleDoc) -> None:
    col = get_collection("world_rules")
    col.upsert(
        ids=[doc.rule_id],
        documents=[doc.description],
        metadatas=[{
            "rule_id": doc.rule_id,
            "novel_id": doc.novel_id,
            "category": doc.category,
            "severity": doc.severity,
            "established_at_scene": doc.established_at_scene,
            "established_by": doc.established_by,
        }],
    )


def get_world_rules(novel_id: str, severity: str | None = None) -> list[WorldRuleDoc]:
    col = get_collection("world_rules")
    conditions: dict = {"novel_id": novel_id}
    if severity:
        conditions["severity"] = severity
    where = _where(conditions)

    result = col.get(where=where, include=["documents", "metadatas"])
    rules = []
    for doc_text, meta in zip(result["documents"], result["metadatas"]):
        rules.append(WorldRuleDoc(
            rule_id=meta["rule_id"],
            novel_id=meta["novel_id"],
            description=doc_text,
            category=meta["category"],
            severity=meta["severity"],
            established_at_scene=int(meta["established_at_scene"]),
            established_by=meta["established_by"],
        ))
    return rules


# ---------------------------------------------------------------------------
# Scene Archive
# ---------------------------------------------------------------------------

def archive_scene(doc: SceneArchiveDoc) -> None:
    col = get_collection("scene_archive")
    col.upsert(
        ids=[doc.archive_id],
        documents=[doc.summary],
        metadatas=[{
            "archive_id": doc.archive_id,
            "novel_id": doc.novel_id,
            "scene_number": doc.scene_number,
            "chapter": doc.chapter,
            "characters_present": doc.characters_present,
            "location": doc.location,
            "plot_events": doc.plot_events,
            "timestamp": doc.timestamp,
            "token_count": doc.token_count,
        }],
    )


def query_scene_archive(
    novel_id: str,
    query_text: str,
    k: int = 5,
) -> list[SceneArchiveDoc]:
    col = get_collection("scene_archive")
    n = _safe_n_results(col, k)
    if n == 0:
        return []

    result = col.query(
        query_texts=[query_text],
        n_results=n,
        where={"novel_id": {"$eq": novel_id}},
        include=["documents", "metadatas"],
    )
    docs = []
    for summary, meta in zip(result["documents"][0], result["metadatas"][0]):
        docs.append(SceneArchiveDoc(
            archive_id=meta["archive_id"],
            novel_id=meta["novel_id"],
            scene_number=int(meta["scene_number"]),
            chapter=int(meta["chapter"]),
            summary=summary,
            characters_present=meta["characters_present"],
            location=meta["location"],
            plot_events=meta["plot_events"],
            timestamp=meta["timestamp"],
            token_count=int(meta.get("token_count", 0)),
        ))
    return docs
