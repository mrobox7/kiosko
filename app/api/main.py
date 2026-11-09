"""Entry point: `uvicorn app.api.main:app --port 8001`."""

from app.api.app import create_app
from app.config.observability import configure_logging
from app.runtime import build_runtime

app = create_app(build_runtime())
configure_logging(app)
