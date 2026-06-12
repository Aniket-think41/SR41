"""
Settings — every value can come from the environment / .env file.
See .env.example for the full annotated list.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- core ---
    env: str = "development"  # development | production
    database_url: str = "sqlite:///./skillshare.db"  # use postgresql+psycopg2://… in prod

    # --- auth / JWT (BACKEND_SPEC §4.1) ---
    # HS256 + jwt_secret by default (dev). For RS256 set jwt_algorithm=RS256
    # and provide the PEM keypair.
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_private_key: str = ""  # PEM, required when jwt_algorithm=RS256
    jwt_public_key: str = ""   # PEM, required when jwt_algorithm=RS256
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- Google OAuth (POST /api/auth/google) ---
    google_client_id: str = ""  # empty → endpoint returns a clear 403

    # --- CORS: the dashboard origin(s), comma-separated ---
    cors_origins: str = "http://localhost:3001"

    # --- rate limiting (BACKEND_SPEC §4.3) ---
    rate_limit_enabled: bool = True
    rate_limit_auth_per_min: int = 10
    rate_limit_write_per_min: int = 60
    rate_limit_search_per_min: int = 30
    redis_url: str = ""  # optional; in-memory limiter is used when empty (single-process only)

    # --- uploads (BACKEND_SPEC §6) ---
    storage_backend: str = "local"   # local | s3  (switchable; see app/storage.py)
    upload_dir: str = "var/uploads"  # local backend: where files are written
    public_base_url: str = "http://localhost:8400"  # local backend: base for /uploads URLs
    s3_bucket: str = ""
    s3_region: str = "auto"
    s3_endpoint_url: str = ""        # e.g. Cloudflare R2 endpoint
    s3_public_base_url: str = ""     # public CDN base for stored files
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    max_upload_mb: int = 50          # images/diagrams/short clips; raise for video

    # --- licensing (BACKEND_SPEC §3.7) ---
    license_key_pattern: str = r"^T41-PREM-[A-Z0-9]{4,}$"

    # --- seed script ---
    seed_password: str = "skillshare-demo"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def jwt_signing_key(self) -> str:
        return self.jwt_private_key if self.jwt_algorithm.startswith("RS") else self.jwt_secret

    @property
    def jwt_verify_key(self) -> str:
        return self.jwt_public_key if self.jwt_algorithm.startswith("RS") else self.jwt_secret


@lru_cache
def get_settings() -> Settings:
    return Settings()
