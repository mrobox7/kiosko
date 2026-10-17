"""Settings read from the environment (see PLAN.md section 3)."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every tunable value. Required LLM settings fail fast when empty."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    backend_url: str = "http://localhost:8000"
    backend_timeout_s: float = 10
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "openai/gpt-oss-120b"
    llm_timeout_s: float = 60
    llm_max_output_tokens: int = 1024
    max_iterations: int = 8
    max_tool_calls_per_turn: int = 12
    tool_result_max_chars: int = 4000
    max_message_chars: int = 1000
    rate_limit_turns_per_min: int = 10
    session_token_budget: int = 200_000
    restaurant_timezone: str = "Asia/Kolkata"
    log_level: str = "INFO"

    def require_llm(self) -> None:
        """Raise if the LLM settings needed to run the agent are missing."""
        if not self.llm_api_key.get_secret_value() or not self.llm_model:
            raise ValueError("LLM_API_KEY and LLM_MODEL must be set (see .env.example)")


settings = Settings()
