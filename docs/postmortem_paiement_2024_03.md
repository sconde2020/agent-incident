# Post-mortem – Indisponibilité payments-api (15 mars 2024)

## Résumé

Le service de paiement a été indisponible pendant **1h52** (14h28 → 16h20), impactant environ **2 300 utilisateurs**. Perte estimée : 45 commandes non finalisées.

## Chronologie

| Heure | Événement |
| --- | --- |
| 14h28 | Alerte Datadog : taux d'erreurs 503 > 50% sur payments-api |
| 14h32 | Ticket INC0001042 créé par alice.martin |
| 14h35 | Agent qualification : P1 attribué, assigné team-payments |
| 14h40 | team-payments commence l'investigation |
| 15h00 | Identification : pool de connexions catalog-db saturé |
| 15h20 | Tentative de libération connexions idle – insuffisant |
| 15h45 | Décision : redémarrage catalog-service + augmentation max_connections |
| 16h10 | Service rétabli progressivement |
| 16h20 | Retour à la normale confirmé, alerte résolue |

## Cause racine

Une migration de schéma lancée manuellement sur catalog-db à 14h25 a provoqué un lock sur la table `products`. Les connexions en attente ont saturé le pool (100/100). payments-api, qui dépend de catalog-service pour la vérification des prix, a commencé à retourner des 503.

## Impact

- 2 300 utilisateurs impactés
- 45 commandes abandonnées (panier non converti)
- SLA breached : disponibilité payments-api = 97.8% sur la journée (cible : 99.95%)

## Actions correctives

| Action | Responsable | Délai |
| --- | --- | --- |
| Ajouter PgBouncer devant catalog-db | team-dba | 2024-03-22 |
| Interdire les migrations manuelles en heures ouvrées | team-dba | Immédiat |
| Ajouter alerte à 70% max_connections | team-infra | 2024-03-18 |
| Activer circuit breaker payments → catalog | team-payments | 2024-03-25 |
| Documenter procédure de migration | team-dba | 2024-03-29 |

## Leçons apprises

- Les migrations de base de données en production doivent passer par une procédure de change management
- payments-api ne doit pas être en dépendance directe de catalog-db – le circuit breaker aurait évité la cascade
- Le runbook pool de connexions était incomplet : il ne mentionnait pas l'impact des locks DDL
