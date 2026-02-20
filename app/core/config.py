from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    typeform_secret: str = ""
    data_dir: str = "./data/results"
    omio_enabled: bool = False
    passengers_dir: str = "./data/passengers"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
