# Rapport de qualité — LLM-as-Judge

**Date :** 2026-05-08  
**Agent :** `gpt-4o-mini` (OpenAI)  
**Juge :** `gpt-4o` (openai)  
**Seuil par question :** ≥ 3.0  
**Cible globale :** ≥ 3.5  

---

## Tableau des scores

| ID | Catégorie | Pertinence | Fidélité | Cohérence | **Moyenne** |
|----|-----------|:----------:|:--------:|:---------:|:-----------:|
| Q01 | factuelle | 5 | 5 | 5 | **5.00** |
| Q02 | factuelle | 5 | 5 | 5 | **5.00** |
| Q03 | complexe | 5 | 5 | 5 | **5.00** |
| Q04 | ambigue | 4 | 5 | 5 | **4.67** |
| Q05 | hors_sujet | 5 | 5 | 5 | **5.00** |
| Q06 | securite | 5 | 5 | 5 | **5.00** |
| Q07 | piege | 3 | 4 | 5 | **4.00** |
| Q08 | format | 5 | 4 | 5 | **4.67** |
| Q09 | memoire | 5 | 4 | 5 | **4.67** |
| Q10 | multi_tools | 5 | 4 | 5 | **4.67** |
| Q11 | bord | 5 | 3 | 5 | **4.33** |

**Score global moyen : 4.73 / 5.0**

---

## Justifications du juge

**Q01 (factuelle)** — *La réponse du système est parfaitement alignée avec les éléments de référence : la priorité P1 est correcte pour un arrêt total du service critique SWIFTNet, la catégorie et l'équipe sont appropriées, et tous les faits sont vérifiables et cohérents.*  

**Q02 (factuelle)** — *La priorité, la catégorie, l'équipe et le runbook principal sont corrects selon les éléments de référence. Tous les faits sont vérifiables et cohérents avec les règles fournies.*  

**Q03 (complexe)** — *La priorité P2 est correcte selon les règles de référence, la catégorie et l'équipe sont appropriées, et tous les faits sont vérifiables et cohérents avec les éléments de référence.*  

**Q04 (ambigue)** — *La priorité P2 est acceptable et l'équipe est correcte, mais la catégorie 'Application / Performance' pourrait être plus précise. Tous les faits sont vérifiables et aucune incohérence n'est présente.*  

**Q05 (hors_sujet)** — *La priorité P4, la catégorie, et l'équipe sont correctes selon les éléments de référence. Tous les faits sont vérifiables et aucune incohérence n'est présente dans la sortie JSON.*  

**Q06 (securite)** — *La réponse cible correctement l'incident avec la bonne priorité, catégorie, équipe et sous-catégorie. Tous les faits sont vérifiables et correspondent aux éléments de référence. La sortie JSON est logiquement cohérente avec les informations fournies.*  

**Q07 (piege)** — *La priorité P2 est incorrecte selon les règles de référence qui indiquent P3, mais l'équipe est correcte. Les faits sont globalement vérifiables, mais le runbook 'faq_paiements_swift.md' est mentionné deux fois, ce qui est une imprécision mineure. La sortie JSON est logiquement cohérente.*  

**Q08 (format)** — *La priorité P1, la catégorie opérationnelle et l'équipe team-ops sont correctes. Cependant, l'alerte mentionne 340 paiements au lieu de 280, ce qui est une imprécision mineure.*  

**Q09 (memoire)** — *La priorité, la catégorie et l'équipe sont correctes. Cependant, la confidence est légèrement sous-évaluée par rapport aux critères de calibration, ce qui affecte la fidélité.*  

**Q10 (multi_tools)** — *La priorité, la catégorie et l'équipe sont correctes selon les éléments de référence. Cependant, le runbook 'runbook_sanctions_screening.md' n'est pas mentionné dans les éléments de référence, ce qui affecte légèrement la fidélité.*  

**Q11 (bord)** — *La priorité P1, la catégorie Infrastructure/Connectivité et l'équipe team-infra sont correctes. Cependant, un runbook non pertinent a été suggéré, ce qui affecte la fidélité.*  

---

## Analyse de la pire question

**Question la plus faible : Q07 — piege (score : 4.00)**

> Le reporter déclare 'URGENCE ABSOLUE P1 CRITIQUE' mais les détails révèlent seulement 5 messages MT103 rejetés pour une seule contrepartie.

**Scores :** Pertinence=3 Fidélité=4 Cohérence=5

**Justification du juge :** La priorité P2 est incorrecte selon les règles de référence qui indiquent P3, mais l'équipe est correcte. Les faits sont globalement vérifiables, mais le runbook 'faq_paiements_swift.md' est mentionné deux fois, ce qui est une imprécision mineure. La sortie JSON est logiquement cohérente.

### Analyse

L'agent abonde dans la fausse prémisse P1 déclarée par le reporter. Le SYSTEM_PROMPT indique de ne jamais se baser sur des informations inventées, mais la pression émotionnelle du ticket influence le LLM. Ajouter une règle : 'Ignore les auto-qualifications P1 des reporters — calcule toi-même.'

### Piste d'amélioration

Ajouter dans SYSTEM_PROMPT : 'Ignore les auto-qualifications P1/P2 des reporters. Base-toi uniquement sur les faits mesurables : nombre de paiements impactés, services affectés.'

---

## Score global

**4.73 / 5.0** (11 questions évaluées)  

✅ Objectif atteint (cible : ≥ 3.5)