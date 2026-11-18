"""Application settings, loaded from environment variables or a .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(ROOT_DIR / ".env", ROOT_DIR / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    company_name: str = "Nilaveli Electronics"
    data_dir: Path = ROOT_DIR / "data"
    admin_api_key: str = "change-me"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_sample_docs: bool = False  # load sample_data/ on startup when the store is empty
    public_base_url: str = ""  # e.g. https://my-space.hf.space (used for Twilio signature checks)

    # LLM provider: "gemini" (free tier), "anthropic" (Claude, paid), or "auto"
    # (auto = Gemini if GEMINI_API_KEY is set, else Claude if ANTHROPIC_API_KEY is set, else offline).
    llm_provider: str = "auto"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    llm_effort: str = "low"  # Claude only
    extraction_effort: str = "medium"  # Claude only
    llm_fallbacks: bool = True  # Claude server-side refusal fallbacks
    llm_offline: bool = False  # force the offline (no-API) mode even if a key is set

    # Embeddings and retrieval
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    reranker_model: str = "Xenova/ms-marco-MiniLM-L-6-v2"
    use_reranker: bool = True
    rerank_candidates: int = 12
    chunk_size: int = 600  # characters
    chunk_overlap: int = 100
    top_k: int = 6
    graph_hops: int = 2
    min_relevance: float = 0.25  # below this the bot says it does not know

    # Conversation memory
    memory_turns: int = 6

    # WhatsApp
    whatsapp_provider: str = "twilio"  # twilio | meta
    whatsapp_dry_run: bool = True  # log outgoing messages instead of sending them
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = "whatsapp:+14155238886"
    meta_verify_token: str = ""
    meta_app_secret: str = ""
    meta_access_token: str = ""
    meta_phone_number_id: str = ""
    meta_graph_version: str = "v21.0"
    rate_limit_per_minute: int = 12

    @property
    def active_provider(self) -> str | None:
        if self.llm_offline:
            return None
        p = self.llm_provider.lower()
        if p == "gemini":
            return "gemini" if self.gemini_api_key else None
        if p == "anthropic":
            return "anthropic" if self.anthropic_api_key else None
        if self.gemini_api_key:
            return "gemini"
        if self.anthropic_api_key:
            return "anthropic"
        return None

    @property
    def llm_enabled(self) -> bool:
        return self.active_provider is not None

    @property
    def llm_model(self) -> str | None:
        return {"gemini": self.gemini_model, "anthropic": self.anthropic_model}.get(self.active_provider or "")

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
