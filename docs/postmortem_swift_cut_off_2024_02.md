# Post-mortem – Échec batch cut-off SWIFT (28 février 2024)

## Résumé

Le batch de traitement fin de journée (cut-off 17h00) a échoué le 28 février 2024, laissant **280 paiements SWIFT non émis** (MT103 et MT202). L'incident a duré **2h40** (17h05–19h45). Aucun paiement n'a été perdu définitivement, mais tous ont accusé un retard de valeur d'un jour ouvré.

## Chronologie

| Heure | Événement |
| --- | --- |
| 16h55 | cut-off-manager lance la vérification pré-batch : 280 paiements en statut QUEUED |
| 17h00 | Déclenchement du batch EOD (cut-off officiel SWIFT Paris) |
| 17h05 | cut-off-manager retourne une erreur : `DB_CONNECTION_FAILED` vers swift-messages-db |
| 17h06 | Alerte Datadog : `EOD batch cut-off failed`. Ticket INC0002038 créé automatiquement |
| 17h10 | Agent qualification : P1 attribué, team-ops et team-infra notifiés |
| 17h15 | team-ops tente une relance manuelle – même erreur de connexion |
| 17h25 | team-infra identifie : swift-messages-db a failover sur replica à 16h52 suite à une interruption réseau de 8 secondes |
| 17h30 | La chaîne de connexion du cut-off-manager pointait encore sur le master (adresse IP hardcodée, non DNS) |
| 17h40 | Mise à jour de la chaîne de connexion vers le replica devenu master. Redémarrage du service |
| 17h45 | Reconnexion swift-messages-db OK. Relance batch cut-off manuelle |
| 19h45 | Dernier des 280 paiements émis avec succès sur le réseau SWIFT |

## Cause racine

Un failover automatique de swift-messages-db à 16h52 (master → replica, dû à une micro-coupure réseau de 8 secondes) a changé l'adresse IP du master. Le service cut-off-manager utilisait une **adresse IP hardcodée** en lieu et place d'un nom DNS pointant vers le master. Après le failover, il tentait de se connecter à l'ancien master (désormais replica) qui n'acceptait que les connexions en lecture seule.

**Erreur dans le code** : la chaîne de connexion dans `cut-off-manager/config/prod.yml` était :
```yaml
# MAUVAIS (avant correctif)
database:
  host: 10.10.5.42   # IP hardcodée du master
  port: 5432
```
Au lieu de :
```yaml
# CORRECT (après correctif)
database:
  host: swift-messages-db-master.internal  # DNS CNAME mis à jour lors du failover
  port: 5432
```

## Impact

| Indicateur | Valeur |
| --- | --- |
| Paiements non émis à 17h00 | 280 (254 MT103 + 26 MT202) |
| Durée de l'incident | 2 heures 40 minutes |
| Retard de valeur | J+1 (un jour ouvré) |
| Clients corporate impactés | 47 clients |
| Correspondants touchés | 8 (Deutsche Bank, BNP Paribas, Citi, Barclays, HSBC, SG, Natixis, CA) |
| Pénalités potentielles | En cours d'évaluation avec équipe Juridique |
| SLA breach | Oui – 100% des paiements EOD non respectés |

## Analyse des 5 Pourquoi

1. **Pourquoi les paiements n'ont pas été envoyés ?** → Le batch cut-off a échoué
2. **Pourquoi le batch a échoué ?** → cut-off-manager ne pouvait pas se connecter à swift-messages-db
3. **Pourquoi la connexion a échoué ?** → L'adresse IP hardcodée ne correspondait plus au master après failover
4. **Pourquoi l'IP était hardcodée ?** → La migration vers DNS n'avait pas inclus le cut-off-manager (oubli lors de la migration infrastructure de septembre 2023)
5. **Pourquoi le failover n'a pas été détecté avant impact ?** → Aucun test de failover n'avait été réalisé sur cut-off-manager depuis la migration

## Actions correctives

| Action | Responsable | Délai | Statut |
| --- | --- | --- | --- |
| Remplacer toutes les IP hardcodées par des DNS dans les services SWIFT | team-infra | 2024-03-08 | ✅ Fait |
| Ajouter test de connexion DB avec basculement DNS dans les health checks | team-swift | 2024-03-10 | ✅ Fait |
| Implémenter un test de failover DB mensuel sur les services critiques | team-dba | 2024-03-15 | ✅ Fait |
| Ajouter une alerte pré-cut-off (16h30) si connexion DB KO | team-ops | 2024-03-07 | ✅ Fait |
| Créer un runbook dédié aux échecs de batch cut-off | team-ops | 2024-03-12 | ✅ Fait |
| Mettre en place un test de non-régression du batch cut-off en recette | team-swift | 2024-03-22 | 🔄 En cours |
| Négocier avec les correspondants une tolérance sur les retards dus à des incidents techniques | team-correspondent | 2024-04-01 | 🔄 En cours |

## Leçons apprises

1. **Ne jamais hardcoder des adresses IP** pour les connexions aux bases de données critiques – utiliser systématiquement des noms DNS gérés par l'infrastructure
2. **Le cut-off SWIFT n'est pas rejouable à l'identique** – un retard d'émission entraîne un retard de valeur irréversible pour les clients
3. **Les tests de failover doivent couvrir tous les services consommateurs** d'une base de données, pas seulement les plus visibles
4. **L'alerte pre-cut-off à 16h30** aurait permis de détecter le problème 30 minutes avant le batch et de le résoudre à temps
5. **Procédure de relance manuelle** documentée – l'équipe Ops a perdu 15 minutes à chercher la procédure de relance manuelle non documentée

## Indicateurs de suivi post-incident

- Vérification hebdomadaire : aucune IP hardcodée dans les configurations SWIFT (scan automatique)
- Test mensuel : failover swift-messages-db avec vérification de tous les services SWIFT
- KPI cut-off : taux de succès du batch EOD (cible : 100%)