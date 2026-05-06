# Runbook – Saturation du pool de connexions PostgreSQL

## Symptômes

- Erreur : `FATAL: sorry, too many clients already`
- Erreur : `connection refused` sur les appels base de données
- Métriques : `pg_stat_activity.count` proche ou égal à `max_connections`
- Alertes Datadog : `PostgreSQL max_connections reached`

## Services concernés

- catalog-service → catalog-db
- payments-api → payments-db
- auth-service → auth-db

## Causes fréquentes

1. Fuite de connexions dans le code applicatif (connexions non fermées)
2. Pic de trafic non anticipé
3. Requête longue bloquant des connexions (lock)
4. Redémarrage applicatif sans libération propre du pool

## Diagnostic

```sql
-- Nombre de connexions actives par état
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;

-- Connexions par application
SELECT application_name, count(*) FROM pg_stat_activity GROUP BY application_name ORDER BY count DESC;

-- Requêtes longues (> 5 min)
SELECT pid, now() - query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active' AND now() - query_start > interval '5 minutes';
```

## Résolution

### Étape 1 – Identifier et tuer les connexions idle

```sql
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
  AND now() - state_change > interval '10 minutes';
```

### Étape 2 – Redémarrer le service applicatif

```bash
kubectl rollout restart deployment/<service-name> -n production
```

### Étape 3 – Vérifier la configuration du pool

Vérifier dans la config applicative :
- `pool_size` : nombre de connexions maintenues ouvertes
- `max_overflow` : connexions supplémentaires autorisées
- `pool_timeout` : délai avant erreur si pool saturé
- `pool_recycle` : durée de vie max d'une connexion

### Étape 4 – Ajustement temporaire (si urgent)

```sql
-- Augmenter temporairement max_connections (nécessite redémarrage PG)
ALTER SYSTEM SET max_connections = 200;
SELECT pg_reload_conf();
```

## Escalade

Si le problème persiste après résolution du pool → escalader à **team-dba** (oncall-dba@company.com).

## Prévention

- Utiliser PgBouncer comme connection pooler devant PostgreSQL
- Mettre en place des alertes à 70% et 90% de max_connections
- Activer `idle_in_transaction_session_timeout = '5min'`
