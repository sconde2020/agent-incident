import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RAGRetriever:
    def __init__(
        self,
        chroma_path: str,
        top_k: int = 4,
        embedding_model: str = "paraphrase-multilingual-mpnet-base-v2",
        collection_name: str = "incident_docs",
    ):
        self.chroma_path = chroma_path
        self.top_k = top_k
        self.embedding_model = embedding_model
        self.collection_name = collection_name
        self._collection = None  # chargement paresseux

    def _get_collection(self):
        """Initialiser la connexion Chroma à la première utilisation."""
        if self._collection is not None:
            return self._collection

        import chromadb
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

        embedding_fn = SentenceTransformerEmbeddingFunction(model_name=self.embedding_model)
        client = chromadb.PersistentClient(path=self.chroma_path)
        try:
            self._collection = client.get_collection(
                name=self.collection_name,
                embedding_function=embedding_fn,
            )
        except Exception as exc:
            logger.warning("rag.retriever.collection_not_found error=%s", exc)
            return None
        return self._collection

    def retrieve(
        self,
        query: str,
        k: Optional[int] = None,
        doc_type_filter: Optional[str] = None,
    ) -> list[dict]:
        """
        Retourner les k chunks les plus proches sémantiquement du query.
        doc_type_filter : 'runbook', 'postmortem', 'faq' ou None pour tout.
        """
        collection = self._get_collection()
        if collection is None:
            logger.warning("rag.retriever.no_collection – RAG désactivé")
            return []

        k = k or self.top_k
        where = {"doc_type": doc_type_filter} if doc_type_filter else None

        try:
            results = collection.query(
                query_texts=[query],
                n_results=k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.error("rag.retriever.query_failed error=%s", exc)
            return []

        # Chroma peut retourner plusieurs chunks du même fichier (sections ##/###).
        # On ne garde que le chunk le plus pertinent par source_file.
        seen: dict[str, dict] = {}
        for text, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            source = meta.get("source_file", "")
            score = round(1.0 - dist, 3)
            if source not in seen or score > seen[source]["relevance_score"]:
                seen[source] = {
                    "text": text,
                    "source_file": source,
                    "doc_type": meta.get("doc_type", ""),
                    "section": meta.get("section_title", ""),
                    "relevance_score": score,
                }

        docs = list(seen.values())
        logger.debug("rag.retriever.results returned=%d unique_files=%d", len(docs), len(seen))
        return docs
