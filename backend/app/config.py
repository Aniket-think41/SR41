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
    access_token_expire_minutes: int = 7 * 24 * 60  # 7 days
    refresh_token_expire_days: int = 15

    # --- Google OAuth (POST /api/auth/google) ---
    google_client_id: str = ""  # empty → endpoint returns a clear 403

    # --- Microsoft / Azure AD OAuth (POST /api/auth/microsoft) ---
    # Empty client id → the endpoint returns a clear 403 and the dashboard button
    # explains it's off. tenant is "common" (any Microsoft account) unless you
    # restrict to a single Azure AD tenant id.
    microsoft_client_id: str = ""
    microsoft_tenant: str = "common"

    # --- dashboard origin: where the CLI/MCP device-login verification page lives ---
    frontend_url: str = "http://localhost:3001"

    # --- CORS: the dashboard origin(s), comma-separated ---
    cors_origins: str = "http://localhost:3001"

    # --- rate limiting (BACKEND_SPEC §4.3) ---
    rate_limit_enabled: bool = True
    rate_limit_auth_per_min: int = 10
    rate_limit_write_per_min: int = 60
    rate_limit_search_per_min: int = 30
    redis_url: str = ""  # optional; in-memory limiter is used when empty (single-process only)

    # --- AWS SES SMTP (org invitation emails) ---
    # SES is best-effort: if disabled or misconfigured, invitations are still
    # created in the DB and the admin gets a server log warning.
    ses_enabled: bool = False       # set True in prod
    ses_sender: str = ""            # verified SES identity, e.g. noreply@skillshare.think41.com
    ses_smtp_username: str = ""     # SES SMTP credentials (not IAM access key)
    ses_smtp_password: str = ""
    ses_smtp_host: str = "email-smtp.us-west-2.amazonaws.com"
    ses_smtp_port: int = 587

    # --- uploads (BACKEND_SPEC §6) ---
    # Switchable storage (see app/storage.py). local for dev; gcs is the default
    # cloud provider, s3 the alternative.
    storage_backend: str = "local"   # local | gcs | s3
    upload_dir: str = "var/uploads"  # local backend: where files are written
    public_base_url: str = "http://localhost:8400"  # local backend: base for /uploads URLs

    # -- gcs backend (Google Cloud Storage — default cloud) --
    gcs_bucket: str = ""
    gcs_project: str = ""            # optional; inferred from credentials when empty
    gcs_credentials_file: str = ""   # path to a service-account JSON; empty → Application Default Credentials
    gcs_public_base_url: str = ""    # public CDN base; empty → https://storage.googleapis.com/<bucket>

    # -- s3 backend (AWS S3 / Cloudflare R2 / MinIO — alternative) --
    s3_bucket: str = ""
    s3_region: str = "auto"
    s3_endpoint_url: str = ""        # e.g. Cloudflare R2 endpoint
    s3_public_base_url: str = ""     # public CDN base for stored files
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    max_upload_mb: int = 50          # images/diagrams/short clips; raise for video

    # --- licensing (BACKEND_SPEC §3.7) ---
    license_key_pattern: str = r"^T41-PREM-[A-Z0-9]{4,}$"

    # --- payments: Razorpay (spec §5) ---
    # Scaffolded now, activates when credentials are present. Empty → payments are
    # disabled gracefully (checkout returns a clear "not configured" error and the
    # UI hides upgrade buttons). Adding these later turns it on with no code change.
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""

    # --- caching: Redis (spec §8) ---
    # Reuses redis_url (above). Empty → cache is a no-op pass-through, callers fall
    # back to hitting the DB directly. cache_default_ttl is seconds.
    cache_enabled: bool = True
    cache_default_ttl: int = 60

    # --- error monitoring: Sentry (spec §8) ---
    # Empty DSN → Sentry init is skipped (no-op). Set to activate.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 0.0

    # --- admin bootstrap (production) ---
    # Set ADMIN_EMAIL + ADMIN_PASSWORD to auto-create an admin user on startup.
    # This is the only way to get an admin in production without running the
    # seed script. The user is created if they don't exist, or promoted to
    # admin if they already have an account.
    admin_email: str = ""
    admin_password: str = ""

    # --- signup email verification (OTP) ---
    # A one-time code is emailed on signup; the account is created only after it's
    # verified. When SES isn't configured the code is returned in the API response
    # (and logged) so the flow still works without email — set this False to force
    # email-only delivery even without SES (locks out signup until SES is set up).
    otp_length: int = 6
    otp_ttl_minutes: int = 10
    otp_max_attempts: int = 5
    otp_dev_return: bool = True  # expose the code in the response when email can't send

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
