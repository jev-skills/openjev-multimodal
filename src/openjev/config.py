from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENJEV_", env_file=".env", extra="ignore")

    backend_url: str = "http://127.0.0.1:18081"
    model_name: str = "Qwen/Qwen3.5-0.8B"
    api_key: SecretStr | None = None
    backend_api_key: SecretStr | None = None
    max_body_bytes: int = Field(default=16 * 1024 * 1024, ge=1024)
    max_input_tokens: int = Field(default=8192, ge=512)
    max_total_input_tokens: int = Field(default=131072, ge=512)
    max_concurrent_requests: int = Field(default=4, ge=1, le=64)
    request_timeout: float = Field(default=120, gt=0)
    max_images: int = Field(default=8, ge=1, le=32)
    image_max_edge: int = Field(default=1024, ge=128, le=4096)
    image_max_pixels: int = Field(default=20_000_000, ge=1)
    image_token_budget: int = Field(default=512, ge=64, le=4096)
