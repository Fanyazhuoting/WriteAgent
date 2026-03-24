"""Abstract base class for all WriteAgent agents."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any

from utils.llm_client import chat_completion
from utils.audit_logger import log_agent_call
from utils.token_counter import count_tokens
from prompts.registry import registry


class BaseAgent(ABC):
    """
    Abstract base for all agents.

    Subclasses must define:
        agent_id  (str class attribute)
        prompt_name (str class attribute — key in the prompt registry)
        run(state) -> dict
    """

    agent_id: str = "base_agent"
    prompt_name: str = "base"

    def _get_system_prompt(self, version: str | None = None) -> str:
        return registry.get_system(self.prompt_name, version)

    def _call_llm(
        self,
        messages: list[dict],
        novel_id: str,
        scene_number: int,
        prompt_version: str = "v1",
    ) -> tuple[str, dict]:
        """
        Call the LLM, log the interaction, and return (content, log_entry).
        Attempts to parse JSON; returns raw string if parsing fails.
        """
        prompt_text = "\n".join(m["content"] for m in messages)
        t0 = time.monotonic()
        content = chat_completion(messages)
        duration_ms = int((time.monotonic() - t0) * 1000)

        prompt_tokens = count_tokens(prompt_text)
        completion_tokens = count_tokens(content)

        log_entry = log_agent_call(
            novel_id=novel_id,
            agent_id=self.agent_id,
            scene_number=scene_number,
            prompt_version=prompt_version,
            prompt=prompt_text,
            output=content,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
        )
        return content, log_entry

    def _parse_json(self, content: str) -> dict:
        """Extract JSON from LLM output, stripping markdown fences if present."""
        import re
        text = content.strip()

        # Strip all markdown code fences (handles leading spaces before ```)
        text = re.sub(r'```[a-zA-Z]*\n?', '', text).strip()
        if text.endswith('```'):
            text = text[:-3].strip()

        # Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Find the outermost JSON object in text (handles leading/trailing prose)
        brace_match = re.search(r'\{[\s\S]*\}', text)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                pass

        # Return raw content under a generic key so callers can handle gracefully
        return {"_raw": content}

    @abstractmethod
    def run(self, state: dict) -> dict:
        """Execute this agent's logic and return a partial state update."""
        ...
