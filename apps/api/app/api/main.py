import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.queue import QueueClient
from app.api.routes import campaigns, contacts, overview
from app.config import get_settings
from app.logging import configure_logging
from app.services.errors import ServiceError

log = logging.getLogger("pulse.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.queue = QueueClient()
    await app.state.queue.ensure_connected()
    yield
    await app.state.queue.close()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, "api")
    app = FastAPI(
        title="Pulse API",
        description="Campaign & notification manager (demo). Deliveries are simulated; no email is sent.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError):
        return JSONResponse({"detail": exc.message, "errors": exc.errors}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
            field = loc[0] if loc else "request"
            message = err.get("msg", "Invalid value").removeprefix("Value error, ")
            if err.get("type") == "datetime_from_date_parsing" or "datetime" in err.get("type", ""):
                message = "Enter a valid date and time."
            errors.setdefault(field, message)
        return JSONResponse({"detail": "Please fix the highlighted fields.", "errors": errors}, status_code=422)

    @app.get("/", include_in_schema=False)
    def root():
        return {"name": "Pulse API", "docs": "/docs", "health": "/api/health"}

    app.include_router(overview.router)
    app.include_router(campaigns.router)
    app.include_router(contacts.router)
    return app


app = create_app()
