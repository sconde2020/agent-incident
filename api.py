import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from agent import Agent, AgentError
from config import Config, setup_logging
from monitoring import RequestMonitor
from db.models import IncidentCreated, IncidentOut
from security.auth import require_auth, set_api_key
from security.input_validator import validate_incident_input

logger = logging.getLogger(__name__)

_INC_RE = re.compile(r"^INC\d{7}$")

# ─── État global de l'application ─────────────────────────────────────────────
_config: Optional[Config] = None
_agent: Optional[Agent] = None
_monitor: Optional[RequestMonitor] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialisation au démarrage, nettoyage à l'arrêt."""
    global _config, _agent, _monitor
    _config = Config()
    setup_logging(_config)
    set_api_key(_config.api_key)
    _monitor = RequestMonitor(model=_config.llm_model)
    _agent = Agent(_config, monitor=_monitor)
    logger.info("api.startup model=%s host=%s port=%d", _config.llm_model, _config.api_host, _config.api_port)
    yield
    logger.info("api.shutdown")


app = FastAPI(
    title="Agent de qualification des incidents SWIFT",
    version="1.0.0",
    lifespan=lifespan,
)

# ─── Schéma de sécurité Swagger ───────────────────────────────────────────────

_orig_openapi = app.openapi


def _openapi_with_bearer():
    schema = _orig_openapi()
    schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
    }
    for path, path_item in schema.get("paths", {}).items():
        if path == "/health":
            continue
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation["security"] = [{"BearerAuth": []}]
    return schema


app.openapi = _openapi_with_bearer


# ─── Middleware de traçage ─────────────────────────────────────────────────────

@app.middleware("http")
async def trace_requests(request: Request, call_next):
    """Ajouter un X-Request-ID et mesurer la latence sur chaque requête."""
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start = time.monotonic()

    response = await call_next(request)

    duration_ms = int((time.monotonic() - start) * 1000)
    logger.info(
        "api.request method=%s path=%s status=%d duration_ms=%d request_id=%s",
        request.method, request.url.path, response.status_code, duration_ms, request_id,
    )
    response.headers["X-Request-ID"] = request_id
    return response


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.post("/qualify", response_model=IncidentOut, dependencies=[Depends(require_auth)])
async def qualify_incident(request: Request, payload: dict) -> IncidentOut:
    """Qualifier un incident – l'incident doit exister en base (créé via POST /create)."""
    request_id = getattr(request.state, "request_id", "?")

    incident_id = payload.get("id")
    if not incident_id:
        raise HTTPException(status_code=422, detail="Le champ 'id' est obligatoire. Créez d'abord l'incident via POST /create.")
    if not _INC_RE.match(incident_id):
        raise HTTPException(status_code=400, detail="Format d'identifiant invalide (attendu INCxxxxxxx)")

    raw = _agent.incident_db.get(incident_id)
    if not raw:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} non trouvé. Créez-le d'abord via POST /create.")

    try:
        validated = validate_incident_input(raw)
    except ValidationError as exc:
        logger.warning("api.qualify.validation_error errors=%s request_id=%s", exc, request_id)
        raise HTTPException(status_code=422, detail=exc.errors())

    try:
        result = _agent.qualify(validated)
    except AgentError as exc:
        logger.error("api.qualify.agent_error error=%s request_id=%s", exc, request_id)
        raise HTTPException(status_code=500, detail="Erreur interne de l'agent")

    return result


@app.post("/create", response_model=IncidentCreated, dependencies=[Depends(require_auth)])
async def create_incident(request: Request, payload: dict) -> IncidentCreated:
    """Créer un incident brut en base pour simuler un cas réel avant qualification."""
    request_id = getattr(request.state, "request_id", "?")

    try:
        validated = validate_incident_input(payload)
    except ValidationError as exc:
        logger.warning("api.create.validation_error errors=%s request_id=%s", exc, request_id)
        raise HTTPException(status_code=422, detail=exc.errors())

    try:
        created = _agent.incident_db.create(validated.model_dump(exclude_none=False))
    except Exception as exc:
        logger.error("api.create.db_error error=%s request_id=%s", exc, request_id)
        raise HTTPException(status_code=500, detail="Erreur lors de la création de l'incident")

    return IncidentCreated(**created)


@app.get("/incidents/{incident_id}", dependencies=[Depends(require_auth)])
async def get_incident(incident_id: str) -> dict:
    """Récupérer un incident qualifié par son identifiant."""
    if not _INC_RE.match(incident_id):
        raise HTTPException(status_code=400, detail="Format d'identifiant invalide (attendu INCxxxxxxx)")

    incident = _agent.incident_db.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} non trouvé")
    return incident


@app.get("/health")
async def health_check() -> dict:
    """Health check – vérifie la disponibilité de l'agent et du LLM configuré."""
    return {
        "status": "ok",
        "model": _config.llm_model if _config else "unknown",
        "version": "1.0.0",
    }


@app.get("/metrics", dependencies=[Depends(require_auth)])
async def get_metrics() -> dict:
    """Métriques de l'agent : qualifications, erreurs, latence, tokens, coût estimé."""
    assert _monitor is not None
    return _monitor.get_stats()


# ─── Gestionnaire d'erreurs global ────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("api.unhandled_exception error=%s path=%s", exc, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erreur interne du serveur"})
