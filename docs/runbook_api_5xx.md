# Runbook – Erreurs HTTP 5xx sur une API

## Symptômes

- Taux d'erreurs 500/503 > 5% sur un service
- Alertes Datadog : `HTTP 5xx rate > threshold`
- Utilisateurs signalent des pages d'erreur ou indisponibilité
- Logs applicatifs avec stack traces (NullPointerException, TimeoutError, etc.)

## Services concernés

- payments-api
- auth-service
- orders-api
- catalog-service

## Causes fréquentes

1. Exception non gérée dans le code (bug applicatif)
2. Service dépendant indisponible (cascade)
3. Erreur de configuration après déploiement
4. Saturation mémoire (OOMKilled)
5. Certificat TLS expiré sur une dépendance

## Diagnostic

### Consulter les logs applicatifs

```bash
# Logs en temps réel
kubectl logs -f deployment/<service-name> -n production --tail=100

# Filtrer les erreurs
kubectl logs deployment/<service-name> -n production | grep -E "ERROR|Exception|Traceback"
```

### Vérifier l'état des pods

```bash
kubectl get pods -n production | grep <service-name>
kubectl describe pod <pod-name> -n production
```

### Identifier si lié à un déploiement récent

```bash
kubectl rollout history deployment/<service-name> -n production
git log --oneline -10  # vérifier les commits récents
```

## Résolution

### Cas 1 – Erreur applicative (bug)

1. Identifier la stack trace dans les logs
2. Si déploiement récent → rollback immédiat

```bash
kubectl rollout undo deployment/<service-name> -n production
```

3. Ouvrir un incident de déploiement et notifier l'équipe

### Cas 2 – Service dépendant indisponible

1. Identifier la dépendance en échec (traces Datadog APM)
2. Traiter l'incident sur le service dépendant
3. Vérifier que le circuit breaker est actif pour éviter la cascade

### Cas 3 – Pod OOMKilled

```bash
# Vérifier la cause
kubectl describe pod <pod-name> -n production | grep -A5 "OOMKilled"

# Augmenter la limite mémoire temporairement
kubectl set resources deployment/<service-name> --limits=memory=1Gi -n production
```

### Cas 4 – Redémarrage des pods (dernier recours)

```bash
kubectl rollout restart deployment/<service-name> -n production
```

## Escalade

- Taux d'erreur > 20% sur service critique → **P1**, alerter l'équipe on-call immédiatement
- Impacte payments-api → alerter **team-payments** + **team-dba** en parallèle
- Impacte auth-service → alerter **team-security**

## Prévention

- Tests de non-régression en CI avant tout déploiement
- Health checks `/health` et `/ready` configurés sur tous les services
- Activer les alertes sur taux d'erreur à 1%, 5%, 20%
