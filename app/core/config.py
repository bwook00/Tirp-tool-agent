from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    typeform_secret: str = ""
    data_dir: str = "./data/results"
    omio_enabled: bool = False
    omio_search_headless: bool = True
    omio_search_timeout_ms: int = 30000
    passengers_dir: str = "./data/passengers"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
