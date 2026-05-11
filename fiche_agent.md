# Agent de qualification des incidents SWIFT

---

## Problème

Les équipes support trient manuellement chaque incident SWIFT (priorité P1–P4, catégorie, équipe, runbook), soit ~15 min/incident et **1 250 €/jour** pour 200 tickets.

---

## Solution

Agent RAG + LLM **(OpenAI gpt-4o-mini)** orchestrant 5 tools déterministes (CMDB, monitoring, détection doublon, détection incident majeur, incidents similaires) — pipeline en 9 étapes, qualification en < 5 s, sortie validée avant écriture en base.

---

## KPIs

| Indicateur | Observé | Cible |
| --- | --- | --- |
| Taux de qualification réussie | 92 % | 95 % |
| Temps de réponse moyen | 1 515 ms | < 5 000 ms |
| Coût / requête | $0,00052 | < $0,001 |

---

## ROI

**68 082 %** — gain mensuel estimé : **~22 467 €**

| | Sans agent | Avec agent |
| --- | --- | --- |
| Volume | 200 incidents / jour | 200 incidents / jour |
| Tickets automatisés | 0 | 120 (60 %) |
| Coût traitement | 1 250 €/jour | 500 €/jour |
| Coût agent | — | 1,10 €/jour |
| **Économie nette** | — | **~749 €/jour** |

> Coût agent détaillé : API gpt-4o-mini 200 × $0,00052 = 0,10 €/jour · Hébergement 1 €/jour

---

## Plan de déploiement

**Pilote** — team-ops + team-swift · 50 incidents/jour · 2 semaines
Critère de sortie : taux de qualification ≥ 90 % validé par un opérateur senior

**Généralisation** — déploiement sur 200 incidents/jour après validation compliance et audit sécurité (filtrage sanctions, anti-injection prompt)
