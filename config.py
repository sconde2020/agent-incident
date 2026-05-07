import logging
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    # LLM – OpenAI
    openai_api_key: str
    llm_model: str = "gpt-4o"
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

    # Agent
    duplicate_window_hours: int = 2
    major_incident_threshold: int = 3
    # En dessous de ce seuil, le résultat est marqué comme incertain
    confidence_low_threshold: float = 0.5

    # Logs
    log_level: str = "INFO"

    class Config:
        env_file = ".env"


def setup_logging(config: Config) -> None:
    """Configure le logging global avec format structuré ISO-8601."""
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
