"""
Centralised settings — loaded once from environment variables / .env file.
"""

from __future__ import annotations

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class SmtpSettings(BaseModel):
    host: str = "smtp.gmail.com"
    port: int = 587
    user: str = ""
    password: str = ""      # Gmail app password or SendGrid key
    from_addr: str = ""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_nested_delimiter="__",
    )

    # ------------------------------------------------------------------ #
    # Scheduler                                                            #
    # ------------------------------------------------------------------ #
    CRON_SCHEDULE: str = "0 23 * * *"       # scrape once daily at 23:00
    TIMEZONE: str = "Asia/Ho_Chi_Minh"

    # ------------------------------------------------------------------ #
    # LLM — choose "ollama" or "openai"                                   #
    # ------------------------------------------------------------------ #
    LLM_PROVIDER: str = "ollama"

    # Ollama (local)
    OLLAMA_MODEL: str = "ollama/llama3.2"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_TOKENS: int = 8192

    # OpenAI (or compatible)
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "openai/gpt-4o-mini"

    # Groq
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "groq/llama-3.1-8b-instant"

    # Google Gemini
    GOOGLE_API_KEY: str = ""
    GEMINI_MODEL: str = "google_genai/gemini-2.0-flash"

    LLM_VERBOSE: bool = False
    BROWSER_HEADLESS: bool = True

    # ------------------------------------------------------------------ #
    # Scraping targets                                                     #
    # ------------------------------------------------------------------ #
    TARGET_ASINS: str = "B08N5WRWNW"

    AMAZON_PRODUCT_URL: str = "https://www.amazon.com/dp/{asin}"

    REQUEST_DELAY: float = 2.0

    # ------------------------------------------------------------------ #
    # Storage                                                              #
    # ------------------------------------------------------------------ #
    OUTPUT_DIR: str = "data"
    OUTPUT_FORMAT: str = "json"   # json | csv

    BROWSER_STATE_PATH: str = "data/browser_state.json"
    DB_PATH: str = "data/tracker.db"

    # ------------------------------------------------------------------ #
    # Email / SMTP                                                         #
    # ------------------------------------------------------------------ #
    smtp: SmtpSettings = SmtpSettings()

    # Comma-separated fallback recipients; overridden by per-book email in registry
    EMAIL_TO: str = ""
    EMAIL_DIGEST_CRON: str = "30 23 * * *"  # daily 23:30 local time (after scrape)

    # ------------------------------------------------------------------ #
    # Web UI                                                               #
    # ------------------------------------------------------------------ #
    WEB_PORT: int = 8080
    WEB_BASE_URL: str = "http://localhost:8080"

    # ------------------------------------------------------------------ #
    # Amazon credentials                                                   #
    # ------------------------------------------------------------------ #
    AMAZON_EMAIL: str = ""
    AMAZON_PASSWORD: str = ""

    # ------------------------------------------------------------------ #
    # Logging                                                              #
    # ------------------------------------------------------------------ #
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "logs"

    @property
    def asins(self) -> list[str]:
        return [a.strip() for a in self.TARGET_ASINS.split(",") if a.strip()]

    @property
    def email_recipients(self) -> list[str]:
        return [e.strip() for e in self.EMAIL_TO.split(",") if e.strip()]


settings = Settings()


def build_graph_config() -> dict:
    """Build the graph_config dict expected by SmartScraperGraph."""
    provider = settings.LLM_PROVIDER.lower()

    if provider == "ollama":
        llm_cfg: dict = {
            "model": settings.OLLAMA_MODEL,
            "model_tokens": settings.OLLAMA_MODEL_TOKENS,
            "format": "json",
            "base_url": settings.OLLAMA_BASE_URL,
        }
    elif provider == "openai":
        llm_cfg = {
            "api_key": settings.OPENAI_API_KEY,
            "model": settings.OPENAI_MODEL,
        }
    elif provider == "groq":
        llm_cfg = {
            "api_key": settings.GROQ_API_KEY,
            "model": settings.GROQ_MODEL,
        }
    elif provider == "gemini":
        llm_cfg = {
            "api_key": settings.GOOGLE_API_KEY,
            "model": settings.GEMINI_MODEL,
        }
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{settings.LLM_PROVIDER}'. "
            "Valid options: ollama, openai, groq, gemini"
        )

    return {
        "llm": llm_cfg,
        "verbose": settings.LLM_VERBOSE,
        "headless": settings.BROWSER_HEADLESS,
    }
