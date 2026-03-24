"""PlotAgent — drives narrative progression and manages pacing."""
from __future__ import annotations

from .base_agent import BaseAgent
from prompts.registry import registry


class PlotAgent(BaseAgent):
    agent_id = "plot_agent"
    prompt_name = "plot"

    def run(self, state: dict) -> dict:
        novel_id = state["novel_id"]
        scene_number = state["current_scene_number"]
        scene_brief = state.get("current_scene_brief", "")
        genre = state.get("genre", "")
        style_guide = state.get("style_guide", "")
        output_language = state.get("output_language", "English")
        scene_history = state.get("scene_history", [])
        world_rules_context = state.get("world_rules_context", "")
        character_states = state.get("character_states", {})
        plot_events = state.get("plot_events", [])
        human_injection = state.get("human_injection") or "(none)"

        # Format character states for prompt
        char_summary = "\n".join(
            f"- {name}: {summary}" for name, summary in character_states.items()
        ) or "(none)"

        # Format plot events for prompt
        events_summary = "\n".join(f"- {e}" for e in plot_events[-10:]) or "(none)"

        prompt_data = registry.get(self.prompt_name)
        user_msg = prompt_data["user_template"].format(
            genre=genre,
            style_guide=style_guide,
            plot_events=events_summary,
            world_rules_context=world_rules_context or "(none)",
            character_states=char_summary,
            scene_history="\n\n".join(scene_history[-3:]) or "(none)",
            scene_brief=scene_brief,
            human_injection=human_injection,
            output_language=output_language,
        )

        messages = [
            {"role": "system", "content": self._get_system_prompt()},
            {"role": "user", "content": user_msg},
        ]

        content, _ = self._call_llm(messages, novel_id, scene_number)
        result = self._parse_json(content)

        scene_draft = result.get("scene_draft", content)
        new_events = result.get("plot_events", [])
        new_subplot = result.get("new_subplot")

        update: dict = {
            "raw_scene_draft": scene_draft,
            "plot_events": new_events,
            "agent_messages": [{
                "agent_id": self.agent_id,
                "content": content,
                "timestamp": "",
                "prompt_version": "v1",
                "token_count": 0,
            }],
        }

        if new_subplot:
            update["plot_events"] = new_events + [f"[SUBPLOT] {new_subplot}"]

        return update
