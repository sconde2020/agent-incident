# Runbook – Incidents sur le service de filtrage sanctions

## Symptômes

- Alerte `Sanctions screening response time > 20s` (SLO nominal : < 2s)
- Mode dégradé activé automatiquement (`screening_mode: DEGRADED`)
- Paiements bloqués avec code `SANCTIONS_TIMEOUT` ou `SCREENING_ERROR`
- Faux positifs en masse : paiements légitimes bloqués avec `OFAC_MATCH` ou `EU_MATCH`
- Taux de faux positifs soudainement > 5% (nominal < 1%)
- Base `sanctions-db` inaccessible ou lente
- Liste de sanctions non mise à jour depuis > 7 jours

## Services concernés

- **sanctions-screening** – service de filtrage (critique)
- **sanctions-db** – base des listes de sanctions (critique)
- **payment-hub** – bloqué en amont (cascade)
- **fin-processor** – paiements en attente de validation

## Impact réglementaire

> **ATTENTION** : Tout incident sur le filtrage sanctions doit être signalé immédiatement à l'équipe **Conformité (team-compliance)** et documenté. Les paiements traités sans screening complet sont soumis à déclaration réglementaire interne.

## Causes fréquentes

1. Timeout de connexion à `sanctions-db` (connexions saturées ou réseau)
2. Mise à jour des listes de sanctions avec trop d'aliases (fuzzy matching explosif)
3. Dégradation du cache Redis des résultats de screening
4. Bug dans le moteur de matching après mise à jour de version
5. Pic de volume de paiements (batch client) saturant le service
6. Fichier liste corrompu lors du téléchargement OFAC/EU

## Diagnostic

### Étape 1 – Identifier le mode de défaillance

```bash
# Statut du service
curl http://sanctions-screening:8080/health | jq '.'

# Mode opérationnel (NORMAL / DEGRADED / DOWN)
curl http://sanctions-screening:8080/api/status | jq '.screening_mode, .list_version, .last_update'

# Métriques de latence
curl http://sanctions-screening:8080/metrics | grep "screening_response_time"
```

### Étape 2 – Vérifier la base sanctions-db

```bash
# Connexions actives
psql -h sanctions-db-prod.internal -U sanctions_ro -c \
  "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"

# Requêtes lentes
psql -h sanctions-db-prod.internal -U sanctions_ro -c \
  "SELECT query, mean_exec_time, calls FROM pg_stat_statements
   WHERE query LIKE '%sanctions%' ORDER BY mean_exec_time DESC LIMIT 10;"
```

### Étape 3 – Vérifier les versions des listes

```bash
# Version des listes chargées
curl http://sanctions-screening:8080/api/lists/status | jq '.'
# Résultat attendu : ofac_version, eu_version, un_version, last_sync_date

# Comparer avec les versions officielles disponibles
# OFAC : https://www.treasury.gov/ofac/downloads/sdn.xml (date dans le header)
# EU : https://webgate.ec.europa.eu/fsd/fsf (date de publication)
```

### Étape 4 – Analyser les faux positifs (si applicable)

```bash
# Extraire les paiements bloqués des dernières 2 heures
curl "http://sanctions-screening:8080/api/blocked-payments?since=2h" | jq '.'

# Vérifier le seuil de fuzzy matching actuel
curl http://sanctions-screening:8080/api/config | jq '.fuzzy_threshold'
# Valeur normale : 92. Si < 90 : risque élevé de faux positifs
```

## Résolution

### Cas 1 – Timeout / connexion sanctions-db

```bash
# Redémarrer le pool de connexions
curl -X POST http://sanctions-screening:8080/admin/reset-db-pool

# Si insuffisant : redémarrer le service
kubectl rollout restart deployment/sanctions-screening -n swift

# Vérifier le retour en mode NORMAL
watch -n 15 'curl -s http://sanctions-screening:8080/api/status | jq ".screening_mode"'
```

### Cas 2 – Faux positifs après mise à jour des listes

```bash
# 1. Identifier la liste problématique
curl http://sanctions-screening:8080/api/lists/status

# 2. Rollback vers la version précédente
curl -X POST http://sanctions-screening:8080/admin/lists/rollback \
  --data '{"list": "ofac", "version": "previous"}'

# 3. Ajuster le seuil de fuzzy matching si nécessaire
curl -X PATCH http://sanctions-screening:8080/admin/config \
  --data '{"fuzzy_threshold": 92}'

# 4. Recharger les listes et redémarrer le service
curl -X POST http://sanctions-screening:8080/admin/reload-lists
```

### Cas 3 – Mode dégradé actif (paiements passés sans screening complet)

> Cette procédure nécessite une **validation obligatoire de team-compliance** avant toute action.

1. Notifier immédiatement team-compliance (oncall-compliance@banque-swift.fr)
2. Activer la procédure de revue manuelle des paiements traités en mode dégradé
3. Identifier les paiements traités sans screening : aucun déblocage sans validation

```bash
# Extraire la liste des paiements traités en mode dégradé
curl "http://sanctions-screening:8080/api/payments-degraded-mode" \
  --output degraded_payments_$(date +%Y%m%d_%H%M).json

# Transmettre le fichier à team-compliance pour revue
```

### Cas 4 – Service sanctions-screening complètement indisponible

1. **NE PAS** activer le bypass total sans accord Conformité et Direction
2. Suspendre tous les paiements SWIFT entrants et sortants
3. Escalader immédiatement à team-compliance et à la Direction Conformité
4. Contacter l'éditeur du service de screening si panne applicative

```bash
# Suspension des paiements en attente (action de précaution)
curl -X POST http://payment-hub:8080/admin/pause-outbound \
  --data '{"reason": "sanctions_screening_unavailable"}'
```

## Déblocage des paiements après résolution

```bash
# Lister les paiements bloqués
curl http://payment-hub:8080/api/payments?status=SANCTIONS_HOLD | jq '.total'

# Re-soumettre au screening (par batch)
curl -X POST http://payment-hub:8080/admin/rescreen-blocked-payments \
  --data '{"batch_size": 100, "priority": "chronological"}'
```

## Escalade

| Situation | Contact | Délai max |
| --- | --- | --- |
| Timeout > 30s | team-compliance + team-swift | Immédiat |
| Mode dégradé | team-compliance (obligatoire) | Immédiat |
| Faux positifs > 5% | team-compliance | < 15 min |
| Service DOWN | Direction Conformité + RSSI | Immédiat |

## Prévention

- Tester les nouvelles versions de listes sanctions en environnement de validation avant déploiement
- Maintenir le seuil de fuzzy matching à 92% minimum
- Alerter à J-1 avant toute mise à jour majeure des listes OFAC (publication hebdomadaire le mardi)
- Monitorer le taux de faux positifs quotidiennement (cible < 0.5%)
- Garder un snapshot des listes précédentes pendant 30 jours pour rollback