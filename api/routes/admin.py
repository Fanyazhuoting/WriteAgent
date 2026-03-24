"""Admin endpoints — prompt versions and system health."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from api.models import PromptVersionInfo, PromptActivateRequest, HealthResponse
from api.dependencies import get_registry
from config.constants import AGENT_IDS
from prompts.registry import PromptRegistry

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/prompts", response_model=list[PromptVersionInfo])
def list_prompt_versions(reg: PromptRegistry = Depends(get_registry)):
    results = []
    for name in AGENT_IDS.values():
        agent_key = name.replace("_agent", "").replace("_checker", "_checker")
        # Map agent_id back to prompt_name
        prompt_name_map = {
            "worldbuilding_agent": "worldbuilding",
            "character_agent": "character",
            "plot_agent": "plot",
            "consistency_checker": "consistency_checker",
            "narrative_output_agent": "narrative_output",
        }
        prompt_name = prompt_name_map.get(name, name)
        try:
            versions = reg.list_versions(prompt_name)
        except Exception:
            versions = []
        results.append(PromptVersionInfo(
            agent=name,
            versions=versions,
            active_version=reg._version,
        ))
    return results


@router.put("/prompts/{agent}/{version}")
def activate_prompt_version(
    agent: str,
    version: str,
    reg: PromptRegistry = Depends(get_registry),
):
    """Switch the active prompt version for all agents (global switch)."""
    reg._version = version
    reg.reload()
    return {"status": "activated", "agent": agent, "version": version}


@router.get("/health", response_model=HealthResponse)
def health_check():
    # ChromaDB check
    try:
        from memory.chroma_client import get_client
        get_client()
        chroma_status = "ok"
    except Exception as e:
        chroma_status = f"error: {e}"

    # LLM check (just verify client instantiates)
    try:
        from utils.llm_client import get_llm_client
        get_llm_client()
        llm_status = "ok"
    except Exception as e:
        llm_status = f"error: {e}"

    # LangSmith check
    try:
        from config.settings import settings
        langsmith_status = "enabled" if settings.langchain_tracing_v2 else "disabled"
    except Exception as e:
        langsmith_status = f"error: {e}"

    all_ok = all(s == "ok" or s in ("enabled", "disabled") for s in [chroma_status, llm_status, langsmith_status])
    return HealthResponse(
        status="ok" if all_ok else "degraded",
        chroma=chroma_status,
        llm=llm_status,
        langsmith=langsmith_status,
    )
