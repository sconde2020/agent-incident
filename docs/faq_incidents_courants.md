# FAQ – Incidents courants en production

## Application inaccessible / erreur 503

**Q : Le service retourne des 503, par où commencer ?**

Vérifier dans cet ordre :
1. L'état des pods Kubernetes (`kubectl get pods -n production`)
2. Les logs applicatifs pour détecter une exception
3. Les métriques Datadog : CPU, mémoire, erreurs
4. Les services dépendants (CMDB → onglet dépendances)

Voir : [runbook_api_5xx.md](runbook_api_5xx.md)

---

## Latence élevée

**Q : Les utilisateurs signalent des lenteurs, comment diagnostiquer ?**

1. Consulter les traces APM Datadog pour identifier le span lent
2. Vérifier si corrélé à un déploiement récent
3. Contrôler les requêtes SQL lentes (`pg_stat_statements`)
4. Vérifier les appels vers des services tiers (Stripe, SendGrid...)

Voir : [runbook_api_latency.md](runbook_api_latency.md)

---

## Base de données inaccessible

**Q : Le service ne peut plus se connecter à PostgreSQL ?**

Causes les plus fréquentes :
- Pool de connexions saturé → voir [runbook_db_connection_pool.md](runbook_db_connection_pool.md)
- Réseau interne dégradé → vérifier avec `kubectl exec` + `psql`
- PostgreSQL en cours de failover → contacter team-dba

---

## Erreurs d'authentification en masse

**Q : Des utilisateurs ne peuvent plus se connecter ?**

1. Vérifier auth-service (logs + métriques)
2. Contrôler le taux d'expiration des sessions Redis
3. Vérifier que les certificats JWT ne sont pas expirés
4. Contacter team-security si suspicion d'attaque brute-force

---

## Notifications non reçues

**Q : Les emails/SMS/push ne partent plus ?**

1. Vérifier l'état des workers notification-service
2. Contrôler la file Kafka (`incidents.notifications`) – backlog
3. Vérifier les quotas SMTP (SendGrid dashboard)
4. Vérifier Firebase FCM pour les push

Équipe responsable : team-backend (#team-backend)

---

## Comment prioriser un incident ?

| Priorité | Critère |
| --- | --- |
| P1 | Service critique indisponible, > 500 utilisateurs impactés |
| P2 | Service critique dégradé OU service secondaire indisponible |
| P3 | Fonctionnalité partielle dégradée, contournement possible |
| P4 | Incident mineur, faible impact, résolution planifiable |

---

## Qui contacter en dehors des heures ouvrées ?

| Équipe | Contact on-call |
| --- | --- |
| Paiements | oncall-payments@company.com |
| Backend | oncall-backend@company.com |
| Sécurité | oncall-security@company.com |
| Infra / DBA | oncall-infra@company.com |
