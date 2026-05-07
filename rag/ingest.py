import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def ingest_docs(docs_dir: str = "docs/", chroma_path: str = "chroma_db/") -> int:
    """
    Lire, chunker et embedder tous les .md de docs_dir dans Chroma.
    Retourne le nombre de chunks indexés.
    La collection est recréée à chaque appel pour refléter les mises à jour des docs.
    """
    # Imports tardifs : chromadb et sentence-transformers sont lourds,
    # on ne les charge que quand l'ingestion est réellement demandée.
    from langchain_text_splitters import MarkdownHeaderTextSplitter
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    docs_path = Path(docs_dir)
    if not docs_path.exists():
        logger.warning("rag.ingest.docs_dir_not_found path=%s", docs_dir)
        return 0

    md_files = list(docs_path.glob("*.md"))
    if not md_files:
        logger.warning("rag.ingest.no_md_files path=%s", docs_dir)
        return 0

    logger.info("rag.ingest.start files=%d chroma=%s", len(md_files), chroma_path)

    embedding_fn = SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-mpnet-base-v2"
    )
    client = chromadb.PersistentClient(path=chroma_path)

    # Supprimer et recréer la collection pour garantir la fraîcheur des données
    try:
        client.delete_collection("incident_docs")
    except Exception:
        pass
    collection = client.create_collection(
        name="incident_docs",
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("##", "section"), ("###", "subsection")]
    )

    all_docs, all_ids, all_metadatas = [], [], []
    counter = 0

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        chunks = splitter.split_text(content)

        # Déduire le type de document depuis le nom du fichier
        stem = md_file.stem
        if stem.startswith("runbook"):
            doc_type = "runbook"
        elif stem.startswith("postmortem"):
            doc_type = "postmortem"
        elif stem.startswith("faq"):
            doc_type = "faq"
        else:
            doc_type = "doc"

        for chunk in chunks:
            headers = " | ".join(chunk.metadata.values()) if chunk.metadata else ""
            # Inclure les titres de sections dans le texte pour améliorer le recall sémantique
            full_text = f"[{headers}]\n{chunk.page_content}" if headers else chunk.page_content

            all_docs.append(full_text)
            all_ids.append(f"{stem}_{counter}")
            all_metadatas.append({
                "source_file": md_file.name,
                "section_title": headers,
                "doc_type": doc_type,
            })
            counter += 1

    if all_docs:
        # Insertion par batch pour éviter les timeouts sur de grandes collections
        batch_size = 50
        for i in range(0, len(all_docs), batch_size):
            collection.add(
                documents=all_docs[i:i + batch_size],
                ids=all_ids[i:i + batch_size],
                metadatas=all_metadatas[i:i + batch_size],
            )

    logger.info("rag.ingest.done chunks=%d files=%d", counter, len(md_files))
    return counter
