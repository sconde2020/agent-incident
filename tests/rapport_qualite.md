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
| Q01 | factuelle | 5 | 5 | 5 | **5.00** |
| Q02 | factuelle | 5 | 4 | 5 | **4.67** |
| Q03 | complexe | 5 | 5 | 5 | **5.00** |
| Q04 | ambigue | 4 | 5 | 5 | **4.67** |
| Q05 | hors_sujet | 5 | 5 | 5 | **5.00** |
| Q06 | securite | 3 | 3 | 3 | **3.00** |
| Q07 | piege | 3 | 4 | 5 | **4.00** |
| Q08 | format | 5 | 4 | 5 | **4.67** |
| Q09 | memoire | 5 | 4 | 5 | **4.67** |
| Q10 | multi_tools | 5 | 4 | 5 | **4.67** |
| Q11 | bord | 5 | 3 | 5 | **4.33** |

**Score global moyen : 4.52 / 5.0**

---

## Justifications du juge

**Q01 (factuelle)** — *La réponse cible correctement l'incident avec la bonne priorité, catégorie et équipe. Tous les faits sont vérifiables et cohérents avec les éléments de référence.*  

**Q02 (factuelle)** — *La priorité, la catégorie et l'équipe sont correctes selon les règles de référence. Cependant, le runbook 'faq_paiements_swift.md' n'est pas mentionné dans les éléments de référence, ce qui entraîne une légère pénalité en fidélité.*  

**Q03 (complexe)** — *La priorité P2 est correcte selon les règles de référence pour un écart nostro > 100K€. La catégorie, l'équipe et le runbook sont également appropriés et vérifiés par les éléments de référence. Toutes les parties de la réponse sont logiquement cohérentes.*  

**Q04 (ambigue)** — *La priorité P2 est acceptable et l'équipe est correcte. La catégorie 'Application / Performance' est pertinente. Tous les faits sont vérifiables et aucune incohérence n'est présente dans la sortie.*  

**Q05 (hors_sujet)** — *La priorité P4, la catégorie, et l'équipe sont correctes selon les règles fournies. Tous les faits correspondent aux éléments de référence, et la sortie est logiquement cohérente.*  

**Q06 (securite)** — *La priorité P2 est correcte, mais l'équipe devrait être 'team-infra' selon la CMDB. Le runbook 'swift_fin_indisponible.md' n'est pas pertinent pour la sécurité. L'alerte sur le certificat PKI est hors sujet, et il y a une incohérence entre la criticité 'critical' et 'is_major' à False.*  

**Q07 (piege)** — *La priorité P2 est incorrecte selon les règles de référence qui indiquent P3. Les faits sont globalement corrects mais le runbook 'faq_paiements_swift.md' est mentionné deux fois, ce qui est une imprécision mineure. La sortie est logiquement cohérente.*  

**Q08 (format)** — *La priorité P1 est correcte car il s'agit d'un arrêt total d'un service critique. Tous les faits sont vérifiables, mais l'alerte mentionne 340 paiements au lieu de 280, ce qui est une imprécision mineure. La cohérence entre les éléments est maintenue.*  

**Q09 (memoire)** — *La priorité, la catégorie et l'équipe sont correctes. Une légère imprécision dans le confidence score, mais aucun runbook inventé.*  

**Q10 (multi_tools)** — *La priorité, la catégorie et l'équipe sont correctes. Cependant, le runbook 'faq_paiements_swift.md' est mentionné deux fois, ce qui est une imprécision mineure.*  

**Q11 (bord)** — *La priorité P1, la catégorie Infrastructure/Connectivité et l'équipe team-infra sont correctes. Cependant, un runbook non pertinent est suggéré, ce qui affecte la fidélité.*  

---

## Analyse de la pire question

**Question la plus faible : Q06 — securite (score : 3.00)**

> Tentatives d'accès non autorisé détectées sur le HSM de SWIFT Alliance Access en pleine nuit.

**Scores :** Pertinence=3 Fidélité=3 Cohérence=3

**Justification du juge :** La priorité P2 est correcte, mais l'équipe devrait être 'team-infra' selon la CMDB. Le runbook 'swift_fin_indisponible.md' n'est pas pertinent pour la sécurité. L'alerte sur le certificat PKI est hors sujet, et il y a une incohérence entre la criticité 'critical' et 'is_major' à False.

### Analyse

L'incident de sécurité n'est pas correctement catégorisé. Le corpus ne contient pas de runbook sécurité dédié : la fidélité souffre de suggestions inventées. Ajouter un runbook_security_incident.md dans docs/ améliorerait significativement le score.

### Piste d'amélioration

Créer `docs/runbook_security_incident.md` couvrant : accès HSM non autorisé, tentative d'intrusion sur SWIFT Alliance, procédure de notification RSSI et isolement réseau. Réindexer la collection ChromaDB.

---

## Score global

**4.52 / 5.0** (11 questions évaluées)  

✅ Objectif atteint (cible : ≥ 3.5)