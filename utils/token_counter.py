"""Token counting utilities (tiktoken as a proxy for Qwen tokenization)."""
import tiktoken

_enc = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Estimate token count using cl100k_base (close enough for Qwen-max budgeting)."""
    return len(_enc.encode(text))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to at most max_tokens tokens."""
    tokens = _enc.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return _enc.decode(tokens[:max_tokens])
