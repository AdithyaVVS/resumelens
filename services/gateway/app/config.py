from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # A service whose address is empty is switched off: the gateway does not route to
    # it and does not report on it. Later steps turn the others on in docker-compose.
    auth_url: str = ""
    resume_url: str = ""
    analysis_url: str = ""
    jobs_url: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    auth_rate_limit: int = 10
    max_body_bytes: int = 65536

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
