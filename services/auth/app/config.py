from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # No defaults on purpose: the service refuses to start without them.
    database_url: str
    jwt_secret: str
    jwt_expire_minutes: int = 60 * 24  # tokens last 24 hours


settings = Settings()
