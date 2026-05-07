"""Point d'entrée CLI de l'agent de qualification des incidents SWIFT."""
import json
import logging
from typing import NoReturn, Optional

import typer
from pydantic import ValidationError

app = typer.Typer(
    help="Agent de qualification des incidents SWIFT",
    add_completion=False,
)
logger = logging.getLogger(__name__)


@app.command()
def init(
    db_path: Optional[str] = typer.Option(None, help="Chemin de la base SQLite (défaut : config.db_path)"),
    data_dir: Optional[str] = typer.Option(None, help="Dossier des données mock (défaut : config.data_path)"),
    docs_dir: Optional[str] = typer.Option(None, help="Dossier des docs à indexer dans Chroma (défaut : config.docs_path)"),
    chroma_path: Optional[str] = typer.Option(None, help="Chemin du vector store Chroma (défaut : config.chroma_path)"),
) -> None:
    """Initialiser la base de données SQLite et indexer la documentation dans Chroma."""
    from config import Config, setup_logging
    from db.init_db import init_db
    from rag.ingest import ingest_docs

    config = Config()
    setup_logging(config)
    db_path = db_path or config.db_path
    data_dir = data_dir or config.data_path
    docs_dir = docs_dir or config.docs_path
    chroma_path = chroma_path or config.chroma_path

    typer.echo("→ Initialisation de la base de données SQLite...")
    init_db(db_path=db_path, data_dir=data_dir)
    typer.echo(f"  ✓ Base de données prête : {db_path}")

    typer.echo("→ Indexation de la documentation dans Chroma...")
    chunks = ingest_docs(
        docs_dir=docs_dir, chroma_path=chroma_path,
        embedding_model=config.embedding_model,
        collection_name=config.chroma_collection_name,
        batch_size=config.rag_ingest_batch_size,
    )
    typer.echo(f"  ✓ {chunks} chunks indexés dans {chroma_path}")

    typer.echo("✓ Initialisation terminée. Lancez : python main.py qualify --id INCxxxxxxx")


def _cli_error(code: str, message: str, status: int = 1) -> NoReturn:
    typer.echo(json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False, indent=2))
    raise typer.Exit(code=status)


def _resolve_incident_id(incident_id: Optional[str], json_payload: Optional[str]) -> str:
    """Résoudre l'ID depuis --id ou depuis le champ 'id' du JSON."""
    if incident_id:
        return incident_id
    try:
        parsed = json.loads(json_payload or "")
    except json.JSONDecodeError as exc:
        _cli_error("INVALID_JSON", f"Payload JSON invalide : {exc}")
    resolved = parsed.get("id")
    if not resolved:
        _cli_error("MISSING_ID", "Le JSON doit contenir un champ 'id' (ex: INCxxxxxxx)")
    return resolved


def _fetch_and_validate(db_path: str, incident_id: str):
    """Charger l'incident depuis SQLite et valider les entrées."""
    from db.incidents import IncidentDB
    from security.input_validator import validate_incident_input

    raw = IncidentDB(db_path).get(incident_id)
    if not raw:
        _cli_error("NOT_FOUND", f"Aucun incident trouvé : {incident_id}")
    try:
        return validate_incident_input(raw)
    except ValidationError as exc:
        _cli_error("VALIDATION_ERROR", str(exc))


@app.command()
def qualify(
    incident_id: Optional[str] = typer.Option(None, "--id", help="ID de l'incident (INCxxxxxxx)"),
    json_payload: Optional[str] = typer.Option(None, "--json", help="Payload JSON inline"),
    db_path: Optional[str] = typer.Option(None, help="Chemin de la base SQLite (défaut : config.db_path)"),
) -> None:
    """Qualifier un incident : priorité, catégorie, équipe, suggestions de résolution."""
    from config import Config, setup_logging
    from agent import Agent, AgentError

    if not incident_id and not json_payload:
        _cli_error("MISSING_ARGUMENT", "Fournir --id ou --json")
    config = Config()
    setup_logging(config)
    db_path = db_path or config.db_path
    resolved_id = _resolve_incident_id(incident_id, json_payload)
    incident_input = _fetch_and_validate(db_path, resolved_id)
    try:
        result = Agent(config).qualify(incident_input)
    except AgentError as exc:
        _cli_error("AGENT_ERROR", str(exc))
    typer.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


@app.command()
def serve(
    host: Optional[str] = typer.Option(None, help="Adresse d'écoute (défaut : config.api_host)"),
    port: Optional[int] = typer.Option(None, help="Port HTTP (défaut : config.api_port)"),
    reload: bool = typer.Option(False, help="Rechargement automatique (dev)"),
) -> None:
    """Lancer le serveur API FastAPI via uvicorn."""
    from config import Config
    import uvicorn
    config = Config()
    uvicorn.run("api:app", host=host or config.api_host, port=port or config.api_port, reload=reload)


if __name__ == "__main__":
    app()
