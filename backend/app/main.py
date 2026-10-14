"""The FastAPI app: builds the shared clients at startup, sets CORS, and
registers every router behind App Check (health aside)."""

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common import setup_logging
from config import FilesLocationConstants, settings
from app.api.dependencies import require_app_check
from app.api.routes.health import router as health_router
from app.api.routes.chat_message import router as chat_router
from app.api.routes.session import router as session_router
from app.api.routes.chat_run import router as chat_run_router
from app.api.routes.feedback import router as feedback_router, review_router

setup_logging(
    environment=settings.app.ENVIRONMENT,
    log_file=FilesLocationConstants.LOG_DIR / "dev_log.log",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the clients, the database engine and the `Orchestrator` once, and
    park them on `app.state` for the routes' dependencies."""
    from common.context import AppContext
    from app.orchestration.orchestrator import Orchestrator

    logger.info("Starting App lifespan")
    async with AppContext(settings) as ctx:
        app.state.openai_client = ctx.openai_client
        app.state.sqlalchemy_engine = ctx.engine
        app.state.sqlalchemy_session_factory = ctx.session_factory
        app.state.app_env = ctx.app_env
        app.state.orchestrator = Orchestrator()
        logger.info(f"App ready in {app.state.app_env.upper()}")

        yield

    logger.info("Ending App lifespan")


# 1. the app
app = FastAPI(
    title="BookShelf API",
    description="AI assistant for finding books",
    version="1.0.0",
    lifespan=lifespan,
)

# 2. CORS
# NOTE: origins come from APP_ALLOW_ORIGINS, as exact matches: never "*", since
# credentials are allowed and browsers reject the wildcard with them. Methods and
# headers are the ones frontend/src/api.js sends, so a new verb or header is a
# deliberate line here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-Firebase-AppCheck"],
)

# 3. the routers
# NOTE: health stays open, since `make deploy-check` and the Cloud Run startup
# probe call /ready. Everything else needs App Check, applied per router so a
# new route on one of them is covered by default.
app.include_router(health_router)
app_check = [Depends(require_app_check)]
app.include_router(chat_router, dependencies=app_check)
app.include_router(session_router, dependencies=app_check)
app.include_router(feedback_router, dependencies=app_check)
# the review surface reads every session's turns and has no admin gate, so
# production doesn't serve it: review locally with `make dev-neon`
if settings.app.ENVIRONMENT != "production":
    app.include_router(chat_run_router, dependencies=app_check)
    app.include_router(review_router, dependencies=app_check)
