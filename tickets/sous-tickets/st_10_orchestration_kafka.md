# 🟨 10. Orchestration agent RUN (Kafka event-driven)

### 📝 Description

Mettre en place un service d'orchestration asynchrone basé sur Kafka pour traiter les tickets incidents ITSM.
Le service consomme les événements de création de tickets, enrichit le contexte via RAG, exécute l'analyse via LLM, puis met à jour l'ITSM avec la classification, la criticité, le routing et les suggestions de résolution.

### 🛠️ Outils

* Kafka (event streaming) – `confluent-kafka`
* ITSM : ServiceNow / Jira Service Management
* Monitoring : Datadog / Prometheus / Grafana
* CMDB : ServiceNow CMDB
* Documentation : Confluence

### 📊 Données

* événements Kafka (incident_created)
* tickets ITSM (détails + historique)
* métriques monitoring (alertes, erreurs, latence)
* données CMDB (dépendances, ownership)
* documentation (runbooks, post-mortems)

### ⚙️ Fonctionnalités

* consommation Kafka des tickets incidents
* orchestration des appels ITSM / monitoring / CMDB / docs
* construction du contexte RAG
* appel LLM pour classification et scoring
* génération de suggestions de résolution
* mise à jour automatique de l'ITSM ou publication Kafka

### 🎯 Objectif

Centraliser et automatiser le traitement des tickets incidents via une architecture event-driven scalable, afin d'améliorer la qualification, la priorisation et la résolution des incidents RUN.
