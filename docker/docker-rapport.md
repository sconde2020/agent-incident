# Rapport — Containerisation Docker

**Date :** 2026-05-07  
**Image :** `agent-incident:v1`  
**Base :** `python:3.11-slim`  
**Port exposé :** `8000`  
**Taille de l'image :** 4.57 GB (inclut PyTorch CPU + sentence-transformers + modèle d'embedding pré-téléchargé)

---

## Résultats des tests

| Étape | Commande / Action | Résultat | OK ? |
|-------|-------------------|----------|------|
| `docker build` | `docker build -t agent-incident:v1 .` | Image construite sans erreur | ✅ |
| `docker run` démarre | `docker run -d -p 8000:8000 -e OPENAI_API_KEY=... -e API_KEY=testkey --name mon-agent agent-incident:v1` | Conteneur `Up` + healthcheck `healthy` | ✅ |
| `/health` répond 200 | `curl http://localhost:8000/health` | `{"status":"ok","model":"gpt-4o-mini","version":"1.0.0"}` | ✅ |
| `/qualify` retourne une réponse | `POST /qualify {"id":"INC0001042"}` avec `Authorization: Bearer testkey` | `P1 / Application / Performance — team-payments — confidence 0.85` | ✅ |

---

## Détail de chaque étape

### 1. `docker build`

```
docker build -t agent-incident:v1 .
```

Couches principales (dans l'ordre, bénéficiant du cache) :

| Couche | Contenu |
|--------|---------|
| 1 | `python:3.11-slim` + `curl` |
| 2 | `torch` CPU-only (index PyTorch whl/cpu) |
| 3 | `requirements.txt` (openai, fastapi, chromadb, sentence-transformers…) |
| 4 | Pré-téléchargement du modèle `paraphrase-multilingual-mpnet-base-v2` |
| 5 | Code applicatif + entrypoint |

Résultat : **succès** — aucune erreur de build.

---

### 2. `docker run` démarre

```bash
docker run -d -p 8000:8000 \
  -e OPENAI_API_KEY=<clé> \
  -e API_KEY=testkey \
  --name mon-agent \
  agent-incident:v1
```

Au premier démarrage, l'entrypoint (`docker-entrypoint.sh`) détecte que `/data/incidents.db` n'existe pas et exécute automatiquement `python main.py init` :
- Création du schéma SQLite + import des 42 incidents mock
- Indexation de `docs/` dans ChromaDB (collection `incident_docs`)

Après init (~2 min au premier démarrage, le modèle étant déjà dans l'image), le serveur FastAPI démarre :

```
api.startup model=gpt-4o-mini host=0.0.0.0 port=8000
Uvicorn running on http://0.0.0.0:8000
```

Statut Docker : `Up X minutes (healthy)` — HEALTHCHECK HTTP sur `/health` validé.

---

### 3. `/health` répond 200

```bash
curl http://localhost:8000/health
```

Réponse :
```json
{"status": "ok", "model": "gpt-4o-mini", "version": "1.0.0"}
```

Code HTTP : **200 OK**

---

### 4. `/qualify` retourne une réponse (INC0001042)

```bash
curl -X POST http://localhost:8000/qualify \
  -H "Authorization: Bearer testkey" \
  -H "Content-Type: application/json" \
  -d '{"id": "INC0001042"}'
```

Réponse (extrait) :
```json
{
  "id": "INC0001042",
  "title": "Application de paiement inaccessible",
  "service": "payments-api",
  "priority": "P1",
  "category": "Application",
  "subcategory": "Performance",
  "assigned_to": "team-payments",
  "confidence_score": 0.85,
  "runbooks_suggested": ["postmortem_paiement_2024_03.md"],
  "is_duplicate": false,
  "is_major_incident": true,
  "monitoring_alerts": ["CRITICAL HTTP 5xx rate > 50%"],
  "enriched_context": {
    "service_tier": 1,
    "business_criticality": "critical",
    "active_alerts": 1,
    "has_critical_alerts": true
  }
}
```

Code HTTP : **200 OK**

---

## Configuration Docker

### Variables d'environnement (définies dans le Dockerfile)

| Variable | Valeur dans le conteneur |
|----------|--------------------------|
| `API_HOST` | `0.0.0.0` |
| `API_PORT` | `8000` |
| `DB_PATH` | `/data/incidents.db` |
| `CHROMA_PATH` | `/data/chroma_db/` |
| `DATA_PATH` | `/app/data/` |
| `DOCS_PATH` | `/app/docs/` |
| `LOG_LEVEL` | `INFO` |

### Variables à fournir au `docker run`

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Clé API OpenAI (requise) |
| `API_KEY` | Clé Bearer pour les endpoints protégés |

### Persistance des données

Monter un volume sur `/data` pour conserver la DB SQLite et ChromaDB entre les redémarrages :

```bash
docker run -d -p 8000:8000 \
  -e OPENAI_API_KEY=<clé> \
  -e API_KEY=<clé> \
  -v incident-data:/data \
  --name mon-agent \
  agent-incident:v1
```

---

## Notes de conception

**Torch CPU-only** — `torch` est installé depuis `https://download.pytorch.org/whl/cpu` avant `requirements.txt` pour éviter que `sentence-transformers` ne tire la variante CUDA (~2 Go de plus). L'image finale fait 4.57 GB (dont ~1.5 GB de modèle d'embedding).

**Modèle pré-téléchargé** — `SentenceTransformer('paraphrase-multilingual-mpnet-base-v2')` est téléchargé pendant le `docker build` et mis en cache dans l'image. Le conteneur n'a donc pas besoin d'accès internet au démarrage.

**Entrypoint idempotent** — `docker-entrypoint.sh` vérifie l'existence de `$DB_PATH` avant d'appeler `init`. Les redémarrages du conteneur ne réinitialisent pas la base.

**HEALTHCHECK** — curl sur `/health` toutes les 30 s, délai de grâce de 120 s pour couvrir le temps d'init au premier démarrage.
