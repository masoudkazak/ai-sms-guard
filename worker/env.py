import os


DATABASE_URL = os.environ.get(
    "DATABASE_URL_SYNC",
    os.environ.get("DATABASE_URL").replace("postgresql+asyncpg", "postgresql").replace("+asyncpg", ""),
)

MOCK_DLR_OVERRIDE = os.environ.get("MOCK_DLR", "").upper() or None

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL")
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL").rstrip("/")
OPENROUTER_TIMEOUT = int(os.environ.get("OPENROUTER_TIMEOUT", "300"))

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
AI_DAILY_CALL_LIMIT = int(os.environ.get("AI_DAILY_CALL_LIMIT", "50"))

RABBITMQ_URL = os.environ.get("RABBITMQ_URL")
RABBITMQ_MAIN_QUEUE = os.environ.get("RABBITMQ_MAIN_QUEUE")
RABBITMQ_REVIEW_QUEUE = os.environ.get("RABBITMQ_REVIEW_QUEUE")
RABBITMQ_DLQ = os.environ.get("RABBITMQ_DLQ")

WATCH_PATH = os.environ.get("WATCH_PATH", "/app")

DUPLICATE_WINDOW_SECONDS = int(os.environ.get("DUPLICATE_WINDOW_SECONDS", "300"))
MAX_RETRY_BEFORE_DLQ = int(os.environ.get("MAX_RETRY_BEFORE_DLQ", "3"))
MULTIPART_SEGMENT_THRESHOLD = int(os.environ.get("MULTIPART_SEGMENT_THRESHOLD", "2"))
