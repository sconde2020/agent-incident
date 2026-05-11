# Agent de qualification des incidents SWIFT

Agent IA qui qualifie automatiquement les incidents bancaires SWIFT : priorité, catégorie, équipe responsable et suggestion de résolution. Basé sur GPT-4o (OpenAI), RAG sur la documentation interne et une base SQLite locale.

---

## Fonctionnement

```
Incident entrant (CLI / API)
        │
        ▼
   Validation des entrées (injection de prompt, données sensibles, formats SWIFT)
        │
        ▼
   CMDB  +  Monitoring  +  Détection doublon  +  Détection incident majeur
        │
        ▼ (si pas doublon)
   RAG (runbooks / post-mortems / FAQ)  +  Incidents similaires
        │
        ▼
   Appel GPT-4o → classification + routing + suggestion
        │
        ▼
   Validation sortie LLM (hallucinations, fuites, cohérence)
        │
        ▼
   Mise à jour SQLite  +  Journal d'audit  →  IncidentOut (JSON)
```

**Court-circuits :**
- Doublon détecté → qualification sans LLM, priorité héritée de l'incident original
- Sortie LLM invalide → fallback P3 / team-ops + flag `qualification_failed=True` pour révision humaine

---

## Stack technique

| Composant | Choix local (dev) |
|---|---|
| LLM | GPT-4o via OpenAI SDK |
| Base de données | SQLite |
| Vector store | ChromaDB |
| Embeddings | `paraphrase-multilingual-mpnet-base-v2` (FR/EN) |
| API | FastAPI + uvicorn |
| CLI | Typer |

---

## Installation

```bash
# 1. Cloner et créer un environnement virtuel
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux / macOS

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env : renseigner OPENAI_API_KEY et API_KEY
```

### Variables d'environnement (`.env`)

| Variable | Description | Défaut |
|---|---|---|
| `OPENAI_API_KEY` | Clé API OpenAI | *(requis)* |
| `LLM_MODEL` | Modèle OpenAI | `gpt-4o` |
| `LLM_MAX_TOKENS` | Tokens max par appel | `1024` |
| `LLM_TEMPERATURE` | Température (0 = déterministe) | `0.1` |
| `DB_PATH` | Chemin SQLite | `incidents.db` |
| `CHROMA_PATH` | Chemin ChromaDB | `chroma_db/` |
| `API_KEY` | Clé d'accès à l'API REST | *(requis)* |
| `DUPLICATE_WINDOW_HOURS` | Fenêtre détection doublons | `2` |
| `MAJOR_INCIDENT_THRESHOLD` | Nb services pour incident majeur | `3` |
| `LOG_LEVEL` | Niveau de log | `INFO` |

---

## Démarrage rapide

### 1. Initialiser la base de données et indexer la documentation

```bash
python main.py init
```

Crée le schéma SQLite, importe les données mock (`data/`) et indexe les runbooks / post-mortems / FAQ (`docs/`) dans ChromaDB.

### 2. Qualifier un incident en ligne de commande

```bash
# Depuis la base de données (incidents mock)
python main.py qualify --id INC0002001

# Depuis un JSON inline
python main.py qualify --json '{"title": "SWIFTNet Link indisponible", "description": "Aucun message FIN depuis 08h10", "service": "swift-gateway"}'
```

**Exemple de sortie :**
```json
{
  "id": "INC0002001",
  "priority": "P1",
  "category": "Infrastructure",
  "subcategory": "Connectivité",
  "assigned_to": "team-swift",
  "confidence_score": 0.94,
  "runbooks_suggested": ["runbook_swift_fin_indisponible.md"],
  "similar_incidents": ["INC0002031"],
  "monitoring_alerts": ["alert-005"],
  "is_duplicate": false,
  "is_major_incident": false,
  "resolution_hint": "Vérifier les sessions FIN actives et le certificat PKI...",
  "enriched_context": {
    "service_tier": 1,
    "business_criticality": "critical",
    "active_alerts": 1,
    "has_critical_alerts": true
  }
}
```

### 3. Lancer le serveur API

```bash
# Développement (rechargement auto)
python main.py serve --reload

# Production
uvicorn api:app --host 0.0.0.0 --port 8080 --workers 4
```

---

## API REST

Authentification : `Authorization: Bearer <API_KEY>`

| Méthode | Endpoint | Description |
|---|---|---|
| `POST` | `/qualify` | Qualifier un incident (body JSON) |
| `GET` | `/incidents/{id}` | Récupérer un incident qualifié |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Métriques (qualifications, latence) |

**Exemple avec curl :**
```bash
curl -X POST http://localhost:8080/qualify \
  -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "File FIN saturée – MT103 non traités",
    "description": "220 messages MT103 en attente depuis 90 minutes",
    "service": "fin-processor"
  }'
```

---

## Docker

Les fichiers Docker sont regroupés dans le dossier [`docker/`](docker/).

### Build

```bash
# Depuis la racine du projet
docker build -f docker/Dockerfile -t agent-incident .
```

### Lancer le conteneur

```bash
docker run -d \
  --name agent-incident \
  -e API_PORT=8080 \
  -p 8080:8080 \
  -v incident-data:/data \
  -e OPENAI_API_KEY=$OPENAI_API_KEY \
  -e API_KEY=$API_KEY \
  agent-incident
```

Le volume `/data` persiste la base SQLite et ChromaDB entre les redémarrages.  
Au premier démarrage, `docker/docker-entrypoint.sh` exécute `python main.py init` automatiquement si la DB est absente.

### Variables d'environnement Docker

Les variables listées dans [Variables d'environnement](#variables-denvironnement-env) peuvent toutes être passées via `-e` ou un fichier `--env-file .env`.

---

## Tests

### Prérequis

```bash
pip install pytest
```

Les tests unitaires n'ont pas besoin de clé API. Les tests d'intégration et de qualité appellent le LLM réel et requièrent `OPENAI_API_KEY` dans `.env`.

Les rapports sont générés automatiquement dans `tests/reports/` à la fin de chaque session pytest :

- `rapport_unitaires.md` — tests unitaires
- `rapport_integration.md` — tests d'intégration
- `rapport_qualite.md` — tests de qualité LLM-as-Judge

### Tests unitaires (sans LLM, sans réseau)

Répartis dans `tests/unit/` : outils, mémoire, validateurs d'entrée et de sortie.

```bash
# Tous les tests unitaires
python -m pytest tests/unit/ -v

# Par fichier
python -m pytest tests/unit/test_tools.py -v
python -m pytest tests/unit/test_memory.py -v
python -m pytest tests/unit/test_input_validator.py -v
python -m pytest tests/unit/test_output_validator.py -v
```

### Tests d'intégration (LLM réel + SQLite)

Répartis dans `tests/integration/` : pipeline, mémoire de session, sécurité. Les tests de doublon passent sans clé API.

```bash
# Tous les tests d'intégration
python -m pytest tests/integration/ -v -m integration

# Par fichier
python -m pytest tests/integration/test_pipeline.py -v -m integration
python -m pytest tests/integration/test_memory_mechanics.py -v -m integration
python -m pytest tests/integration/test_security.py -v -m integration
```

### Tests de qualité — LLM-as-Judge (LLM réel + RAG réel)

11 questions évaluées par un juge LLM (gpt-4o) sur 3 critères : Pertinence, Fidélité, Cohérence. Génère `tests/reports/rapport_qualite.md` à la fin.

```bash
# Initialiser la DB et le RAG si ce n'est pas encore fait
python main.py init

python -m pytest tests/quality/test_quality.py -v -s
```

Score cible : ≥ 3.5 / 5.0 globalement, ≥ 3.0 par question.

### Tests de performance (end-to-end)

Exécute 25 × `POST /create` + `POST /qualify` et met à jour la section métriques de `demo.md`.

```bash
python main.py init                       # initialise la DB et le RAG
python main.py serve --port 8080 &       # serveur en arrière-plan
python test_performance.py               # lance le benchmark
```

> Option : `python test_performance.py --url http://host:port` si le serveur tourne ailleurs.

### Tout lancer

```bash
python -m pytest tests/ -v
```

---

## Structure du projet

```
agent-incident/
├── main.py                  # CLI (init, qualify, serve)
├── api.py                   # API FastAPI
├── agent.py                 # Orchestrateur – pipeline de qualification
├── llm.py                   # Client LLM (Anthropic SDK)
├── config.py                # Configuration (pydantic-settings)
│
├── db/                      # Couche SQLite
│   ├── schema.sql
│   ├── init_db.py
│   ├── incidents.py
│   ├── monitoring.py
│   ├── cmdb.py
│   └── models.py
│
├── security/                # Sécurité
│   ├── auth.py              # Auth Bearer (comparaison constante)
│   ├── audit.py             # Journal d'audit
│   ├── input_validator.py   # Anti-injection, données sensibles, formats SWIFT
│   └── output_validator.py  # Validation sorties LLM, anti-hallucination
│
├── prompts.py               # Templates système et classification (SYSTEM_PROMPT, CLASSIFY_PROMPT)
│
├── rag/                     # Retrieval Augmented Generation
│   ├── ingest.py            # Indexation Markdown → ChromaDB
│   └── retriever.py         # Recherche sémantique
│
├── tools/                   # Outils de l'agent (function calling)
│   ├── search_cmdb.py
│   ├── search_monitoring.py
│   ├── search_incidents.py
│   ├── detect_duplicate.py
│   ├── detect_major_incident.py
│   ├── classify.py
│   ├── route.py
│   ├── create_incident.py
│   └── update_incident.py
│
├── memory/                  # Mémoire conversationnelle de session
│   └── store.py
│
├── tests/                   # Suite de tests
│   ├── conftest.py          # Enregistrement des markers pytest
│   ├── questions.json       # Questions pour les tests de qualité
│   ├── unit/                # Tests unitaires (sans LLM, sans réseau)
│   │   ├── test_tools.py        # 9 classes — outils function calling
│   │   ├── test_memory.py       # ConversationMemory
│   │   ├── test_input_validator.py   # Injection, SQL, données sensibles
│   │   └── test_output_validator.py  # Enums, filtrage, sanitisation, cohérence
│   ├── integration/         # Tests d'intégration (SQLite réel)
│   │   ├── conftest.py          # Fixtures, helpers DB, pytestmark
│   │   ├── test_pipeline.py     # Mécaniques pipeline (CMDB, monitoring, doublons)
│   │   ├── test_memory_mechanics.py  # Mémoire de session
│   │   └── test_security.py     # Barrière sécurité avant LLM
│   ├── quality/             # Tests qualité LLM-as-Judge
│   │   ├── judge.py             # Client juge gpt-4o, prompts, formatage
│   │   ├── conftest.py          # Fixtures (real_agent, score_collector), génération rapport
│   │   └── test_quality.py      # 11 questions évaluées par le juge
│   └── reports/             # Rapports générés automatiquement
│       ├── rapport_qualite.md
│       ├── rapport_unitaires.md
│       └── rapport_integration.md
│
├── docker/                  # Fichiers Docker
│   ├── Dockerfile
│   ├── docker-entrypoint.sh # Init DB au premier démarrage
│   └── docker-rapport.md
│
├── data/                    # Données mock (incidents, CMDB, monitoring)
│   ├── mock_incidents.json
│   ├── mock_cmdb.json
│   └── mock_monitoring.json
│
├── docs/                    # Runbooks, post-mortems, FAQ (indexés dans Chroma)
│   ├── runbook_swift_fin_indisponible.md
│   ├── runbook_api_5xx.md
│   ├── runbook_api_latency.md
│   ├── runbook_db_connection_pool.md
│   ├── runbook_nostro_reconciliation.md
│   ├── runbook_sanctions_screening.md
│   ├── postmortem_paiement_2024_03.md
│   ├── postmortem_swift_cut_off_2024_02.md
│   ├── faq_incidents_courants.md
│   └── faq_paiements_swift.md
│
├── .dockerignore
├── .env.example             # Template de configuration
└── requirements.txt
```

---

## Matrice de priorité

| Priorité | Critères |
|---|---|
| **P1** | Arrêt total d'un service critique, perte financière directe, > 500 paiements bloqués, breach conformité |
| **P2** | Dégradation sévère, > 100 paiements impactés, mode dégradé sanctions, écart nostro > 100K€ |
| **P3** | Impact limité (1 contrepartie, < 50 paiements), problème en attente externe |
| **P4** | Informatif, aucun impact opérationnel immédiat |

## Équipes de routage

| Équipe | Services |
|---|---|
| `team-swift` | swift-gateway, fin-processor, bic-validator, gpi-tracker, mt-parser |
| `team-infra` | swift-alliance, certificats PKI/SSL |
| `team-payments` | payment-hub, payment-router, payments-api |
| `team-compliance` | sanctions-screening, AML |
| `team-ops` | nostro-reconciliation, liquidity-manager, cut-off-manager |
| `team-correspondent` | correspondent-service, relations banques partenaires, RMA |

---

## Sécurité

- **Entrées** : détection d'injection de prompt, données sensibles (IBAN, cartes, tokens Bearer), validation formats BIC/UETR
- **Sorties LLM** : valeurs énumérées, path traversal sur runbooks, fuites de données dans `resolution_hint`, hallucinations
- **API** : authentification Bearer à durée constante (`hmac.compare_digest`)
- **Audit** : toutes les qualifications sont journalisées dans `audit_log` (SQLite)

---

## Données mock incluses

42 incidents SWIFT réels (`data/mock_incidents.json`), 18 services CMDB et 9 équipes (`data/mock_cmdb.json`), 15 alertes monitoring (`data/mock_monitoring.json`).

Services couverts : `swift-gateway`, `fin-processor`, `payment-hub`, `sanctions-screening`, `bic-validator`, `gpi-tracker`, `nostro-reconciliation`, `swift-alliance`, `payment-router`, `correspondent-service`, `cut-off-manager`, `liquidity-manager`, `mt-parser`.
