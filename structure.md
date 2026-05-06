# Structure du projet – Agent de qualification des incidents SWIFT

## Arborescence

```
qualification-incident/
│
├── main.py                        # Point d'entrée – CLI et lancement serveur
├── api.py                         # Interface HTTP FastAPI (mode serveur)
├── agent.py                       # Orchestrateur principal de l'agent
├── llm.py                         # Client LLM (Claude via Anthropic SDK)
├── config.py                      # Chargement et validation de la configuration
├── .env                           # Variables d'environnement (non versionné)
│
├── tools/                         # Outils invocables par l'agent (LLM tool use)
│   ├── __init__.py
│   ├── classify.py                # Outil de classification (priorité, catégorie)
│   ├── route.py                   # Outil de routage vers les équipes
│   ├── search_incidents.py        # Outil de recherche dans l'historique ITSM
│   ├── search_monitoring.py       # Outil de récupération alertes monitoring
│   ├── search_cmdb.py             # Outil d'interrogation CMDB (service, dépendances)
│   ├── detect_duplicate.py        # Outil de détection de doublons
│   ├── detect_major_incident.py   # Outil de détection d'incident majeur
│   └── update_incident.py         # Outil de mise à jour du ticket dans la DB
│
├── rag/                           # Couche RAG – ingestion et recherche documentaire
│   ├── __init__.py
│   ├── ingest.py                  # Ingestion des fichiers .md dans le vector store
│   ├── retriever.py               # Recherche sémantique dans Chroma
│   └── prompts.py                 # Templates de prompts système et utilisateur
│
├── db/                            # Couche d'accès aux données (SQLite en local)
│   ├── __init__.py
│   ├── schema.sql                 # Schéma SQLite (incidents, alertes, services, équipes)
│   ├── init_db.py                 # Script d'initialisation et import des mock data
│   ├── incidents.py               # CRUD incidents et historique
│   ├── monitoring.py              # Lecture alertes et métriques
│   ├── cmdb.py                    # Lecture services, bases de données, équipes
│   └── models.py                  # Modèles Pydantic (IncidentIn, IncidentOut, Alert…)
│
├── security/                      # Sécurité et contrôle d'accès
│   ├── __init__.py
│   ├── auth.py                    # Authentification API (Bearer token / API key)
│   ├── audit.py                   # Journal d'audit des actions de l'agent
│   ├── input_validator.py         # Validation des entrées : formats, injection prompt, données sensibles
│   └── output_validator.py        # Validation des sorties LLM : cohérence, hallucinations, fuites
│
├── data/                          # Données mock (chargées par init_db.py)
│   ├── mock_incidents.json
│   ├── mock_cmdb.json
│   └── mock_monitoring.json
│
├── docs/                          # Documentation indexée dans le vector store
│   ├── runbook_swift_fin_indisponible.md
│   ├── runbook_sanctions_screening.md
│   ├── runbook_nostro_reconciliation.md
│   ├── runbook_api_5xx.md
│   ├── runbook_api_latency.md
│   ├── runbook_db_connection_pool.md
│   ├── postmortem_swift_cut_off_2024_02.md
│   ├── postmortem_paiement_2024_03.md
│   └── faq_paiements_swift.md
│
├── chroma_db/                     # Vector store Chroma (généré par rag/ingest.py)
│   └── ...                        # Ne pas versionner
│
├── tests.md                       # Scénarios de tests fonctionnels
├── requirements.txt
└── README.md
```

---

## Description des modules

### `main.py` – Point d'entrée

Point d'entrée **CLI uniquement** – ne lance pas le serveur HTTP.

```bash
# Qualifier un incident par son identifiant
python main.py qualify --id INC0002001

# Qualifier un incident depuis un JSON inline
python main.py qualify --json '{"title": "...", "service": "swift-gateway"}'

# Initialiser la base de données SQLite et indexer la documentation
python main.py init
```

#### Responsabilités

- Parser les arguments CLI (Typer)
- Appeler `db.init_db` si `init`
- Appeler `rag.ingest` pour charger les docs dans Chroma
- Instancier `Agent` et lancer la qualification
- Afficher le résultat enrichi en console (JSON formaté)

> Le serveur HTTP est lancé directement via `uvicorn` – voir `api.py`.

---

### `api.py` – Interface HTTP FastAPI

Lancé directement avec **uvicorn**, indépendamment de `main.py` :

```bash
# Développement (rechargement auto)
uvicorn api:app --reload --host 0.0.0.0 --port 8080

# Production
uvicorn api:app --host 0.0.0.0 --port 8080 --workers 4
```

#### Endpoints

```http
POST /qualify          # Qualifier un incident (body: IncidentIn)
GET  /incidents/{id}   # Récupérer un incident qualifié
GET  /health           # Health check
GET  /metrics          # Métriques de l'agent (latence, nb qualifications)
```

#### Ce que fait api.py

- Exposer l'agent via HTTP pour intégration ITSM (ServiceNow webhook)
- Valider les payloads entrants avec `security/input_validator.py`
- Valider les sorties LLM avec `security/output_validator.py`
- Appliquer l'authentification (`security/auth.py`)
- Journaliser chaque appel dans le journal d'audit
- Retourner le ticket enrichi (priorité, catégorie, équipe, suggestions)

#### Exemple de réponse

```json
{
  "id": "INC0002001",
  "priority": "P1",
  "category": "Infrastructure",
  "subcategory": "Connectivité",
  "assigned_to": "team-swift",
  "confidence_score": 0.92,
  "runbooks_suggested": ["runbook_swift_fin_indisponible.md"],
  "similar_incidents": ["INC0002031"],
  "monitoring_alerts": ["alert-005"],
  "is_duplicate": false,
  "is_major_incident": false,
  "resolution_hint": "Vérifier le certificat PKI et les sessions FIN actives...",
  "enriched_context": { "service_tier": 1, "business_criticality": "critical" }
}
```

---

### `agent.py` – Orchestrateur de l'agent

C'est le cœur du système. Il orchestre les appels LLM, les outils et le RAG pour produire la qualification complète d'un incident.

**Flux d'exécution**

```
Incident entrant (CLI / API)
      │
      ▼
0. Validation des entrées            → security/input_validator.py
   • format INC, longueurs, types
   • injection de prompt (titre/desc)
   • données sensibles (IBAN, creds)
   • formats SWIFT (BIC, UETR)
   • service et équipe dans la CMDB
      │ ValidationError → rejet immédiat (HTTP 422 / log)
      ▼
1. Récupération contexte CMDB        → tools/search_cmdb.py
2. Récupération alertes monitoring   → tools/search_monitoring.py
3. Détection doublon                 → tools/detect_duplicate.py
4. Détection incident majeur         → tools/detect_major_incident.py
      │
      ▼ (si pas doublon)
5. Recherche RAG (runbooks, FAQ,     → rag/retriever.py
   post-mortems, historique)
6. Recherche incidents similaires    → tools/search_incidents.py
      │
      ▼
7. Appel LLM avec contexte enrichi  → llm.py
   (classification + routing
    + suggestion résolution)
      │
      ▼
7b. Validation des sorties LLM       → security/output_validator.py
    • priorité / catégorie / équipe dans les listes autorisées
    • runbooks référencés existent
    • IDs incidents cohérents (INC + 7 chiffres)
    • pas de données sensibles dans resolution_hint
    • détection d'hallucinations (noms inventés…)
    • cohérence is_duplicate / duplicate_of
    • avertissement si confidence_score < 0.5
      │ ValidationError → fallback : qualification manuelle requise
      ▼
8. Mise à jour ticket SQLite         → tools/update_incident.py
9. Journalisation audit              → security/audit.py
```

**Interface principale**
```python
class Agent:
    def __init__(self, config: Config, db, rag, llm): ...

    async def qualify(self, incident: IncidentIn) -> IncidentOut:
        """Qualifier un incident : priorité, catégorie, équipe, suggestions."""
        ...

    async def enrich_context(self, incident: IncidentIn) -> dict:
        """Agréger CMDB, monitoring, incidents similaires."""
        ...
```

---

### `llm.py` – Client LLM (Claude)

Encapsule tous les appels à l'API Claude (Anthropic SDK). Gère le prompt caching, les retries et le tool use.

```python
class LLMClient:
    def __init__(self, config: Config): ...

    async def classify(self, incident: dict, context: dict) -> ClassificationResult:
        """Appel LLM pour classification et routing."""
        ...

    async def suggest_resolution(self, incident: dict, rag_docs: list[str]) -> str:
        """Appel LLM pour suggestion de résolution basée sur les docs RAG."""
        ...
```

**Modèle utilisé** : `claude-sonnet-4-6` (défini dans `.env`)

**Prompt caching** : Le prompt système (contexte CMDB, règles de classification, matrice de priorité) est mis en cache avec `cache_control: {"type": "ephemeral"}` pour réduire les coûts et la latence.

**Structure du prompt système**
```
[RÔLE] Tu es un agent expert en qualification d'incidents bancaires SWIFT.
[RÈGLES] Matrice de priorité P1-P4, catégories métier, équipes de routage.
[CMDB] Services critiques, dépendances, équipes responsables.      ← CACHÉE
[DOCS RAG] Runbooks et historique pertinents.                       ← VARIABLE
[INCIDENT] Titre, description, service, alertes monitoring.         ← VARIABLE
```

**Tool use** : L'agent utilise les outils Claude (function calling) pour rechercher dans la DB et mettre à jour le ticket de manière structurée.

---

### `tools/` – Outils de l'agent

Chaque outil est une fonction exposée au LLM via le mécanisme de tool use Claude.

| Fichier | Outil Claude | Description |
| --- | --- | --- |
| `classify.py` | `classify_incident` | Assigne priorité, catégorie, sous-catégorie |
| `route.py` | `route_to_team` | Détermine l'équipe assignée selon service et catégorie |
| `search_incidents.py` | `search_similar_incidents` | Recherche dans l'historique ITSM (SQLite full-text + embeddings) |
| `search_monitoring.py` | `get_monitoring_alerts` | Récupère les alertes actives pour un service donné |
| `search_cmdb.py` | `get_service_info` | Retourne les infos CMDB d'un service (tier, dépendances, équipe) |
| `detect_duplicate.py` | `check_duplicate` | Détecte si un incident similaire est déjà ouvert (< 2h, même service) |
| `detect_major_incident.py` | `check_major_incident` | Détecte une corrélation avec des incidents ouverts (incident majeur) |
| `update_incident.py` | `update_incident` | Met à jour le ticket dans SQLite avec la qualification |

**Exemple de définition d'outil**
```python
# tools/search_cmdb.py
TOOL_DEFINITION = {
    "name": "get_service_info",
    "description": "Retourne les informations CMDB d'un service : criticité, tier, dépendances, équipe responsable.",
    "input_schema": {
        "type": "object",
        "properties": {
            "service_name": {"type": "string", "description": "Nom du service (ex: swift-gateway)"}
        },
        "required": ["service_name"]
    }
}

def execute(service_name: str, db) -> dict:
    return db.cmdb.get_service(service_name)
```

---

### `rag/` – Retrieval Augmented Generation

#### `rag/ingest.py`

Indexe tous les fichiers `.md` du dossier `docs/` dans le vector store Chroma.

```python
def ingest_docs(docs_dir: str = "docs/", chroma_path: str = "chroma_db/"):
    """Lire, chunker et embedder tous les .md dans Chroma."""
    ...
```

- **Chunking** : par section Markdown (`## ...`), max 500 tokens par chunk
- **Embeddings** : `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (multilingue FR/EN)
- **Métadonnées** : `source_file`, `section_title`, `doc_type` (runbook / faq / postmortem)

#### `rag/retriever.py`

Recherche sémantique dans Chroma pour trouver les sections de documentation les plus pertinentes.

```python
def retrieve(query: str, k: int = 4, filter: dict = None) -> list[Document]:
    """Retourner les k chunks les plus proches du query."""
    ...
```

#### `rag/prompts.py`

Templates de prompts utilisés par l'agent.

```python
SYSTEM_PROMPT = """..."""          # Prompt système (avec cache)
CLASSIFY_PROMPT = """..."""        # Template de qualification
SUGGEST_PROMPT = """..."""         # Template de suggestion résolution
```

---

### `db/` – Couche d'accès aux données

#### `db/schema.sql`

```sql
CREATE TABLE incidents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'open',
    priority TEXT,
    category TEXT,
    subcategory TEXT,
    service TEXT,
    reported_by TEXT,
    assigned_to TEXT,
    created_at TEXT,
    updated_at TEXT,
    resolved_at TEXT,
    closed_at TEXT,
    resolution TEXT,
    sla_breach_at TEXT,
    confidence_score REAL,
    is_duplicate INTEGER DEFAULT 0,
    duplicate_of TEXT,
    is_major_incident INTEGER DEFAULT 0
);

CREATE TABLE incident_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT REFERENCES incidents(id),
    at TEXT,
    action TEXT,
    by TEXT
);

CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    service TEXT,
    severity TEXT,
    name TEXT,
    message TEXT,
    triggered_at TEXT,
    status TEXT,
    runbook_url TEXT,
    labels TEXT   -- JSON serialisé
);

CREATE TABLE metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT,
    timestamp TEXT,
    cpu_percent REAL,
    memory_percent REAL,
    error_rate_percent REAL,
    p50_latency_ms INTEGER,
    p99_latency_ms INTEGER,
    requests_per_second REAL,
    custom_metrics TEXT  -- JSON serialisé
);

CREATE TABLE services (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE,
    display_name TEXT,
    description TEXT,
    type TEXT,
    language TEXT,
    team TEXT,
    owner TEXT,
    business_criticality TEXT,
    sla_target_availability REAL,
    tier INTEGER,
    dependencies TEXT,   -- JSON array
    dependents TEXT      -- JSON array
);

CREATE TABLE teams (
    id TEXT PRIMARY KEY,
    name TEXT,
    slack_channel TEXT,
    oncall_email TEXT,
    services TEXT        -- JSON array
);
```

#### `db/init_db.py`

```python
def init_db(db_path: str = "incidents.db"):
    """Créer le schéma SQLite et importer les données mock."""
    # 1. Créer les tables (schema.sql)
    # 2. Charger data/mock_incidents.json → table incidents + incident_history
    # 3. Charger data/mock_monitoring.json → tables alerts + metrics
    # 4. Charger data/mock_cmdb.json → tables services + teams
```

---

### `security/` – Sécurité

#### `security/auth.py`

```python
def verify_api_key(api_key: str) -> bool:
    """Vérifier la clé API en-tête Authorization: Bearer <key>."""
    ...

# Middleware FastAPI
async def require_auth(request: Request):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not verify_api_key(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
```

#### `security/audit.py`

Journalise toutes les actions de l'agent dans une table `audit_log` (SQLite).

```python
def log_qualification(incident_id: str, result: dict, duration_ms: int):
    """Enregistrer la qualification : résultat, durée, modèle LLM utilisé."""
    ...
```

---

#### `security/input_validator.py`

Valide et assainit chaque incident avant qu'il entre dans le pipeline de l'agent.

##### Ce qui est contrôlé

| Contrôle | Détail |
| --- | --- |
| **Format INC** | `INC` + 7 chiffres obligatoires |
| **Longueurs** | `title` 5–200 car., `description` 10–5 000 car. |
| **Caractères autorisés** | `service` : alphanum + tirets/underscores uniquement |
| **Valeurs énumérées** | `status`, `priority`, `category`, `subcategory` dans les listes autorisées |
| **Email / équipe** | `reported_by`, `assigned_to` : email valide ou `team-xxx` connu |
| **Injection de prompt** | Détection de patterns (`ignore previous instructions`, `[INST]`, `<\|system\|>`, etc.) dans `title` et `description` |
| **Données sensibles** | Détection d'IBAN, numéros de carte, `password=`, `api_key=`, token Bearer dans `description` |
| **Formats SWIFT** | Fonctions utilitaires : `validate_bic()`, `validate_uetr()` |
| **Cohérence** | `subcategory` requiert `category` |

```python
class IncidentIn(BaseModel):
    id:          Optional[str]   # validé : INC + 7 chiffres
    title:       str             # nettoyé HTML, anti-injection
    description: str             # nettoyé + scan données sensibles
    service:     str             # normalisé lowercase, warn si inconnu CMDB
    status:      Optional[str]   # dans VALID_STATUSES
    priority:    Optional[str]   # dans {P1, P2, P3, P4}
    category:    Optional[str]   # dans VALID_CATEGORIES
    subcategory: Optional[str]   # dans VALID_SUBCATEGORIES
    reported_by: Optional[str]   # email ou team-xxx
    assigned_to: Optional[str]   # email ou team-xxx

def validate_bic(bic: str) -> bool:
    """Format BIC SWIFT : 8 ou 11 caractères [A-Z0-9]."""
    ...

def validate_uetr(uetr: str) -> bool:
    """Format UETR gpi : UUID v4."""
    ...

def validate_incident_batch(incidents: list[dict]) -> tuple[list[IncidentIn], list[dict]]:
    """Valider un lot – retourne (valides, erreurs) pour traitement partiel."""
    ...
```

##### Comportement en cas d'erreur

- `ValidationError` Pydantic → HTTP 422 dans `api.py`, log WARNING dans `audit.py`
- Les données sensibles déclenchent un HTTP 400 avec message générique (sans révéler le contenu détecté)
- L'injection de prompt déclenche un HTTP 400 et un log CRITICAL

---

#### `security/output_validator.py`

Valide la réponse brute du LLM avant écriture en base et restitution à l'appelant.
Garantit qu'aucune hallucination ou fuite ne se propage en aval.

##### Contrôles appliqués sur les sorties LLM

| Contrôle | Détail |
| --- | --- |
| **Valeurs énumérées** | `priority` ∈ {P1–P4}, `category`, `subcategory`, `assigned_to` dans les listes autorisées |
| **Runbooks** | Seuls les fichiers présents dans `docs/` sont conservés ; path traversal (`../`) rejeté |
| **Références incidents** | `similar_incidents`, `duplicate_of` : format INC + 7 chiffres |
| **Score de confiance** | `confidence_score` ∈ [0.0, 1.0] ; warning si < 0.5 |
| **Fuites de données** | Scan `resolution_hint` : clés API, IBAN, tokens Bearer |
| **Hallucinations** | Détection de patterns suspects (`example.com`, `I am an AI`, noms d'outils externes…) |
| **Cohérence** | `is_duplicate=True` ↔ `duplicate_of` renseigné ; `is_major_incident=True` ↔ ≥ 2 `related_incidents` |

```python
class QualificationResult(BaseModel):
    priority:           str            # validé contre VALID_PRIORITIES
    category:           str            # validé contre VALID_CATEGORIES
    subcategory:        str            # validé contre VALID_SUBCATEGORIES
    assigned_to:        str            # validé contre KNOWN_TEAMS
    confidence_score:   float          # [0.0, 1.0]
    resolution_hint:    Optional[str]  # scanné fuites + hallucinations
    runbooks_suggested: list[str]      # filtrés sur KNOWN_RUNBOOKS, pas de path traversal
    similar_incidents:  list[str]      # filtrés sur regex INC\d{7}
    monitoring_alerts:  list[str]
    is_duplicate:       bool
    duplicate_of:       Optional[str]  # INC\d{7} si is_duplicate=True
    is_major_incident:  bool
    related_incidents:  list[str]      # ≥ 2 si is_major_incident=True

def validate_llm_output(raw: dict) -> QualificationResult:
    """Valider – lève ValidationError si invalide."""
    ...

def safe_validate_llm_output(raw: dict) -> tuple[Optional[QualificationResult], Optional[str]]:
    """Variante tolérante – retourne (result, None) ou (None, message_erreur)."""
    ...
```

##### Comportement en cas d'erreur (sorties LLM)

- `ValidationError` → l'agent logue l'erreur, marque le ticket `qualification_failed=True` et déclenche une alerte pour révision humaine
- Les fuites de données dans `resolution_hint` → le champ est tronqué et remplacé par un message générique avant renvoi

---

### `config.py` – Configuration

```python
from pydantic_settings import BaseSettings

class Config(BaseSettings):
    # LLM
    anthropic_api_key: str
    llm_model: str = "claude-sonnet-4-6"
    llm_max_tokens: int = 1024

    # Base de données
    db_path: str = "incidents.db"

    # Vector store
    chroma_path: str = "chroma_db/"
    embedding_model: str = "paraphrase-multilingual-mpnet-base-v2"

    # RAG
    rag_top_k: int = 4
    docs_path: str = "docs/"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_key: str  # Clé d'accès à l'API REST

    # Agent
    duplicate_window_hours: int = 2     # Fenêtre de détection doublon
    major_incident_threshold: int = 3   # Nb incidents liés pour déclarer incident majeur

    class Config:
        env_file = ".env"
```

---

### `.env` – Variables d'environnement

```dotenv
# LLM – Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...
LLM_MODEL=claude-sonnet-4-6
LLM_MAX_TOKENS=1024

# Base de données SQLite (local dev)
DB_PATH=incidents.db

# Vector store Chroma
CHROMA_PATH=chroma_db/
EMBEDDING_MODEL=paraphrase-multilingual-mpnet-base-v2

# RAG
RAG_TOP_K=4
DOCS_PATH=docs/

# API REST
API_HOST=0.0.0.0
API_PORT=8080
API_KEY=your-secret-api-key-here

# Agent
DUPLICATE_WINDOW_HOURS=2
MAJOR_INCIDENT_THRESHOLD=3

# Logs
LOG_LEVEL=INFO
```

> **Ne jamais versionner `.env`**. Ajouter `.env` au `.gitignore`.

---

## Flux de données complet

```
Incident créé (CLI / API POST)
         │
         ▼
    [config.py]  ──── lit .env
         │
         ▼
    [agent.py]  ──── orchestrateur
    ┌────┴─────────────────────────────────────────┐
    │                                              │
    ▼                                              ▼
[db/cmdb.py]                            [db/monitoring.py]
Infos service CMDB                      Alertes actives
(tier, criticité, dépendances)          corrélées au service
    │                                              │
    └──────────────────┬───────────────────────────┘
                       │ Contexte enrichi
                       ▼
             [tools/detect_duplicate.py]
             [tools/detect_major_incident.py]
                       │
                       ▼ (si pas doublon)
             [db/incidents.py]           [rag/retriever.py]
             Incidents similaires   +    Runbooks / FAQ / post-mortems
             (historique ITSM)           (recherche sémantique Chroma)
                       │
                       └──────────────┬──────────────┘
                                      │ Contexte RAG
                                      ▼
                                  [llm.py]
                            Appel Claude API
                            (tool use + RAG)
                              classification
                              routing
                              suggestions
                                      │
                                      ▼
                          [tools/update_incident.py]
                          Mise à jour SQLite
                                      │
                                      ▼
                           [security/audit.py]
                           Journal d'audit
                                      │
                                      ▼
                              IncidentOut (JSON)
                              retourné à l'appelant
```

---

## Installation et démarrage

```bash
# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Configurer l'environnement
cp .env.example .env
# Éditer .env : renseigner ANTHROPIC_API_KEY et API_KEY

# 3. Initialiser la base de données et indexer la documentation
python main.py init

# 4a. Qualifier un incident en CLI
python main.py qualify --id INC0002001

# 4b. Lancer le serveur API
python main.py serve
```

---

## `requirements.txt`

```
anthropic>=0.40.0
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
pydantic>=2.10.0
pydantic-settings>=2.6.0
chromadb>=0.5.0
sentence-transformers>=3.3.0
langchain>=0.3.0
langchain-community>=0.3.0
typer>=0.13.0
python-dotenv>=1.0.0
```

---

## Correspondance local ↔ production

| Composant | Local (SQLite + Chroma) | Production |
| --- | --- | --- |
| ITSM | `db/incidents.py` → SQLite | API ServiceNow / Jira SM |
| Monitoring | `db/monitoring.py` → SQLite | API Datadog / Prometheus |
| CMDB | `db/cmdb.py` → SQLite | API ServiceNow CMDB |
| Documentation | `rag/` → Chroma local | Confluence API + pgvector |
| Bus événements | Appel direct Python | Kafka (`incidents.created`) |
| Output | Mise à jour SQLite | Kafka (`incidents.qualified`) + ITSM API |