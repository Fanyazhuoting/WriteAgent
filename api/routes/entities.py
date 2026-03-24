"""Entity CRUD and graph endpoints."""
from __future__ import annotations

import networkx as nx
from fastapi import APIRouter, HTTPException

from api.models import EntityResponse, EntityUpdateRequest, EntityGraphResponse
from memory.entity_store import list_entities, get_entity, upsert_entity
from memory.schemas import EntityDoc

router = APIRouter(prefix="/entities", tags=["entities"])


def _to_response(e: EntityDoc) -> EntityResponse:
    return EntityResponse(
        entity_id=e.entity_id,
        entity_type=e.entity_type,
        name=e.name,
        description=e.description,
        version=e.version,
        last_updated_scene=e.last_updated_scene,
    )


@router.get("/{novel_id}", response_model=list[EntityResponse])
def list_all_entities(novel_id: str, entity_type: str | None = None):
    entities = list_entities(novel_id, entity_type=entity_type)
    return [_to_response(e) for e in entities]


@router.get("/{novel_id}/graph", response_model=EntityGraphResponse)
def get_entity_graph(novel_id: str):
    """Build a simple co-occurrence graph from entity descriptions."""
    entities = list_entities(novel_id)
    G = nx.Graph()

    for e in entities:
        G.add_node(e.entity_id, label=e.name, group=e.entity_type)

    # Simple heuristic: connect entities that appear in each other's descriptions
    entity_names = {e.name.lower(): e.entity_id for e in entities}
    for e in entities:
        desc_lower = e.description.lower()
        for other_name, other_id in entity_names.items():
            if other_name != e.name.lower() and other_name in desc_lower:
                G.add_edge(e.entity_id, other_id, label="mentions")

    nodes = [{"id": n, **G.nodes[n]} for n in G.nodes]
    edges = [{"from": u, "to": v, **G.edges[u, v]} for u, v in G.edges]
    return EntityGraphResponse(nodes=nodes, edges=edges)


@router.get("/{novel_id}/{entity_id}", response_model=EntityResponse)
def get_single_entity(novel_id: str, entity_id: str):
    entity = get_entity(entity_id)
    if not entity or entity.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Entity not found")
    return _to_response(entity)


@router.patch("/{novel_id}/{entity_id}", response_model=EntityResponse)
def update_entity(novel_id: str, entity_id: str, body: EntityUpdateRequest):
    entity = get_entity(entity_id)
    if not entity or entity.novel_id != novel_id:
        raise HTTPException(status_code=404, detail="Entity not found")
    entity.description = body.description
    if body.tags is not None:
        entity.tags = body.tags
    entity.version += 1
    upsert_entity(entity)
    return _to_response(entity)
