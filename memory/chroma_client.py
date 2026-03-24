"""ChromaDB client singleton and collection initialisation."""
import chromadb
from chromadb.config import Settings as ChromaSettings
from config.settings import settings

_client: chromadb.ClientAPI | None = None

COLLECTIONS = {
    "world_entities": "world_entities",
    "scene_archive": "scene_archive",
    "world_rules": "world_rules",
}


def get_client() -> chromadb.ClientAPI:
    """Return a persistent ChromaDB client (singleton)."""
    global _client
    if _client is None:
        _client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _ensure_collections(_client)
    return _client


def _ensure_collections(client: chromadb.ClientAPI) -> None:
    """Create all required collections if they don't already exist."""
    for name in COLLECTIONS.values():
        client.get_or_create_collection(name=name)


def get_collection(name: str) -> chromadb.Collection:
    """Return a named ChromaDB collection."""
    if name not in COLLECTIONS:
        raise ValueError(f"Unknown collection: {name}. Must be one of {list(COLLECTIONS)}")
    return get_client().get_collection(name)


def reset_all(confirm: bool = False) -> None:
    """Delete and recreate all collections. USE WITH CAUTION."""
    if not confirm:
        raise RuntimeError("Pass confirm=True to reset all collections.")
    client = get_client()
    for name in COLLECTIONS.values():
        client.delete_collection(name)
    _ensure_collections(client)
