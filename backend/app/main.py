from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from common import setup_logging
from config import FilesLocationConstants

import logging
setup_logging(
    environment=settings.app.ENVIRONMENT, 
    log_file=FilesLocationConstants.LOG_DIR / "dev_log.log"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI): 
    from common.context import AppContext
    from app.orchestration.orchestrator import Orchestrator
    
    logger.info("Starting App lifespan")
    async with AppContext(settings) as ctx:
        
        app.state.openai_client = ctx.openai_client
        logger.info("OpenAI client set")
        
        app.state.sqlalchemy_engine = ctx.engine
        logger.info("SQLAlchemy engine set")
        
        app.state.sqlalchemy_session_factory = ctx.session_factory
        logger.info("SQLAlchemy session factory set")
        
        app.state.app_env = ctx.app_env
        logger.info(f"App environment set to: {app.state.app_env.upper()}")
        
        app.state.orchestrator = Orchestrator()
        logger.info("Orchestrator set")
        
        yield
    
    logger.info("Ending App lifespan")


app = FastAPI(
    title="BookShelf API",
    description="AI-powered book recommendation system",
    version="3.0.0",
    lifespan=lifespan
)

# CORS. Origins come from APP_ALLOW_ORIGINS (exact matches, never "*": this
# sends credentials, and browsers reject the wildcard outright when they are
# allowed). Methods and headers are the ones frontend/src/api.js actually
# sends — GET, POST and PUT over application/json, plus the App Check token —
# rather than "*", so a new verb or header is a deliberate line here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.app.ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["Content-Type", "X-Firebase-AppCheck"],
)

# Include routers
from fastapi import Depends
from app.api.dependencies import require_app_check
from app.api.routes.health import router as health_router
from app.api.routes.chat_message import router as chat_router
from app.api.routes.session import router as session_router
from app.api.routes.chat_run import router as chat_run_router
from app.api.routes.feedback import router as feedback_router

# Health stays open: `make deploy-check` and the Cloud Run startup probe curl
# /ready, and none of the three reaches OpenAI. Everything else needs App Check,
# applied per router so a route added to one of them is covered by default.
app.include_router(health_router)
app_check = [Depends(require_app_check)]
app.include_router(chat_router, dependencies=app_check)
app.include_router(session_router, dependencies=app_check)
# The review surface serves every user's messages and has no admin gate yet
# (docs/deployment.md §4.1), so production doesn't serve it at all: review
# locally with `make dev-neon`, which reads the same database.
if settings.app.ENVIRONMENT != "production":
    app.include_router(chat_run_router, dependencies=app_check)
    app.include_router(feedback_router, dependencies=app_check)