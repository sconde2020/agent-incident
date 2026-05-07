import hmac
import logging
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Injecté au démarrage depuis config.api_key
_api_key: str = ""

# Déclare le schéma Bearer dans l'OpenAPI → bouton "Authorize" dans Swagger
_bearer_scheme = HTTPBearer(auto_error=False)


def set_api_key(key: str) -> None:
    global _api_key
    _api_key = key


def verify_api_key(provided: str) -> bool:
    if not _api_key:
        logger.error("auth.api_key_not_configured")
        return False
    # Comparaison à durée constante pour prévenir les attaques timing
    return hmac.compare_digest(provided.encode(), _api_key.encode())


async def require_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> None:
    """Dépendance FastAPI – vérifie le header Authorization: Bearer <key>."""
    if not credentials or not verify_api_key(credentials.credentials):
        ip = request.client.host if request.client else "unknown"
        logger.warning("auth.invalid_key ip=%s", ip)
        raise HTTPException(status_code=401, detail="Non autorisé")
