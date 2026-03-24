"""Qwen-max LLM client via DashScope OpenAI-compatible API."""
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
) -> str:
    """
    Call Qwen-max and return the assistant message content.

    Args:
        messages: List of {"role": ..., "content": ...} dicts.
        model: Override model name (defaults to settings.qwen_model_name).
        temperature: Override temperature.
        max_tokens: Override max_tokens.

    Returns:
        The model's reply as a plain string.
    """
    client = get_llm_client()
    response = client.chat.completions.create(
        model=model or settings.qwen_model_name,
        messages=messages,
        temperature=temperature if temperature is not None else settings.llm_temperature,
        max_tokens=max_tokens or settings.llm_max_tokens,
    )
    return response.choices[0].message.content
