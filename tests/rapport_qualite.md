# Rapport de qualité — LLM-as-Judge

**Date :** 2026-05-07  
**Agent :** `gpt-4o-mini` (OpenAI)  
**Juge :** `gpt-4o` (openai)  
**Seuil par question :** ≥ 3.0  
**Cible globale :** ≥ 3.5  

---

## Tableau des scores

| ID | Catégorie | Pertinence | Fidélité | Cohérence | **Moyenne** |
|----|-----------|:----------:|:--------:|:---------:|:-----------:|
| Q01 | factuelle | 5 | 4 | 5 | **4.67** |
| Q02 | factuelle | 5 | 4 | 5 | **4.67** |
| Q03 | complexe | 5 | 4 | 5 | **4.67** |
| Q04 | ambigue | 2 | 3 | 4 | **3.00** |
| Q05 | hors_sujet | 2 | 5 | 3 | **3.33** |
| Q06 | securite | 3 | 3 | 4 | **3.33** |
| Q07 | piege | 3 | 4 | 5 | **4.00** |
| Q08 | format | 5 | 4 | 5 | **4.67** |
| Q09 | memoire | 5 | 4 | 5 | **4.67** |
| Q10 | multi_tools | 5 | 4 | 5 | **4.67** |
| Q11 | bord | 5 | 3 | 4 | **4.00** |

**Score global moyen : 4.15 / 5.0**

---

## Justifications du juge

**Q01 (factuelle)** — *La priorité, la catégorie et l'équipe sont correctes selon les éléments de référence. Cependant, le runbook est mentionné plusieurs fois dans rag_docs, ce qui est une imprécision mineure.*  

**Q02 (factuelle)** — *La priorité, la catégorie et l'équipe sont correctes selon les règles de référence. Cependant, l'alerte mentionne une expiration dans 7 jours, ce qui est incorrect par rapport à l'incident soumis.*  

**Q03 (complexe)** — *La priorité, la catégorie et l'équipe sont correctes selon les règles de référence. Cependant, il y a une répétition du runbook dans 'rag_docs', ce qui est une imprécision mineure.*  

**Q04 (ambigue)** — *La priorité P1 est incorrecte car l'impact n'est pas chiffré, ce qui devrait être P2 ou P3. La confiance est trop élevée à 0.85. Un runbook non référencé est mentionné, ce qui affecte la fidélité.*  

**Q05 (hors_sujet)** — *La priorité devrait être P4 selon les règles de référence, et l'équipe 'team-ops' est correcte. Les faits sont vérifiables et cohérents avec les éléments de référence, mais il y a une incohérence entre la priorité et la description.*  

**Q06 (securite)** — *La priorité P2 est correcte, mais la catégorie devrait être 'Sécurité' sans 'Configuration'. Le runbook mentionné n'est pas spécifiquement lié à la sécurité, ce qui affecte la fidélité. La cohérence est globalement bonne, mais il y a une légère incohérence avec la catégorie.*  

**Q07 (piege)** — *La priorité P2 est incorrecte selon la règle P3 pour 1 contrepartie et <50 paiements. Les faits sont globalement corrects mais le runbook est répété. La sortie est logiquement cohérente.*  

**Q08 (format)** — *La priorité, la catégorie et l'équipe sont correctes selon les règles de référence. Cependant, il y a une imprécision dans le nombre de paiements mentionnés dans les alertes, ce qui affecte légèrement la fidélité.*  

**Q09 (memoire)** — *La priorité P2 est correcte selon les éléments de référence. Tous les faits sont vérifiables, mais un runbook est mentionné deux fois, ce qui est une imprécision mineure. La sortie est logiquement cohérente avec le service et l'équipe.*  

**Q10 (multi_tools)** — *La priorité, la catégorie et l'équipe sont correctes. Cependant, le runbook mentionné n'est pas explicitement référencé dans les éléments factuels, ce qui affecte légèrement la fidélité.*  

**Q11 (bord)** — *La priorité P1 est correcte vu l'impact potentiel sur les services critiques. Cependant, le runbook mentionné n'est pas référencé, ce qui affecte la fidélité. La cohérence est globalement bonne, mais le confidence score est trop bas pour un incident SWIFT.*  

---

## Analyse de la pire question

**Question la plus faible : Q04 — ambigue (score : 3.00)**

> Signalement vague : 'une erreur sur les paiements, les clients se plaignent'. Aucune métrique ni log fourni.

**Scores :** Pertinence=2 Fidélité=3 Cohérence=4

**Justification du juge :** La priorité P1 est incorrecte car l'impact n'est pas chiffré, ce qui devrait être P2 ou P3. La confiance est trop élevée à 0.85. Un runbook non référencé est mentionné, ce qui affecte la fidélité.

### Analyse

Face à une description vague, l'agent sur-qualifie ou sous-qualifie. Une règle explicite dans le SYSTEM_PROMPT pour demander une clarification ou fixer un seuil de confidence minimal en cas de contexte insuffisant aiderait.

### Piste d'amélioration

Ajouter dans SYSTEM_PROMPT : 'Si impact non chiffré et service inconnu, assigner P3 maximum et fixer confidence ≤ 0.4.' Documenter ce comportement dans les règles de calibration.

---

## Score global

**4.15 / 5.0** (11 questions évaluées)  

✅ Objectif atteint (cible : ≥ 3.5)