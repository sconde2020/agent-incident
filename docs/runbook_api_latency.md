# Runbook – Latence élevée sur une API

## Symptômes

- P99 latency > 5 secondes
- Timeouts côté clients (frontend, mobile)
- Alertes Datadog : `P99 latency > threshold`
- Accumulation de requêtes en attente dans les logs

## Services concernés

- orders-api
- payments-api
- catalog-service

## Causes fréquentes

1. Dépendance lente (base de données, service tiers)
2. Requête SQL non optimisée (index manquant, full scan)
3. Saturation des ressources CPU ou mémoire
4. Déploiement récent introduisant une régression
5. Appel externe (API tierce) dégradé

## Diagnostic

### Vérifier les métriques service

```bash
# Latence par endpoint (Datadog)
avg:trace.django.request{service:orders-api} by {resource_name}.rollup(avg, 60)

# Vérifier si corrélé à un déploiement
kubectl rollout history deployment/orders-api -n production
```

### Identifier la dépendance lente

```bash
# Traces distribuées – chercher le span le plus long
# Dans Datadog APM : filtrer sur service=orders-api, trier par duration DESC
```

### Vérifier la base de données

```sql
-- Requêtes lentes (> 2s)
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;
```

## Résolution

### Cas 1 – Requête SQL lente

```sql
-- Analyser le plan d'exécution
EXPLAIN ANALYZE <requête lente>;

-- Ajouter un index si full scan détecté
CREATE INDEX CONCURRENTLY idx_orders_user_id ON orders(user_id);
```

### Cas 2 – Service dépendant dégradé

Vérifier le statut du service dépendant et activer le circuit breaker si disponible :

```python
# Vérifier timeout configuré sur le client HTTP
# Réduire temporairement le timeout pour fail fast
```

### Cas 3 – Régression après déploiement

```bash
# Rollback vers la version précédente
kubectl rollout undo deployment/orders-api -n production
```

### Cas 4 – Saturation ressources

```bash
# Augmenter les replicas
kubectl scale deployment/orders-api --replicas=4 -n production
```

## Escalade

- Latence persistante > 30 min → escalader à **team-backend** (#team-backend)
- Si origine base de données → escalader à **team-dba**

## Prévention

- Définir des SLO de latence par endpoint
- Activer le circuit breaker sur les appels inter-services
- Mettre en place des tests de performance en CI/CD
