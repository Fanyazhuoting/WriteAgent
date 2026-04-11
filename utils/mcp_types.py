"""
MCP Types — Unified structures for Model Context Protocol tools.
Standardizes how tools are defined, declared to LLMs, and executed.
"""
from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("writeagent.mcp")

@dataclass
class MCPTool:
    """
    Represents a single tool in the Model Context Protocol style.
    Pairs the LLM-visible schema with the local Python handler.
    """
    name: str
    description: str
    input_schema: Dict[str, Any]  # JSON Schema for parameters
    handler: Callable            # The actual Python function to run

    def to_openai_spec(self) -> Dict[str, Any]:
        """Convert this tool to an OpenAI/Qwen compatible function specification."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema
            }
        }

@dataclass
class MCPRegistry:
    """
    A collection of MCP tools that can be passed to an agent.
    """
    tools: Dict[str, MCPTool] = field(default_factory=dict)

    def register(self, tool: MCPTool):
        """Register a new tool in the collection."""
        self.tools[tool.name] = tool
        logger.debug(f"Registered MCP tool: {tool.name}")

    def get_schemas(self) -> List[Dict[str, Any]]:
        """Return all tool specifications for LLM context."""
        return [t.to_openai_spec() for t in self.tools.values()]

    def handle_call(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a tool by name with the provided arguments."""
        if name not in self.tools:
            error_msg = f"Tool '{name}' not found in registry."
            logger.error(error_msg)
            return {"error": error_msg}
        
        try:
            return self.tools[name].handler(**arguments)
        except Exception as e:
            error_msg = f"Error executing tool '{name}': {str(e)}"
            logger.exception(error_msg)
            return {"error": error_msg}
