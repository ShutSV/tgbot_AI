from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import PostgresDsn


load_dotenv(override=True )


class Settings(BaseSettings):
    DATABASE_PRIVATE_URL: PostgresDsn
    OPENAI_API_KEY: str
    TELEGRAM_TOKEN: str


settings = Settings()
