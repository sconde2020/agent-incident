"""Point d'entrée CLI de l'agent de qualification des incidents SWIFT."""
import json
import logging
from typing import NoReturn, Optional

import typer

app = typer.Typer(
    help="Agent de qualification des incidents SWIFT",
    add_completion=False,
)
logger = logging.getLogger(__name__)


@app.command()
def init(
    db_path: str = typer.Option("incidents.db", help="Chemin de la base SQLite"),
    data_dir: str = typer.Option("data/", help="Dossier des données mock"),
    docs_dir: str = typer.Option("docs/", help="Dossier des docs à indexer dans Chroma"),
    chroma_path: str = typer.Option("chroma_db/", help="Chemin du vector store Chroma"),
) -> None:
    """Initialiser la base de données SQLite et indexer la documentation dans Chroma."""
    from config import Config, setup_logging
    from db.init_db import init_db
    from rag.ingest import ingest_docs

    config = Config()
    setup_logging(config)

    typer.echo("→ Initialisation de la base de données SQLite...")
    init_db(db_path=db_path, data_dir=data_dir)
    typer.echo(f"  ✓ Base de données prête : {db_path}")

    typer.echo("→ Indexation de la documentation dans Chroma...")
    chunks = ingest_docs(docs_dir=docs_dir, chroma_path=chroma_path)
    typer.echo(f"  ✓ {chunks} chunks indexés dans {chroma_path}")

    typer.echo("✓ Initialisation terminée. Lancez : python main.py qualify --id INCxxxxxxx")


@app.command()
def qualify(
    incident_id: Optional[str] = typer.Option(None, "--id", help="ID de l'incident (INCxxxxxxx)"),
    json_payload: Optional[str] = typer.Option(None, "--json", help="Payload JSON inline"),
    db_path: str = typer.Option("incidents.db", help="Chemin de la base SQLite"),
) -> None:
    """Qualifier un incident : priorité, catégorie, équipe, suggestions de résolution."""
    from config import Config, setup_logging
    from agent import Agent, AgentError
    from security.input_validator import validate_incident_input
    from pydantic import ValidationError

    def _error(code: str, message: str, status: int = 1) -> NoReturn:
        typer.echo(json.dumps({"error": {"code": code, "message": message}}, ensure_ascii=False, indent=2))
        raise typer.Exit(code=status)

    config = Config()
    setup_logging(config)

    if not incident_id and not json_payload:
        _error("MISSING_ARGUMENT", "Fournir --id ou --json")

    from db.incidents import IncidentDB
    db = IncidentDB(db_path)

    # Résoudre l'ID : depuis --id directement, ou depuis le champ "id" du JSON
    if incident_id:
        resolved_id = incident_id
    else:
        try:
            parsed = json.loads(json_payload or "")
        except json.JSONDecodeError as exc:
            _error("INVALID_JSON", f"Payload JSON invalide : {exc}")
        resolved_id = parsed.get("id")
        if not resolved_id:
            _error("MISSING_ID", "Le JSON doit contenir un champ 'id' (ex: INCxxxxxxx)")

    # L'incident doit exister en base – pas de création à la volée
    raw = db.get(resolved_id)
    if not raw:
        _error("NOT_FOUND", f"Aucun incident trouvé : {resolved_id}")

    # Validation des entrées
    try:
        incident_input = validate_incident_input(raw)
    except ValidationError as exc:
        _error("VALIDATION_ERROR", str(exc))

    # Qualification
    try:
        result = Agent(config).qualify(incident_input)
    except AgentError as exc:
        _error("AGENT_ERROR", str(exc))

    typer.echo(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Adresse d'écoute"),
    port: int = typer.Option(8080, help="Port HTTP"),
    reload: bool = typer.Option(False, help="Rechargement automatique (dev)"),
) -> None:
    """Lancer le serveur API FastAPI via uvicorn."""
    import uvicorn
    uvicorn.run("api:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
