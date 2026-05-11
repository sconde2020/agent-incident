# Rapport de qualité — LLM-as-Judge

**Date :** 2026-05-11  
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
| Q04 | ambigue | 4 | 3 | 5 | **4.00** |
| Q05 | hors_sujet | 5 | 5 | 5 | **5.00** |
| Q06 | securite | 5 | 5 | 5 | **5.00** |
| Q07 | piege | 3 | 4 | 5 | **4.00** |
| Q08 | format | 5 | 4 | 5 | **4.67** |
| Q09 | memoire | 5 | 4 | 5 | **4.67** |
| Q10 | multi_tools | 5 | 4 | 5 | **4.67** |
| Q11 | bord | 5 | 2 | 4 | **3.67** |

**Score global moyen : 4.61 / 5.0**

---

## Justifications du juge

**Q01 (factuelle)** — *La réponse du système est parfaitement alignée avec les éléments de référence : la priorité P1 est correcte pour un arrêt total du service critique SWIFTNet, la catégorie et l'équipe sont appropriées, et tous les faits sont vérifiables et cohérents.*  

**Q02 (factuelle)** — *La priorité P2 est correcte selon la règle pour un certificat PKI expirant dans moins de 7 jours. Tous les faits sont vérifiables et le runbook principal est présent. La sortie est logiquement cohérente avec les éléments de référence.*  

**Q03 (complexe)** — *La priorité P2 est correcte selon les règles de référence, la catégorie et l'équipe sont appropriées, et tous les faits sont vérifiables et cohérents avec les éléments de référence.*  

**Q04 (ambigue)** — *La priorité P2 est acceptable, mais la confiance est incorrectement notée à 0.60 au lieu de <0.6. La catégorie et l'équipe sont correctes. Les runbooks mentionnés ne sont pas inventés, mais il y a une imprécision notable dans la confiance.*  

**Q05 (hors_sujet)** — *La priorité P4, la catégorie, l'équipe et la criticité sont correctes selon les éléments de référence. Tous les faits sont vérifiables et cohérents avec la description de l'incident.*  

**Q06 (securite)** — *La réponse qualifie correctement l'incident avec la priorité P2, la catégorie Sécurité/Accès, et l'équipe team-infra. Tous les faits sont vérifiables et cohérents avec les éléments de référence.*  

**Q07 (piege)** — *La priorité P2 est incorrecte selon les règles de référence qui indiquent P3, mais la catégorie et l'équipe sont correctes. La fidélité est presque parfaite, mais le runbook mentionné n'est pas vérifiable. La cohérence interne est maintenue.*  

**Q08 (format)** — *La priorité P1, la catégorie opérationnelle et l'équipe team-ops sont correctes. Cependant, l'alerte mentionne 340 paiements au lieu de 280, ce qui est une imprécision mineure.*  

**Q09 (memoire)** — *La priorité P2, la catégorie et l'équipe sont correctes. Une légère imprécision dans le confidence score, mais tous les faits sont vérifiables et cohérents.*  

**Q10 (multi_tools)** — *La priorité, la catégorie et l'équipe sont correctes selon les éléments de référence. Cependant, le runbook 'faq_paiements_swift.md' est mentionné deux fois, ce qui est une imprécision mineure.*  

**Q11 (bord)** — *La priorité P1 est correcte vu le risque d'extinction des services critiques. Cependant, un runbook inapproprié est suggéré, ce qui pénalise la fidélité. La cohérence est globalement bonne, mais le confidence score est légèrement au-dessus de l'attendu.*  

---

## Analyse de la pire question

**Q11 — bord (score : 3.67)**

> Une alerte de surveillance détecte une anomalie de puissance électrique dans la salle serveurs SWIFT : l'onduleur UPS-SWIFT-01 est en mode batterie depuis 8 minutes.

**Scores :** P=5 F=2 C=4

**Juge :** La priorité P1 est correcte vu le risque d'extinction des services critiques. Cependant, un runbook inapproprié est suggéré, ce qui pénalise la fidélité. La cohérence est globalement bonne, mais le confidence score est légèrement au-dessus de l'attendu.

### Analyse

Service hors CMDB + domaine adjacent mal reconnu. L'agent donne un confidence_score trop élevé ou trop bas.

### Piste d'amélioration

Ajouter dans SYSTEM_PROMPT : 'Si le service est absent de la CMDB mais la description contient des termes SWIFT/bancaires, fixer confidence entre 0.3 et 0.5.'

---

## Score global

**4.61 / 5.0** (11 questions évaluées)  

✅ Objectif atteint (cible : ≥ 3.5)