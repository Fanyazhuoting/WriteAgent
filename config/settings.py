from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM
    dashscope_api_key: str = ""
    qwen_model_name: str = "qwen-max"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_temperature: float = 0.8
    llm_max_tokens: int = 2048

    # ChromaDB
    chroma_persist_dir: str = "./chroma_data"

    # Context Management
    sliding_window_size: int = 5
    hot_context_max_tokens: int = 8000
    retrieval_k: int = 8

    # Negotiation
    max_negotiation_rounds: int = 3

    # LangSmith
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "WriteAgent"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    # Prompt Registry
    prompt_version: str = "v1"
    prompts_dir: str = "./prompts"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
