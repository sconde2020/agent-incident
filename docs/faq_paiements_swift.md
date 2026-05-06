# FAQ – Incidents courants sur les Paiements SWIFT

## Connectivité SWIFTNet

**Q : SWIFTNet est inaccessible, que faire en premier ?**

Vérifier dans cet ordre :
1. Statut SWIFT Alliance Access : `systemctl status swift-alliance`
2. Date d'expiration du certificat PKI : `openssl x509 -in /opt/swift/certs/swiftnet-prod.pem -noout -dates`
3. Connectivité réseau vers SWIFTNet (ping + traceroute)
4. Statut HSM : `/opt/hsm/bin/hsm_test --ping`
5. Page de statut SWIFT Inc. : `https://www.swift.com/about-us/swift-news/operational-status`

Voir : [runbook_swift_fin_indisponible.md](runbook_swift_fin_indisponible.md)

---

**Q : Des messages SWIFT sont envoyés mais ne reçoivent pas d'ACK, est-ce grave ?**

Oui, c'est critique. Un message sans ACK SWIFT peut signifier :
- Le message est perdu en transit (à re-émettre)
- Le réseau FIN est congestionné (attendre et surveiller)
- Le correspondant a un problème (vérifier ses statuts)

**À ne jamais faire** : re-émettre un paiement sans vérifier côté correspondant, au risque de créer un doublon (voir procédure de vérification UETR ci-dessous).

Voir : [runbook_swift_fin_indisponible.md](runbook_swift_fin_indisponible.md)

---

## Messages SWIFT rejetés

**Q : Un MT103 est rejeté avec le code "BIC_VALIDATION_FAILED", que faire ?**

1. Vérifier le BIC saisi (11 caractères, format `BANKCCLL` ou `BANKCCLLBBB`)
2. Consulter le répertoire BIC officiel SWIFT : `https://www.swift.com/our-solutions/compliance-and-shared-services/bankplusbic`
3. Vérifier si le BIC est dans le cache local bic-validator : `curl http://bic-validator:8080/api/lookup/{BIC}`
4. Si le BIC est valide mais rejeté : probablement un problème de cache – contacter team-swift pour flush du cache Redis BIC

Les codes d'erreur courants :
| Code | Signification |
| --- | --- |
| `BIC_NOT_FOUND` | BIC absent du répertoire local |
| `BIC_INVALID_FORMAT` | Format BIC incorrect (longueur, caractères) |
| `BIC_INACTIVE` | BIC présent mais marqué inactif |

---

**Q : Un MT202 est rejeté par le correspondant avec "AC04 – Account Closed", mais notre compte nostro est actif. Pourquoi ?**

Ce rejet peut indiquer :
- Modification du numéro de compte nostro chez le correspondant non répercutée dans notre référentiel
- Erreur de routage vers le mauvais compte (vérifier le champ 57A du MT202)
- Problème temporaire chez le correspondant (contacter team-correspondent)

Action : contacter immédiatement team-correspondent pour vérification du référentiel nostro.

---

**Q : Des paiements URGENT (champ 23B: URGP) ne sont pas traités en priorité. Comment forcer la priorisation ?**

```bash
# Vérifier la configuration de priorisation dans payment-router
curl http://payment-router:8080/api/config/priority-rules

# Forcer le retraitement avec priorité haute (si blocage)
curl -X POST http://payment-hub:8080/api/payments/{payment-id}/reprioritize \
  --data '{"priority": "URGENT"}'
```

Si le problème est systématique, ouvrir un ticket pour team-payments (bug probable dans payment-router).

---

## Filtrage Sanctions

**Q : Un paiement est bloqué avec "OFAC_MATCH" mais la contrepartie est légitime. Comment débloquer ?**

1. **Ne jamais débloquer sans validation Compliance**
2. Contacter team-compliance (oncall-compliance@banque-swift.fr) avec le détail du paiement
3. L'analyste Compliance vérifie le matching dans la base OFAC
4. Si faux positif confirmé, l'analyste autorise le déblocage avec justification documentée

```bash
# Voir le détail du matching sanctions (accès team-compliance uniquement)
curl http://sanctions-screening:8080/api/blocked/{payment-id}/match-details
```

---

**Q : Le taux de faux positifs sanctions a augmenté depuis la dernière mise à jour des listes. Que faire ?**

1. Vérifier la date de la mise à jour : `curl http://sanctions-screening:8080/api/lists/status`
2. Comparer le taux de faux positifs avant/après : métriques Datadog
3. Si taux > 5% : appliquer le rollback des listes (team-compliance) et ajuster le seuil de fuzzy matching

Voir : [runbook_sanctions_screening.md](runbook_sanctions_screening.md)

---

**Q : Le service sanctions-screening est en mode dégradé. Les paiements sont-ils conformes ?**

En mode dégradé, les paiements sont traités avec une validation réduite. C'est un risque réglementaire significatif. Actions obligatoires :
1. Notifier immédiatement team-compliance
2. Mettre en suspens les paiements > 100 000 EUR jusqu'au retour en mode normal
3. Documenter tous les paiements traités en mode dégradé pour revue a posteriori

---

## Réconciliation Nostro

**Q : La réconciliation nostro est incomplète ce matin, quel est le délai acceptable ?**

| Type d'écart | Délai de résolution cible |
| --- | --- |
| Technique (parsing MT940) | < 2 heures |
| Date de valeur erronée (correspondant) | < 4 heures (contact correspondant) |
| Transaction manquante (non créditée) | < 24 heures (investigation correspondant) |
| Litige > 1 M EUR | Immédiat – P1, escalade Direction |

---

**Q : Un MT940 attendu d'un correspondant n'est pas arrivé. Quand relancer ?**

- Si non reçu à J+2h du cut-off du correspondant → contacter team-correspondent
- Si non reçu à J+4h → demander renvoi officiel via MT195 (Request for cancellation / Query)
- Utiliser le portail de suivi correspondant en attendant pour récupérer le solde manuellement

Voir : [runbook_nostro_reconciliation.md](runbook_nostro_reconciliation.md)

---

## SWIFT gpi

**Q : Un client demande le statut de son paiement gpi, mais le UETR n'est pas trouvé dans gpi-tracker. Pourquoi ?**

Causes possibles :
1. Le paiement n'est pas encore traité par fin-processor (vérifier le statut dans payment-hub)
2. Le gpi-tracker est en retard (lag Kafka) – vérifier `curl http://gpi-tracker:8080/api/lag`
3. Le paiement n'est pas un paiement gpi (expéditeur non gpi-member)
4. Problème de propagation UETR entre payment-hub et gpi-tracker

```bash
# Rechercher un paiement par UETR dans payment-hub
curl "http://payment-hub:8080/api/payments?uetr={UETR-value}"
```

---

**Q : Un paiement gpi est bloqué en statut ACSP depuis plus d'une heure, que signifie-t-il ?**

| Statut gpi | Signification |
| --- | --- |
| `ACSP` | Accepté, en cours de traitement par la banque intermédiaire |
| `ACCC` | Crédité sur le compte du bénéficiaire (final) |
| `RJCT` | Rejeté – un code de rejet est associé |
| `PDNG` | En attente (compliance hold, cut-off, etc.) |

Si `ACSP` depuis > 30 min, contacter la banque intermédiaire via gpi Observer sur le portail SWIFT.

---

## Gestion des Correspondants

**Q : Comment vérifier si notre RMA avec un correspondant est actif ?**

```bash
# Vérifier le statut RMA d'un correspondant
curl "http://correspondent-service:8080/api/rma/{BIC}" | jq '.rma_status, .expiry_date'
```

Si `rma_status: EXPIRED`, initier immédiatement le renouvellement RMA via SWIFT Alliance. Cette opération peut prendre 4 à 24h selon le correspondant.

---

## Priorisation des incidents SWIFT

| Priorité | Critère SWIFT |
| --- | --- |
| **P1** | SWIFTNet down, payment-hub down total, batch cut-off échoué, SWIFT Alliance crash, écart nostro > 1 M EUR |
| **P2** | Sanctions en mode dégradé, gpi-tracker down, backlog FIN > 200 messages, RMA expiré correspondant majeur, latence payment-hub > 10s |
| **P3** | BIC validator erreurs < 20%, réconciliation incomplete < 500K EUR, MT940 non reçu, alerte liquidité non critique |
| **P4** | Alertes informationnelles, incidents planifiés, dégradation non impactante |

---

## Contacts d'urgence SWIFT

| Équipe | Canal | Contact on-call |
| --- | --- | --- |
| SWIFT & Paiements Internationaux | #team-swift | oncall-swift@banque-swift.fr |
| Conformité & Sanctions | #team-compliance | oncall-compliance@banque-swift.fr |
| Opérations Bancaires | #team-ops | oncall-ops@banque-swift.fr |
| Relations Correspondants | #team-correspondent | oncall-correspondent@banque-swift.fr |
| Infrastructure | #team-infra | oncall-infra@company.com |
| SWIFT Inc. Support 24/7 | — | +32 2 655 3111 |