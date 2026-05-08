import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _get_doc_type(stem: str) -> str:
    if stem.startswith("runbook"):
        return "runbook"
    if stem.startswith("postmortem"):
        return "postmortem"
    if stem.startswith("faq"):
        return "faq"
    return "doc"


def _process_md_file(md_file: Path, splitter, counter_start: int) -> tuple[list, list, list]:
    content = md_file.read_text(encoding="utf-8")
    chunks = splitter.split_text(content)
    doc_type = _get_doc_type(md_file.stem)
    docs, ids, metadatas = [], [], []
    for i, chunk in enumerate(chunks):
        headers = " | ".join(chunk.metadata.values()) if chunk.metadata else ""
        # Inclure les titres de sections dans le texte pour améliorer le recall sémantique
        full_text = f"[{headers}]\n{chunk.page_content}" if headers else chunk.page_content
        docs.append(full_text)
        ids.append(f"{md_file.stem}_{counter_start + i}")
        metadatas.append({"source_file": md_file.name, "section_title": headers, "doc_type": doc_type})
    return docs, ids, metadatas


def _init_collection(chroma_path: str, embedding_fn, collection_name: str):
    import chromadb
    client = chromadb.PersistentClient(path=chroma_path)
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass
    return client.create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )


def _batch_insert(collection, all_docs: list, all_ids: list, all_metadatas: list, batch_size: int) -> None:
    for i in range(0, len(all_docs), batch_size):
        collection.add(
            documents=all_docs[i:i + batch_size],
            ids=all_ids[i:i + batch_size],
            metadatas=all_metadatas[i:i + batch_size],
        )


def _collect_md_files(docs_dir: str) -> list[Path]:
    """Retourner les .md de docs_dir ; liste vide si répertoire absent ou sans fichier."""
    docs_path = Path(docs_dir)
    if not docs_path.exists():
        logger.warning("rag.ingest.docs_dir_not_found path=%s", docs_dir)
        return []
    md_files = list(docs_path.glob("*.md"))
    if not md_files:
        logger.warning("rag.ingest.no_md_files path=%s", docs_dir)
        return []
    return md_files


def _process_all_files(md_files: list[Path], splitter) -> tuple[list, list, list]:
    all_docs, all_ids, all_metadatas = [], [], []
    for md_file in md_files:
        docs, ids, metas = _process_md_file(md_file, splitter, len(all_docs))
        all_docs.extend(docs)
        all_ids.extend(ids)
        all_metadatas.extend(metas)
    return all_docs, all_ids, all_metadatas


def ingest_docs(
    docs_dir: str = "docs/",
    chroma_path: str = "chroma_db/",
    embedding_model: str = "paraphrase-multilingual-mpnet-base-v2",
    collection_name: str = "incident_docs",
    batch_size: int = 50,
) -> int:
    """
    Lire, chunker et embedder tous les .md de docs_dir dans Chroma.
    Retourne le nombre de chunks indexés.
    La collection est recréée à chaque appel pour refléter les mises à jour des docs.
    """
    md_files = _collect_md_files(docs_dir)
    if not md_files:
        return 0

    # Imports tardifs : chromadb et sentence-transformers sont lourds,
    # on ne les charge que quand l'ingestion est réellement demandée.
    from langchain_text_splitters import MarkdownHeaderTextSplitter
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    logger.info("rag.ingest.start files=%d chroma=%s", len(md_files), chroma_path)
    embedding_fn = SentenceTransformerEmbeddingFunction(model_name=embedding_model)
    collection = _init_collection(chroma_path, embedding_fn, collection_name)
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("##", "section"), ("###", "subsection")])

    all_docs, all_ids, all_metadatas = _process_all_files(md_files, splitter)
    if all_docs:
        _batch_insert(collection, all_docs, all_ids, all_metadatas, batch_size)
    logger.info("rag.ingest.done chunks=%d files=%d", len(all_docs), len(md_files))
    return len(all_docs)
