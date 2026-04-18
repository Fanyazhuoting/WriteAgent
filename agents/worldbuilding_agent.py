"""WorldbuildingAgent — establishes world rules and holds veto power."""
from __future__ import annotations

from .base_agent import BaseAgent
from memory.entity_store import get_world_rules
from memory.retrieval import build_context_for_agent
from prompts.registry import registry
from guardrails.security_mcp import security_mcp


class WorldbuildingAgent(BaseAgent):
    agent_id = "worldbuilding_agent"
    prompt_name = "worldbuilding"

    def run(self, state: dict) -> dict:
        novel_id = state["novel_id"]
        scene_number = state["current_scene_number"]
        scene_brief = state.get("current_scene_brief", "")
        draft = state.get("raw_scene_draft", "")
        genre = state.get("genre", "")
        style_guide = state.get("style_guide", "")
        scene_history = state.get("scene_history", [])

        # Fetch world rules for context
        rules = get_world_rules(novel_id)
        world_rules_text = "\n".join(
            f"[{r.severity.upper()}][{r.category}] {r.description}" for r in rules
        ) or "(none established yet)"

        prompt_data = registry.get(self.prompt_name)
        user_msg = prompt_data["user_template"].format(
            genre=genre,
            style_guide=style_guide,
            world_rules=world_rules_text,
            scene_brief=scene_brief,
            draft=draft or "(no draft yet)",
        )

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_msg},
        ]

        # Use security MCP to sanitize input if needed
        content, _ = self._call_llm(
            messages, 
            novel_id, 
            scene_number, 
            mcp=security_mcp
        )
        result = self._parse_json(content)

        return {
            "world_rules_context": result.get("world_rules_context", ""),
            "worldbuilding_reasoning": result.get("reasoning", {}),
            "is_safe": result.get("is_safe", True),
            "agent_messages": [{
                "agent_id": self.agent_id,
                "content": content,
                "timestamp": "",
                "prompt_version": "v1",
                "token_count": 0,
            }],
        }
