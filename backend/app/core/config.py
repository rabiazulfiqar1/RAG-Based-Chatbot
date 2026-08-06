from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SUPABASE_URL: str = ""
    SUPABASE_DB_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    GROQ_API_KEY: str = ""
    NVIDIA_API_KEY: str = ""
    SUPABASE_DB_SQLALCHEMY_URL: str = ""
    SUPABASE_DB_POOL_URL: str = ""

    REDIS_URL: str

    # This is the modern syntax for Pydantic V2
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding='utf-8')

settings = Settings()