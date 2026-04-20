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


from guardrails.security_mcp import security_mcp
from utils.mcp_types import MCPRegistry


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

    # --- Tool & Retry Configuration ---
    MAX_TOOL_TURNS = 5  # Maximum number of tool-interaction rounds per call
    MAX_RETRIES = 3     # Maximum retries for API or parsing failures

    def _get_system_prompt(self, version: str | None = None) -> str:
        return registry.get_system(self.prompt_name, version)

    def _call_llm(
        self,
        messages: list[dict],
        novel_id: str,
        scene_number: int,
        prompt_version: str = "v1",
        mcp: MCPRegistry | None = None,
    ) -> tuple[str, dict]:
        """
        Call the LLM, handle tool calls using MCP in a multi-turn loop, and return (content, log_entry).
        Includes retry logic for robustness.
        """
        t0 = time.monotonic()
        
        # Use provided MCP or default to security_mcp
        active_mcp = mcp or security_mcp
        tool_schemas = active_mcp.get_schemas() if active_mcp else None
        
        turn_count = 0
        retry_count = 0
        content = ""

        while turn_count < self.MAX_TOOL_TURNS:
            try:
                response = chat_completion(
                    messages=messages,
                    tools=tool_schemas,
                )
                
                # Check if LLM wants to call tools
                if active_mcp and hasattr(response, "tool_calls") and response.tool_calls:
                    # 1. Add assistant message (containing tool_calls) to history
                    msg_dict = response.model_dump()
                    msg_dict = {k: v for k, v in msg_dict.items() if v is not None}
                    messages.append(msg_dict)
                    
                    # 2. Execute each tool call
                    for tool_call in response.tool_calls:
                        func_name = tool_call.function.name
                        try:
                            func_args = json.loads(tool_call.function.arguments)
                            
                            # --- CRITICAL FIX: Prevent novel_id Hallucination ---
                            # If the tool expects a novel_id, we override whatever 
                            # the LLM provided with the ACTUAL internal novel_id.
                            if "novel_id" in func_args:
                                func_args["novel_id"] = novel_id
                            
                            result = active_mcp.handle_call(func_name, func_args)
                        except json.JSONDecodeError:
                            result = {"error": "Invalid tool arguments JSON."}
                        except Exception as e:
                            result = {"error": str(e)}
                        
                        # 3. Add tool result to history
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": func_name,
                            "content": json.dumps(result, ensure_ascii=False)
                        })
                    
                    turn_count += 1
                    continue # Start next turn to let LLM process tool results
                
                # If no tool_calls, we have the final content
                content = response if isinstance(response, str) else response.content
                break

            except Exception as e:
                retry_count += 1
                if retry_count >= self.MAX_RETRIES:
                    content = f"Error: LLM call failed after {self.MAX_RETRIES} retries. Last error: {str(e)}"
                    break
                time.sleep(1) # Simple backoff
                continue

        duration_ms = int((time.monotonic() - t0) * 1000)

        # For logging, we save the full conversation history as a formatted string
        try:
            prompt_log_text = json.dumps(messages, ensure_ascii=False, indent=2)
        except Exception:
            prompt_log_text = "\n".join(str(m) for m in messages)

        prompt_tokens = count_tokens(prompt_log_text)
        completion_tokens = count_tokens(content)

        from utils.metrics import llm_call_duration, llm_tokens_total
        llm_call_duration.labels(agent_id=self.agent_id).observe(duration_ms / 1000)
        llm_tokens_total.labels(agent_id=self.agent_id, direction="prompt").inc(prompt_tokens)
        llm_tokens_total.labels(agent_id=self.agent_id, direction="completion").inc(completion_tokens)

        log_entry = log_agent_call(
            novel_id=novel_id,
            agent_id=self.agent_id,
            scene_number=scene_number,
            prompt_version=prompt_version,
            prompt=prompt_log_text,           # Full history
            output=content,                   # Final response
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            metadata={"tool_turns": turn_count, "retries": retry_count}
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
