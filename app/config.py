from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_TITLE: str
    MONGODB_URL: str
    DEV_URL: str
    PRODUCTION_MODE: bool
    SECRET_KEY: str
    ALGORITHM: str
    SMTP_USER: str
    SMTP_USER_PWD: str
    SMTP_HOST: str
    SMTP_PORT: int

    class Config:
        env_file = ".env"

settings = Settings()