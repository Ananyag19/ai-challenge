from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = 8080

    team_name: str = "Team Name"
    team_members: str = "Member One"
    bot_model: str = "none"
    bot_approach: str = "deterministic pipeline with stub composer"
    contact_email: str = "team@example.com"
    bot_version: str = "0.1.0"
    submitted_at: str = "2026-04-26T08:00:00Z"

    default_wait_seconds: int = 1800
    auto_reply_end_after: int = 3

    groq_api_key: str = ""
    llm_model: str = "openai/gpt-oss-20b"

    def team_members_list(self) -> list[str]:
        return [part.strip() for part in self.team_members.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
