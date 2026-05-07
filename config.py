import logging
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")
    # LLM – OpenAI
    openai_api_key: str
    llm_model: str = "gpt-4o-mini"
    llm_max_tokens: int = 1024
    # Valeur basse pour classification déterministe (0.0 = greedy)
    llm_temperature: float = 0.1

    # Base de données SQLite
    db_path: str = "incidents.db"

    # Vector store Chroma
    chroma_path: str = "chroma_db/"
    embedding_model: str = "paraphrase-multilingual-mpnet-base-v2"

    # RAG
    rag_top_k: int = 4
    docs_path: str = "docs/"

    # API REST
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_key: str = "changeme"

    # Chemins données
    data_path: str = "data/"

    # Chroma
    chroma_collection_name: str = "incident_docs"

    # Limites de recherche DB (performance / tuning)
    detect_duplicate_search_limit: int = 10
    detect_major_incident_main_limit: int = 5
    detect_major_incident_deps_max: int = 10
    detect_major_incident_dep_limit: int = 3
    search_incidents_limit: int = 5
    rag_ingest_batch_size: int = 50

    # Limites de contexte LLM (prompt sizing)
    llm_context_alerts_limit: int = 5
    llm_context_rag_docs_limit: int = 4
    llm_rag_doc_truncate_chars: int = 600
    llm_context_similar_incidents_limit: int = 5
    rag_query_description_max_chars: int = 300

    # Agent
    duplicate_window_hours: int = 2
    major_incident_threshold: int = 3
    # En dessous de ce seuil, le résultat est marqué comme incertain
    confidence_low_threshold: float = 0.5
    duplicate_confidence_score: float = 0.95
    # Nombre maximum d'entrées conservées dans la mémoire conversationnelle
    max_memory: int = 10

    # Fallback conservateur quand la qualification LLM échoue ou pour les doublons
    fallback_priority: str = "P3"
    fallback_category: str = "Application"
    fallback_subcategory: str = "Traitement"
    fallback_assigned_to: str = "team-ops"

    # Logs
    log_level: str = "INFO"


def setup_logging(config: Config) -> None:
    """Configure le logging global avec format structuré ISO-8601."""
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
