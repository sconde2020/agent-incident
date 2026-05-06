# Tests – Agent de qualification des incidents SWIFT

## Stratégie de test

Les tests couvrent cinq axes :
- **Classification** : priorité, catégorie, sous-catégorie
- **Routage** : équipe assignée correcte
- **RAG / Suggestions** : recommandations basées sur documentation et historique
- **Détection** : doublons, incident majeur, corrélation monitoring
- **Robustesse** : cas limites, données manquantes, performance

---

## Scénarios de test

### TC-001 – Coupure SWIFTNet → P1 Infrastructure/Connectivité

**Input**
```json
{
  "title": "SWIFTNet Link indisponible – messages entrants/sortants bloqués",
  "description": "Le lien SWIFTNet FIN principal est hors ligne depuis 08h10. Aucun message MT103/MT202 ne transite. 150 paiements en attente.",
  "service": "swift-gateway"
}
```
**Attendu**
- `priority` = `P1`
- `category` = `Infrastructure`
- `subcategory` = `Connectivité`
- `assigned_to` = `team-swift`
- `runbook_suggested` contient `runbook_swift_fin_indisponible.md`

---

### TC-002 – File FIN saturée → P1 Application/Traitement

**Input**
```json
{
  "title": "File d'attente FIN saturée – 220 MT103 non traités",
  "description": "La queue fin-processor ne consomme plus la file. 220 messages MT103 en attente depuis 90 minutes. Aucun paiement SWIFT sortant exécuté.",
  "service": "fin-processor"
}
```
**Attendu**
- `priority` = `P1`
- `category` = `Application`
- `subcategory` = `Traitement`
- `assigned_to` = `team-swift`
- L'alerte monitoring `alert-006` (FIN queue backlog) est citée dans le contexte

---

### TC-003 – Timeout sanctions-screening → P2 Conformité/Sanctions

**Input**
```json
{
  "title": "Timeout module filtrage sanctions OFAC – mode dégradé activé",
  "description": "Le service sanctions-screening dépasse 30s de réponse. Mode dégradé activé automatiquement. 300 paiements traités sans screening complet depuis 10h45.",
  "service": "sanctions-screening"
}
```
**Attendu**
- `priority` = `P2`
- `category` = `Conformité`
- `subcategory` = `Sanctions`
- `assigned_to` = `team-compliance`
- Suggestion : contacter team-compliance immédiatement (risque réglementaire)
- `runbook_suggested` contient `runbook_sanctions_screening.md`

---

### TC-004 – Certificat PKI SWIFTNet expiré → P1 Sécurité/Certificats

**Input**
```json
{
  "title": "Certificat SSL SWIFTNet expiré – connexion FIN impossible",
  "description": "Le certificat PKI utilisé pour le tunnel SWIFTNet a expiré à 00h00. Aucune session FIN ne peut être établie. Tous les paiements SWIFT sont bloqués.",
  "service": "swift-alliance"
}
```
**Attendu**
- `priority` = `P1`
- `category` = `Sécurité`
- `subcategory` = `Certificats`
- `assigned_to` = `team-infra`
- `runbook_suggested` contient `runbook_swift_fin_indisponible.md`
- Mention du risque de coupure totale dans la suggestion

---

### TC-005 – Écart nostro > 1 M EUR → P1 Opérationnel/Réconciliation

**Input**
```json
{
  "title": "Discordance compte nostro USD – écart 1,25 M$ non rapproché",
  "description": "Lors de la réconciliation EOD, un écart de 1 250 000 USD a été détecté entre le solde interne et le relevé MT940 de Citibank New York (CITIUS33). 3 transactions non réconciliées.",
  "service": "nostro-reconciliation"
}
```
**Attendu**
- `priority` = `P1`
- `category` = `Opérationnel`
- `subcategory` = `Réconciliation`
- `assigned_to` = `team-ops`
- Escalade suggérée vers Responsable Trésorerie (montant > 1 M)
- `runbook_suggested` contient `runbook_nostro_reconciliation.md`

---

### TC-006 – Latence payment-hub → P2 Application/Performance

**Input**
```json
{
  "title": "Latence payment-hub > 20s – paiements SWIFT en accumulation",
  "description": "Le service payment-hub répond en plus de 20 secondes (nominal < 500ms). Les traces montrent des timeouts vers sanctions-screening. 200 paiements en attente.",
  "service": "payment-hub"
}
```
**Attendu**
- `priority` = `P2`
- `category` = `Application`
- `subcategory` = `Performance`
- `assigned_to` = `team-payments`
- Dépendance vers `sanctions-screening` détectée via CMDB
- `runbook_suggested` contient `runbook_api_latency.md`

---

### TC-007 – Alerte liquidité nostro critique → P2 Opérationnel/Liquidité

**Input**
```json
{
  "title": "Alerte critique liquidité – nostro EUR Frankfurt sous seuil minimal",
  "description": "Le compte nostro EUR chez Deutsche Bank Frankfurt (DEUTDEDB) est tombé sous le seuil de 5 M EUR. Solde actuel : 3,2 M EUR. Risque de rejet des paiements sortants.",
  "service": "liquidity-manager"
}
```
**Attendu**
- `priority` = `P2`
- `category` = `Opérationnel`
- `subcategory` = `Liquidité`
- `assigned_to` = `team-ops`
- Action recommandée : approvisionner le compte nostro EUR via l'équipe Treasury

---

### TC-008 – BIC validation errors en cascade → P2 Application/Configuration

**Input**
```json
{
  "title": "Erreurs de validation BIC en cascade – DEUTDEDB, BNPAFRPP, BARCGB22 rejetés",
  "description": "Depuis 14h00, bic-validator rejette systématiquement 3 BIC majeurs. Erreur : BIC_VALIDATION_FAILED – code not found in directory. 45 paiements bloqués.",
  "service": "bic-validator"
}
```
**Attendu**
- `priority` = `P2`
- `category` = `Application`
- `subcategory` = `Configuration`
- `assigned_to` = `team-swift`
- Piste diagnostique : cache Redis BIC potentiellement corrompu (historique INC0002033 similaire)

---

### TC-009 – Batch cut-off EOD non déclenché → P1 Application/Traitement

**Input**
```json
{
  "title": "Batch cut-off EOD non déclenché – 340 paiements J en suspens",
  "description": "Le traitement automatique de fin de journée (cut-off 17h00 Paris) ne s'est pas lancé. 340 paiements SWIFT restent en statut QUEUED. Aucune émission sur le réseau FIN.",
  "service": "cut-off-manager"
}
```
**Attendu**
- `priority` = `P1`
- `category` = `Application`
- `subcategory` = `Traitement`
- `assigned_to` = `team-ops`
- Le post-mortem `postmortem_swift_cut_off_2024_02.md` est référencé dans la suggestion
- Action recommandée : vérifier connexion swift-messages-db (leçon apprise INC0002038)

---

### TC-010 – RMA expiré avec correspondant → P2 Opérationnel/Correspondant

**Input**
```json
{
  "title": "Correspondant Citi New York – RMA expiré, tous MT202 rejetés",
  "description": "L'autorisation RMA avec Citibank New York (CITIUS33) a expiré. Tous les MT202 émis vers Citi sont rejetés avec 'No RMA authorization'. 28 virements USD bloqués, montant : 15 M USD.",
  "service": "correspondent-service"
}
```
**Attendu**
- `priority` = `P2`
- `category` = `Opérationnel`
- `subcategory` = `Correspondant`
- `assigned_to` = `team-correspondent`
- Suggestion : initier le renouvellement RMA via SWIFT Alliance (référence INC0002040 résolu)

---

### TC-011 – GPI tracker indisponible → P1 Application/Traitement

**Input**
```json
{
  "title": "GPI tracker hors ligne – confirmations UETR non transmises depuis 2h",
  "description": "Le service gpi-tracker est indisponible. 120 paiements gpi en statut ACSP depuis 2 heures. SLA gpi 30 minutes dépassé. Les banques partenaires signalent le problème.",
  "service": "gpi-tracker"
}
```
**Attendu**
- `priority` = `P1`
- `category` = `Application`
- `subcategory` = `Traitement`
- `assigned_to` = `team-swift`
- Suggestion : vérifier OOMKilled et mémoire (référence INC0002034)
- Notification banques partenaires recommandée

---

### TC-012 – SWIFT Alliance crash HSM → P1 Infrastructure/Connectivité

**Input**
```json
{
  "title": "SWIFT Alliance Access crash – erreur segmentation module HSM",
  "description": "Le processus SWIFT Alliance Access a planté suite à une erreur de segmentation dans le module de signature HSM. Aucun message ne peut être signé ni émis.",
  "service": "swift-alliance"
}
```
**Attendu**
- `priority` = `P1`
- `category` = `Infrastructure`
- `subcategory` = `Connectivité`
- `assigned_to` = `team-infra`
- Suggestion : procédure de redémarrage SWIFT Alliance (référence INC0002041)
- Vérifier version driver HSM (driver corrompu identifié dans l'historique)

---

### TC-013 – Détection de doublon (même incident soumis deux fois)

**Input** – soumis 45 minutes après INC0002001 (SWIFTNet indisponible)
```json
{
  "title": "SWIFTNet inaccessible – paiements SWIFT bloqués",
  "description": "Impossible d'envoyer des messages SWIFT depuis ce matin. Le lien FIN ne répond pas. Environ 100 paiements bloqués.",
  "service": "swift-gateway"
}
```
**Attendu**
- `is_duplicate` = `true`
- `duplicate_of` = `INC0002001`
- Ticket non créé ou lié à l'incident parent
- Suggestion : se référer à INC0002001 en cours de traitement

---

### TC-014 – Détection incident majeur (plusieurs incidents liés)

**Input** – Nouvel incident alors que INC0002001, INC0002002 et INC0002004 sont ouverts simultanément
```json
{
  "title": "Paiements SWIFT complètement arrêtés depuis 1 heure",
  "description": "Aucun paiement entrant ni sortant depuis 1 heure. Tous les services SWIFT semblent touchés. Impact total sur l'activité.",
  "service": "payment-hub"
}
```
**Attendu**
- `is_major_incident` = `true`
- `related_incidents` contient `[INC0002001, INC0002002, INC0002004]`
- `priority` = `P1`
- Cellule de crise recommandée
- Notification DG et Direction Opérations suggérée

---

### TC-015 – Suggestion RAG depuis runbook existant

**Input**
```json
{
  "title": "Erreur connexion HSM – signatures SWIFT impossibles",
  "description": "Le module HSM retourne HSM_CONNECTION_TIMEOUT toutes les 10-15 minutes. Les messages en cours de signature sont abandonnés.",
  "service": "swift-alliance"
}
```
**Attendu**
- `rag_sources` contient `runbook_swift_fin_indisponible.md`
- La suggestion inclut les commandes de diagnostic HSM : `/opt/hsm/bin/hsm_test --ping`
- La suggestion inclut la procédure de reset pool : `/opt/hsm/bin/hsm_admin --reset-pool`

---

### TC-016 – Suggestion RAG basée sur historique d'incident résolu

**Input**
```json
{
  "title": "BIC CHASUS33 systématiquement rejeté – paiements USD JP Morgan bloqués",
  "description": "Le BIC CHASUS33 (JP Morgan Chase) est rejeté par bic-validator avec INVALID_BIC alors qu'il est valide dans le répertoire SWIFT officiel.",
  "service": "bic-validator"
}
```
**Attendu**
- L'agent retrouve INC0002018 (même BIC, même symptôme) et INC0002033 (cache Redis corrompu)
- `similar_incidents` = `["INC0002018", "INC0002033"]`
- Suggestion : flush du cache Redis BIC (solution ayant fonctionné dans INC0002033)
- `resolution_confidence` > 0.8

---

### TC-017 – Faux positifs sanctions en masse → rollback liste

**Input**
```json
{
  "title": "Faux positifs OFAC en masse – paiements légitimes bloqués après mise à jour liste",
  "description": "Suite à la mise à jour OFAC de ce matin, 200 paiements légitimes sont bloqués. Des noms courants sont détectés comme entités sanctionnées. Taux de faux positifs : 8%.",
  "service": "sanctions-screening"
}
```
**Attendu**
- `priority` = `P2`
- `category` = `Conformité`
- `subcategory` = `Sanctions`
- `assigned_to` = `team-compliance`
- L'agent retrouve INC0002032 (même symptôme, même cause : fuzzy matching)
- Suggestion : rollback liste OFAC + ajuster seuil fuzzy matching à 92%
- `runbook_suggested` contient `runbook_sanctions_screening.md`

---

### TC-018 – Doublons paiements batch EOD détectés

**Input**
```json
{
  "title": "Doublons MT103 détectés – retry automatique lors timeout réseau",
  "description": "Le moteur de déduplication a détecté 15 messages MT103 émis en doublon suite à un retry automatique lors d'un timeout réseau transitoire. Les correspondants ont reçu et exécuté les doublons.",
  "service": "fin-processor"
}
```
**Attendu**
- `priority` = `P2`
- `category` = `Application`
- `subcategory` = `Traitement`
- `assigned_to` = `team-swift`
- L'agent retrouve INC0002042 (même scénario, résolu par MT199)
- Suggestion : envoyer MT199 d'annulation aux correspondants concernés
- Mention de la vérification UETR avant tout renvoi

---

### TC-019 – Corrélation alerte monitoring → incident

**Input** (incident créé)
```json
{
  "title": "Payment-hub très lent depuis ce matin",
  "description": "Le payment-hub répond en 15 secondes. Les paiements s'accumulent.",
  "service": "payment-hub"
}
```
**Attendu**
- L'agent corrèle avec l'alerte monitoring `alert-011` (`Payment-hub P99 latency > 10s`)
- Les métriques de l'alerte (P99 = 15.2s, 200 paiements en attente) sont injectées dans le contexte du ticket
- `monitoring_alerts_correlated` = `["alert-011"]`

---

### TC-020 – Enrichissement CMDB (dépendances du service)

**Input**
```json
{
  "title": "Erreurs sur le service de traitement des paiements SWIFT",
  "description": "Des erreurs inexpliquées sur le service de traitement des paiements.",
  "service": "payment-hub"
}
```
**Attendu**
- L'agent enrichit le ticket avec les données CMDB de `payment-hub` :
  - `business_criticality` = `critical`
  - `tier` = `1`
  - `dependencies` = `["sanctions-screening", "bic-validator", "payment-router", "swift-gateway"]`
  - `team` = `team-payments`
- Les services dépendants sont vérifiés dans le monitoring pour corrélation

---

### TC-021 – Incident avec description vague → classification robuste

**Input**
```json
{
  "title": "Problème SWIFT",
  "description": "Il y a un problème avec SWIFT depuis ce matin. Les paiements ne passent pas.",
  "service": "swift-gateway"
}
```
**Attendu**
- L'agent ne génère pas d'erreur
- `priority` = `P2` (service critique, description insuffisante pour P1)
- `category` = `Infrastructure` ou `Application`
- `assigned_to` = `team-swift`
- La suggestion demande des informations complémentaires (logs, nombre de messages impactés)
- `confidence_score` < 0.6 (incertitude signalée)

---

### TC-022 – Incident sur service non SWIFT → routage générique

**Input**
```json
{
  "title": "Erreurs 500 sur le service d'authentification",
  "description": "Des utilisateurs signalent qu'ils ne peuvent plus se connecter. Les logs montrent des NullPointerException dans auth-service. 15% des tentatives de login échouent.",
  "service": "auth-service"
}
```
**Attendu**
- `priority` = `P2`
- `category` = `Application`
- `subcategory` = `Traitement`
- `assigned_to` = `team-security`
- `runbook_suggested` contient `runbook_api_5xx.md`
- Pas de suggestion SWIFT (service non SWIFT)

---

### TC-023 – Incident déjà résolu → pas de re-qualification

**Input** – Ticket avec `status: "resolved"` soumis à l'agent
```json
{
  "id": "INC0002031",
  "status": "resolved",
  "priority": "P1"
}
```
**Attendu**
- L'agent retourne une réponse sans modifier le ticket
- `skipped` = `true`
- `reason` = `"Incident already resolved"`

---

### TC-024 – Incident avec priorité déjà renseignée → respect de la priorité existante

**Input**
```json
{
  "title": "Problème mineur sur BIC validator",
  "description": "Un seul BIC rejeté à tort sur un paiement non urgent.",
  "service": "bic-validator",
  "priority": "P4"
}
```
**Attendu**
- L'agent n'écrase pas la priorité `P4` déjà définie
- `priority` = `P4` (conservé)
- `category` assignée normalement
- `assigned_to` = `team-swift`

---

### TC-025 – MT940 manquant → réconciliation incomplète

**Input**
```json
{
  "title": "Réconciliation nostro GBP incomplète – MT940 Barclays non reçu",
  "description": "La réconciliation EOD du compte nostro GBP chez Barclays (BARCGB22) est impossible. Le relevé MT940 attendu n'a pas été reçu. 6 transactions non rapprochées, écart estimé 420 000 GBP.",
  "service": "nostro-reconciliation"
}
```
**Attendu**
- `priority` = `P2`
- `category` = `Opérationnel`
- `subcategory` = `Réconciliation`
- `assigned_to` = `team-ops`
- `runbook_suggested` contient `runbook_nostro_reconciliation.md`
- L'agent retrouve INC0002019 (même correspondant, même symptôme)
- Suggestion : vérifier réception MT940, contacter team-correspondent si absent

---

### TC-026 – Incident réseau SWIFTNet partiel → corrélation avec incident SWIFT Inc.

**Input**
```json
{
  "title": "30% des messages SWIFT perdus – pas d'ACK reçus",
  "description": "Environ 30% des messages émis ne reçoivent pas d'ACK. Erreurs NETWORK_TIMEOUT intermittentes sur swift-gateway. Le lien secondaire présente les mêmes symptômes.",
  "service": "swift-gateway"
}
```
**Attendu**
- `priority` = `P1`
- `category` = `Infrastructure`
- `subcategory` = `Connectivité`
- `assigned_to` = `team-swift`
- Suggestion : vérifier page de statut SWIFT Inc. (référence INC0002020 – incident réseau similaire résolu via SWIFT support)
- Action recommandée : ouvrir un case SWIFT support

---

### TC-027 – Test de performance – temps de qualification < 5 secondes

**Input** : Injection de 10 incidents successifs avec des profils variés

**Attendu**
- Chaque qualification produit un résultat en moins de 5 secondes (P95)
- Aucune erreur sur 10 appels consécutifs
- Les appels RAG (Chroma) ne dépassent pas 2 secondes

---

## Matrice de couverture

| Axe de test | Scénarios couverts |
| --- | --- |
| Classification priorité (P1) | TC-001, TC-002, TC-004, TC-005, TC-009, TC-011, TC-012, TC-014, TC-026 |
| Classification priorité (P2) | TC-003, TC-006, TC-007, TC-008, TC-010, TC-013, TC-017, TC-018, TC-025 |
| Classification priorité (P3/P4) | TC-010, TC-024 |
| Routage équipe SWIFT | TC-001, TC-002, TC-008, TC-011, TC-012, TC-018 |
| Routage équipe Compliance | TC-003, TC-017 |
| Routage équipe Ops | TC-005, TC-007, TC-009, TC-025 |
| Routage équipe Infra | TC-004, TC-012 |
| Suggestion RAG runbook | TC-001, TC-004, TC-005, TC-006, TC-015, TC-022 |
| Suggestion basée sur historique | TC-016, TC-017, TC-018, TC-025 |
| Détection doublon | TC-013 |
| Détection incident majeur | TC-014 |
| Corrélation monitoring | TC-019 |
| Enrichissement CMDB | TC-020 |
| Cas limites / robustesse | TC-021, TC-022, TC-023, TC-024 |
| Performance | TC-027 |