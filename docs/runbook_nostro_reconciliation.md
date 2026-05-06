# Runbook – Incidents de réconciliation Nostro

## Symptômes

- Alerte `Nostro reconciliation unmatched transactions > 0`
- Transactions en statut `UNMATCHED` dans le service nostro-reconciliation
- Écart entre solde interne et relevé MT940/MT950 du correspondant
- Réconciliation EOD marquée `INCOMPLETE` ou `FAILED`
- Alerte `Nostro account below minimum threshold` sur liquidity-manager
- Absence de réception du fichier MT940 d'un correspondant

## Services concernés

- **nostro-reconciliation** – moteur de rapprochement
- **mt-parser** – parsing des relevés MT940/MT950
- **fin-processor** – réception des messages MT940
- **liquidity-manager** – surveillance des soldes
- **nostro-db** – base des mouvements nostro

## Définitions clés

- **Nostro** : compte de la banque ouvert chez une banque correspondante
- **MT940** : relevé de compte SWIFT (Customer Statement Message)
- **MT950** : relevé de solde intermédiaire
- **UETR** : identifiant unique de transaction SWIFT gpi
- **Valeur** : date à laquelle la transaction est prise en compte pour le solde

## Causes fréquentes

1. Erreur de date de valeur dans le MT940 du correspondant (cas le plus fréquent)
2. MT940 non reçu ou reçu incomplet (problème réseau / correspondant)
3. Transaction présente dans le système interne mais non encore créditée par le correspondant (décalage horaire)
4. Erreur de parsing MT940 (format non standard d'un correspondant)
5. Paiement annulé d'un côté mais pas de l'autre
6. Transactions CLS (settlement FX) avec décalage T+1 ou T+2

## Diagnostic

### Étape 1 – Identifier l'étendue de l'écart

```bash
# Statut global de réconciliation
curl http://nostro-reconciliation:8080/api/reconciliation/status | jq '.'

# Détail des transactions non rapprochées
curl "http://nostro-reconciliation:8080/api/unmatched?date=$(date +%Y-%m-%d)" | jq '.'

# Résumé par compte nostro
curl http://nostro-reconciliation:8080/api/summary | jq '.accounts[] | select(.gap_amount != 0)'
```

### Étape 2 – Vérifier la réception des MT940

```bash
# Lister les MT940 reçus aujourd'hui
curl "http://fin-processor:8080/api/messages?type=MT940&date=$(date +%Y-%m-%d)" | jq '.count, .senders[]'

# Si un MT940 manque pour un correspondant, vérifier dans les logs
kubectl logs deployment/fin-processor -n swift --since=24h | grep "MT940" | grep -v "processed"
```

### Étape 3 – Analyser les transactions non rapprochées

```sql
-- Transactions internes sans contrepartie MT940
SELECT t.reference, t.amount, t.currency, t.value_date, t.correspondent_bic, t.status
FROM nostro_transactions t
WHERE t.reconciliation_status = 'UNMATCHED'
  AND t.value_date >= CURRENT_DATE - INTERVAL '2 days'
ORDER BY t.value_date DESC;

-- Lignes MT940 sans contrepartie interne
SELECT m.statement_ref, m.amount, m.currency, m.value_date, m.narrative
FROM mt940_lines m
WHERE m.reconciliation_status = 'UNMATCHED'
  AND m.processing_date >= CURRENT_DATE - INTERVAL '2 days';
```

### Étape 4 – Vérifier le service mt-parser

```bash
# Taux d'erreurs de parsing
curl http://mt-parser:8080/metrics | grep "parsing_error_rate"

# Dernières erreurs de parsing
curl http://mt-parser:8080/api/errors?limit=20 | jq '.errors[]'
```

## Résolution

### Cas 1 – Écart dû à une erreur de date de valeur (correspondant)

1. Identifier les transactions MT940 avec date de valeur incorrecte
2. Contacter le back-office du correspondant (team-correspondent)
3. Demander un MT940 correctif (Amended Statement)
4. Traiter le MT940 correctif manuellement

```bash
# Importer un MT940 correctif reçu hors SWIFT (par email/SFTP)
curl -X POST http://nostro-reconciliation:8080/api/import-mt940 \
  --form "file=@amended_mt940_CITIUS33_20240408.txt" \
  --form "correspondent=CITIUS33"
```

### Cas 2 – MT940 non reçu – Demande de reroutage au correspondant

1. Contacter team-correspondent pour qu'ils contactent le correspondant
2. Demander le renvoi du MT940 manquant
3. En attendant, valider manuellement le solde via le portail en ligne du correspondant

```bash
# Marquer la réconciliation comme "en attente" (évite les alertes répétées)
curl -X PATCH "http://nostro-reconciliation:8080/api/accounts/CITIUS33/reconciliation" \
  --data '{"status": "PENDING_STATEMENT", "expected_by": "2024-04-09T12:00:00Z"}'
```

### Cas 3 – Erreur de parsing MT940

```bash
# Afficher le fichier MT940 brut pour analyse
curl "http://fin-processor:8080/api/messages/MT940/{message-id}/raw"

# Forcer un re-parsing avec le profil correspondant
curl -X POST "http://mt-parser:8080/api/reparse" \
  --data '{"message_id": "{message-id}", "correspondent_profile": "BARCGB22"}'

# Si le format est nouveau, créer/mettre à jour le profil de parsing
# → Contacter team-swift pour mise à jour du profil mt-parser
```

### Cas 4 – Alerte liquidité associée à l'écart

Si le compte nostro est en dessous du seuil, contacter le desk Treasury :

1. Calculer le solde réel (solde interne + transactions en transit)
2. Si approvisionnement nécessaire, initier un virement nostro (MT202)
3. Informer le liquidity-manager du virement en cours

```bash
# Mettre à jour le solde prévisionnel dans le liquidity-manager
curl -X PATCH "http://liquidity-manager:8080/api/accounts/DEUTDEDB/forecast" \
  --data '{"inbound_expected": 5000000, "currency": "EUR", "expected_at": "2024-04-04T14:00:00Z"}'
```

## Réconciliation manuelle (dernier recours)

Si la réconciliation automatique ne peut pas être résolue dans les 4 heures :

```bash
# Forcer le rapprochement manuel d'une paire (transaction interne / ligne MT940)
curl -X POST http://nostro-reconciliation:8080/api/manual-match \
  --data '{
    "internal_ref": "TRN-20240408-001234",
    "mt940_ref": "940LINE-CITI-20240408-0089",
    "match_reason": "MANUAL_VALUE_DATE_CORRECTION",
    "validated_by": "thomas.petit@banque-swift.fr"
  }'
```

## Escalade

| Situation | Action |
| --- | --- |
| Écart < 100 000 EUR/USD | Résolution team-ops dans la journée |
| Écart 100 000 – 1 000 000 EUR | Escalader au Responsable Trésorerie |
| Écart > 1 000 000 EUR | Escalader DG + Direction Financière. Ouvrir un incident P1 |
| Transactions suspectes | Notifier team-compliance immédiatement |
| Correspondant non joignable | Contacter le correspondent banking via team-correspondent |

## Prévention

- Configurer des alertes à J+1 matin si un MT940 attendu n'est pas reçu
- Surveiller les profils de parsing mt-parser après chaque changement de format correspondant
- Planifier des revues mensuelles des procédures de réconciliation avec chaque correspondant majeur
- Tester le mécanisme de réconciliation automatique après chaque déploiement de mt-parser