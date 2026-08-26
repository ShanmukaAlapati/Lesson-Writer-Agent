from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from exceptions import ConfigurationError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Shared fallback -- used by either role if its own override isn't set.
    groq_api_key: str = Field(default="")
    groq_model_name: str = Field(default="")

    # Optional per-role overrides.
    groq_generate_api_key: str = Field(default="")
    groq_evaluate_api_key: str = Field(default="")
    groq_generate_model_name: str = Field(default="")
    groq_evaluate_model_name: str = Field(default="")

    # Tried in order after the primary model fails.
    groq_generate_model_fallbacks: str = Field(default="")
    groq_evaluate_model_fallbacks: str = Field(default="")

    max_retries: int = Field(default=2, ge=0, le=5)
    max_tokens_generate: int = Field(default=1800, gt=0)
    max_tokens_evaluate: int = Field(default=1000, gt=0)

    memory_db_path: str = Field(default="pitfalls.db")
    output_dir: str = Field(default="output")
    log_level: str = Field(default="INFO")

    def resolved_generate_key(self) -> str:
        return self.groq_generate_api_key or self.groq_api_key

    def resolved_evaluate_key(self) -> str:
        return self.groq_evaluate_api_key or self.groq_api_key

    def resolved_generate_model(self) -> str:
        return self.groq_generate_model_name or self.groq_model_name

    def resolved_evaluate_model(self) -> str:
        return self.groq_evaluate_model_name or self.groq_model_name

    def resolved_generate_models(self) -> list[str]:
        fallbacks = [m.strip() for m in self.groq_generate_model_fallbacks.split(',')] if self.groq_generate_model_fallbacks else []
        return [self.resolved_generate_model()] + fallbacks

    def resolved_evaluate_models(self) -> list[str]:
        fallbacks = [m.strip() for m in self.groq_evaluate_model_fallbacks.split(',')] if self.groq_evaluate_model_fallbacks else []
        return [self.resolved_evaluate_model()] + fallbacks


def get_settings() -> Settings:
    settings = Settings()
    missing = []

    if not settings.resolved_generate_key():
        missing.append("generation (set GROQ_API_KEY or GROQ_GENERATE_API_KEY)")
    if not settings.resolved_evaluate_key():
        missing.append("evaluation (set GROQ_API_KEY or GROQ_EVALUATE_API_KEY)")
    if missing:
        raise ConfigurationError(
            "Missing API key for: " + "; ".join(missing) + ". "
            "Copy .env.example to .env and fill it in."
        )
    return settings
