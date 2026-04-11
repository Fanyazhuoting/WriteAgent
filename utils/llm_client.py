"""Qwen-max LLM client via DashScope OpenAI-compatible API."""
from typing import Any
from openai import OpenAI
from config.settings import settings


def get_llm_client() -> OpenAI:
    """Return a configured OpenAI-compatible client pointing at DashScope."""
    return OpenAI(
        api_key=settings.dashscope_api_key,
        base_url=settings.qwen_base_url,
    )


def chat_completion(
    messages: list[dict],
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    tools: list[dict] | None = None,
    tool_choice: str | dict | None = None,
) -> Any:
    """
    Call Qwen-max and return the assistant message content or object.

    Args:
        messages: List of {"role": ..., "content": ...} dicts.
        model: Override model name (defaults to settings.qwen_model_name).
        temperature: Override temperature.
        max_tokens: Override max_tokens.
        tools: Optional list of tool definitions.
        tool_choice: Optional tool choice specification.

    Returns:
        The model's reply (message object if tools are used, else content string).
    """
    client = get_llm_client()
    kwargs = {
        "model": model or settings.qwen_model_name,
        "messages": messages,
        "temperature": temperature if temperature is not None else settings.llm_temperature,
        "max_tokens": max_tokens or settings.llm_max_tokens,
    }
    if tools:
        kwargs["tools"] = tools
    if tool_choice:
        kwargs["tool_choice"] = tool_choice

    response = client.chat.completions.create(**kwargs)
    message = response.choices[0].message
    
    # If tools were provided, return the full message object so caller can check tool_calls
    if tools:
        return message
    
    return message.content
