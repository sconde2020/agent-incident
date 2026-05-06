# 🟦 EPIC / STORY

## 🤖 Agent RUN – Qualification intelligente des tickets incidents

### 📝 Description

Développer un agent intelligent de traitement des tickets incidents en environnement RUN permettant d’automatiser la **qualification, priorisation, enrichissement, routage et suggestion de résolution**.

L’agent s’appuie sur une architecture **RAG (Retrieval Augmented Generation)** et exploite des sources IT internes (ITSM, monitoring, CMDB, documentation) sans entraînement de modèle.

Objectif : réduire le temps de traitement des incidents et améliorer la qualité de résolution et de routing.

---

### ⚙️ Fonctionnalités globales

* Classification multi-niveaux des tickets incidents
* Détection automatique de criticité (impact / urgence / service)
* Recherche de doublons et détection d’incident majeur
* Suggestion de résolution basée sur historique et documentation
* Routage intelligent vers les équipes techniques
* Enrichissement automatique des tickets avec contexte IT
* Génération de recommandations actionnables (runbooks)

---

### 🛠️ Outils intégrés

* ITSM : ServiceNow / Jira Service Management
* Monitoring : Datadog / Prometheus / Grafana
* Documentation : Confluence
* CMDB : ServiceNow CMDB (ou équivalent)

---

### 📊 Données exploitées

* Historique des tickets ITSM
* Documentation technique (runbooks, FAQ, post-mortems)
* Métriques et alertes de monitoring
* Modèle CMDB (applications, dépendances, ownership)

---

### Architecture

```text
              ┌──────────────────┐
              │      ITSM        │
              │   (ServiceNow)   │
              └────────┬─────────┘
                       │ incident.created
                       ▼
              ┌──────────────────────┐
              │     Kafka Topic      │
              │  incidents.created   │
              └──────────┬───────────┘
                         │
                         ▼
          ┌──────────────────────────────┐
          │      Agent Orchestrator      │
          │  (Kafka Consumer - Python)   │
          └───┬──────────┬───────┬───┬───┘
              │          │       │   │
              ▼          ▼       ▼   ▼
         ┌─────────┐ ┌────────┐ ┌──────┐ ┌───────────┐
         │  ITSM   │ │Monitor.│ │ CMDB │ │Confluence │
         │   API   │ │  API   │ │  API │ │   API     │
         └────┬────┘ └───┬────┘ └──┬───┘ └─────┬─────┘
              │          │         │             │
              └──────────┴────┬────┴─────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │   RAG + LLM Engine     │
                 │  (Claude / GPT-4o)     │
                 │  classification,       │
                 │  scoring, routing,     │
                 │  suggestion résolution │
                 └────────────┬───────────┘
                              │
               ┌──────────────┴─────────────┐
               ▼                            ▼
  ┌────────────────────────┐   ┌────────────────────────┐
  │     Update ITSM        │   │     Kafka Output       │
  │  (ticket enrichi :     │   │  incidents.qualified   │
  │  classification,       │   │  (événement résultat)  │
  │  priorité, équipe,     │   └────────────────────────┘
  │  suggestions)          │
  └────────────────────────┘
```

---

### Architecture simplifiée – mode développement local

Les APIs externes sont remplacées par **SQLite** (données structurées) et un **Vector Store local** (documentation). Kafka est supprimé : l'incident est injecté directement via script ou CLI.

```text
              ┌──────────────────────────┐
              │     Nouvel incident      │
              │    (script / CLI)        │
              └────────────┬─────────────┘
                           │
                           ▼
          ┌────────────────────────────────┐
          │       Agent Orchestrator       │
          │           (Python)             │
          └───────────┬────────────────────┘
                      │
           ┌──────────┴──────────┐
           ▼                     ▼
  ┌─────────────────┐   ┌─────────────────────┐
  │   SQLite DB     │   │   Vector Store      │
  │─────────────────│   │   (Chroma)          │
  │ incidents       │   │─────────────────────│
  │ incident_history│   │ runbooks (.md)      │
  │ alerts          │   │ post-mortems (.md)  │
  │ metrics         │   │ FAQ (.md)           │
  │ services (CMDB) │   └──────────┬──────────┘
  │ teams           │              │
  └────────┬────────┘              │
           └──────────┬────────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │   RAG + LLM Engine     │
         │  (Claude / GPT-4o)     │
         │  classification,       │
         │  scoring, routing,     │
         │  suggestion résolution │
         └────────────┬───────────┘
                      │
                      ▼
         ┌────────────────────────┐
         │    Update SQLite       │
         │  (incident enrichi :   │
         │  priorité, catégorie,  │
         │  équipe, suggestions)  │
         └────────────────────────┘
```

| Composant prod | Remplacement local |
| --- | --- |
| ITSM API (ServiceNow) | SQLite – tables `incidents`, `incident_history` |
| Monitoring API (Datadog) | SQLite – tables `alerts`, `metrics` |
| CMDB API (ServiceNow) | SQLite – tables `services`, `teams`, `databases` |
| Confluence API | Fichiers `.md` indexés dans Chroma |
| Kafka Topic | Appel direct Python (pas de bus) |
| Kafka Output | Écriture SQLite (mise à jour de l'incident) |

---

### 🔧 Stack technique

| Couche | Choix |
| --- | --- |
| Langage | Python 3.11+ |
| Kafka consumer/producer | `confluent-kafka` |
| RAG framework | `LangChain` ou `LlamaIndex` |
| LLM | Claude (Anthropic SDK) ou GPT-4o (OpenAI SDK) |
| Embeddings | `sentence-transformers` ou API embeddings LLM |
| Vector store | `pgvector` (PostgreSQL) ou `Chroma` (local dev) |
| API interne | `FastAPI` (si exposition HTTP nécessaire) |
| Connecteurs ITSM | `pysnow` (ServiceNow) / API REST Jira |
| Monitoring | API REST Datadog / Prometheus HTTP API |

---

## 🚀 Résultat attendu global

* réduction du temps de qualification incident
* amélioration du routage des tickets
* accélération de la résolution (N1/N2)
* industrialisation du support RUN via automatisation intelligente

---

## 🧩 Sous-tickets

| # | Sous-ticket | Fichier |
| --- | --- | --- |
| 1 | Ingestion ITSM | [st_01_ingestion_itsm.md](sous-tickets/st_01_ingestion_itsm.md) |
| 2 | Intégration Monitoring & Observabilité | [st_02_monitoring_observabilite.md](sous-tickets/st_02_monitoring_observabilite.md) |
| 3 | Intégration CMDB | [st_03_integration_cmdb.md](sous-tickets/st_03_integration_cmdb.md) |
| 4 | Ingestion documentation (RAG) | [st_04_ingestion_documentation_rag.md](sous-tickets/st_04_ingestion_documentation_rag.md) |
| 5 | Moteur de classification | [st_05_moteur_classification.md](sous-tickets/st_05_moteur_classification.md) |
| 6 | Moteur de scoring de criticité | [st_06_moteur_scoring_criticite.md](sous-tickets/st_06_moteur_scoring_criticite.md) |
| 7 | Détection de doublons & incident majeur | [st_07_detection_doublons_incident_majeur.md](sous-tickets/st_07_detection_doublons_incident_majeur.md) |
| 8 | Routage intelligent | [st_08_routage_intelligent.md](sous-tickets/st_08_routage_intelligent.md) |
| 9 | Suggestion de résolution (RAG) | [st_09_suggestion_resolution_rag.md](sous-tickets/st_09_suggestion_resolution_rag.md) |
| 10 | Orchestration agent RUN (Kafka event-driven) | [st_10_orchestration_kafka.md](sous-tickets/st_10_orchestration_kafka.md) |
