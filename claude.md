# CLAUDE.md – Agent de qualification des incidents SWIFT

## Présentation

Agent IA qui qualifie automatiquement les incidents bancaires SWIFT : priorité (P1–P4),
catégorie, équipe assignée, suggestions de runbooks. Exposé en CLI (`main.py`) et HTTP (`api.py`).

**Stack** : Python 3.12+, FastAPI, SQLite, ChromaDB, Anthropic SDK (Claude), Pydantic v2, Typer.

---

## Démarrage

```bash
pip install -r requirements.txt
cp .env.example .env          # renseigner API_KEY + ANTHROPIC_API_KEY (ou OPENAI_API_KEY)

python main.py init            # initialise SQLite + indexe docs/ dans Chroma
python main.py serve --port 8080 --reload   # serveur HTTP dev

# CLI direct
python main.py qualify --id INC0002001
```

---

## Architecture et responsabilités

```text
main.py        → CLI (Typer) — aucune logique métier
api.py         → HTTP (FastAPI) — validation + dispatch vers Agent
agent.py       → orchestrateur — lit les outils, appelle llm.py, écrit en DB
llm.py         → client LLM (Anthropic SDK) — tous les appels sont ici
config.py      → Config (pydantic-settings) — chargé depuis .env
tools/         → outils LLM (function calling) — un fichier = un outil
db/            → couche données SQLite — un fichier = un domaine
rag/           → ingestion + recherche sémantique (Chroma)
security/      → auth, audit, validation entrées/sorties LLM
memory/        → mémoire conversationnelle de session
```

### Structure des fichiers

```text
agent-incident/
├── main.py
├── api.py
├── agent.py
├── llm.py
├── config.py
│
├── db/
│   ├── schema.sql
│   ├── init_db.py
│   ├── incidents.py
│   ├── monitoring.py
│   ├── cmdb.py
│   └── models.py
│
├── security/
│   ├── auth.py
│   ├── audit.py
│   ├── input_validator.py
│   └── output_validator.py
│
├── rag/
│   ├── ingest.py
│   ├── retriever.py
│   └── prompts.py
│
├── tools/
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
├── memory/
│   └── store.py
│
├── tests/
│   ├── conftest.py
│   ├── test_unitaires.py
│   ├── test_integration.py
│   ├── test_qualite.py
│   └── questions.json
│
├── docker/
│   ├── Dockerfile
│   └── docker-entrypoint.sh
│
├── data/                    # mock: incidents, CMDB, monitoring
├── docs/                    # runbooks, post-mortems, FAQ (Chroma)
├── .env.example
└── requirements.txt
```

### Flux d'exécution d'une qualification

```text
POST /qualify  →  validate_incident_input()
               →  agent.qualify()
                    ├─ search_cmdb / search_monitoring
                    ├─ detect_duplicate / detect_major_incident
                    ├─ rag.retriever (runbooks, post-mortems)
                    ├─ llm.classify() — appel Claude avec tool use
                    ├─ validate_llm_output()
                    └─ update_incident (SQLite) + audit_log
               →  IncidentOut (JSON)
```

---

## Principes de développement

### SOLID appliqué à ce projet

**Single Responsibility** — chaque module a une seule raison de changer.

- `tools/classify.py` classifie, `tools/route.py` route : ne pas fusionner.
- `IncidentDB` gère les incidents, `CmdbDB` la CMDB : ne pas croiser les domaines.
- `api.py` dispatche, `agent.py` orchestre : ne pas mettre de logique métier dans les endpoints.

**Open/Closed** — ajouter un outil sans modifier l'existant.

- Créer `tools/mon_outil.py` avec `TOOL_DEFINITION` + classe `MonOutil(execute())`.
- L'ajouter dans `tools/__init__.py` et l'enregistrer dans `agent.py`.
- Ne jamais modifier un outil existant pour couvrir un nouveau cas d'usage.

**Liskov Substitution** — tous les outils sont interchangeables sur leur interface.

- Chaque outil expose `execute(**kwargs) -> dict` et un `TOOL_DEFINITION` dict.
- Un outil qui retourne `{"success": False, "error": "..."}` est préférable à une exception non contrôlée.

**Interface Segregation** — les DB classes sont séparées par domaine.

- `IncidentDB`, `MonitoringDB`, `CmdbDB` : chacune n'expose que ce dont son consommateur a besoin.
- Ne pas ajouter de méthodes monitoring dans `IncidentDB`.

**Dependency Inversion** — `Agent` dépend d'abstractions, pas de concret.

- Les outils, le client LLM et les DB sont injectés dans `Agent.__init__`.
- Ne pas instancier `IncidentDB` ou `LLMClient` à l'intérieur de `Agent.qualify()`.

### Autres règles

- **Pas de logique métier dans les endpoints** — `api.py` valide, dispatch et formate. Tout le reste va dans `agent.py` ou les tools.
- **Validation à la frontière uniquement** — `validate_incident_input()` en entrée, `validate_llm_output()` en sortie LLM. Ne pas re-valider à l'intérieur du pipeline.
- **Pas d'accès DB direct depuis les endpoints** — sauf les cas simples de lecture (`GET /incidents/{id}`, `POST /create`). Toute logique complexe passe par `Agent`.
- **Longueur des fonctions et méthodes** — 30 lignes max, 35 lignes en limite absolue. Au-delà, extraire une méthode privée. La sélection `llm.classify()` est un exemple de limite acceptable : une fonction qui dépasse 35 lignes cache plusieurs responsabilités.
- **Paramètres modifiables dans `config.py`** — toute valeur susceptible de changer selon l'environnement (seuils, timeouts, noms de modèle, chemins) doit être un champ de `Config` chargé depuis `.env`. Pas de constantes hardcodées dans les tools ou l'agent.
- **Commentaires** — uniquement quand le *pourquoi* n'est pas évident : contrainte cachée, invariant subtil, contournement d'un bug précis. Ne pas commenter ce que le code dit déjà. Un seul bloc de commentaire par méthode au maximum.
- **Chaque outil loggue ses appels** — `logger.info("tools.<nom> key=value")` en début d'`execute()`.
- **Pas de `print()`** — utiliser `logging` partout.

---

## Ajouter un tool

1. Créer `tools/mon_outil.py` avec `TOOL_DEFINITION` + une classe exposant `execute(**kwargs) -> dict`.
2. L'exporter dans `tools/__init__.py`.
3. L'enregistrer dans `agent.py` (liste `TOOLS` et dispatch `_handle_tool_call`).

**Template `tools/mon_outil.py` :**

```python
TOOL_DEFINITION = {
    "name": "mon_outil",
    "description": "...",
    "input_schema": {"type": "object", "properties": {...}, "required": [...]},
}

class MonOutil:
    def __init__(self, dep):          # injection de dépendance
        self.dep = dep

    def execute(self, **kwargs) -> dict:
        ...
        return {"success": True, ...}
```

---

## Sécurité — règles non négociables

- **Toujours passer par `validate_incident_input()`** avant tout traitement LLM.
- **Toujours passer par `validate_llm_output()`** avant d'écrire en DB ou de répondre.
- Les champs `title` et `description` sont scannés anti-injection de prompt.
- Les sorties LLM sont scannées pour fuites de données sensibles (IBAN, clés API, tokens).
- Ne jamais logger le contenu de `description` en entier (peut contenir des données sensibles).
- Ne jamais exposer le détail des erreurs internes dans les réponses HTTP (HTTP 500 générique).

---

## Modèles de données clés

```python
IncidentIn      # entrée validée — security/input_validator.py
IncidentOut     # sortie qualifiée — db/models.py
IncidentCreated # réponse brute POST /create — db/models.py
```

Format ID : `INC` + 7 chiffres (`INC0002001`). Validé par regex `^INC\d{7}$`.

---

## Endpoints HTTP

| Méthode | Route | Description |
| ------- | ----- | ----------- |
| `POST` | `/create` | Créer un incident brut (simulation) |
| `POST` | `/qualify` | Qualifier — accepte payload complet ou `{"id": "INCxxxxxxx"}` |
| `GET` | `/incidents/{id}` | Lire un incident qualifié |
| `GET` | `/health` | Health check |
| `GET` | `/metrics` | Métriques (nb qualifications, latence moyenne) |

Tous les endpoints sauf `/health` requièrent `Authorization: Bearer <API_KEY>`.

---

## Fichiers à ne pas versionner

```text
.env
incidents.db
chroma_db/
__pycache__/
*.pyc
```
