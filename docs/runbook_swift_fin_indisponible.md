# Runbook – SWIFTNet FIN indisponible / Connectivité SWIFT dégradée

## Symptômes

- Aucune session FIN active sur swift-gateway (alerte `SWIFTNet FIN connectivity lost`)
- Messages MT103/MT202 non émis, bloqués en file d'attente fin-processor
- Absence d'ACK/NAK sur messages envoyés depuis plus de 30 minutes
- Alerte `FIN queue backlog > 200` sur fin-processor
- SWIFT Alliance Access retourne `CONNECTION_REFUSED` ou `SESSION_TIMEOUT`
- Tableau de bord SWIFT monitoring : sessions FIN = 0

## Services concernés (par ordre d'impact)

- **swift-alliance** – interface physique SWIFTNet (critique)
- **swift-gateway** – passerelle FIN/InterAct/FileAct (critique)
- **fin-processor** – traitement messages MT (critique)
- **payment-hub** – orchestration paiements (critique)
- **gpi-tracker** – confirmations gpi (dégradé)

## Causes fréquentes

1. Certificat PKI SWIFTNet expiré (cause la plus fréquente)
2. Panne ou redémarrage de SWIFT Alliance Access
3. Erreur ou panne du module HSM
4. Coupure réseau entre les serveurs et SWIFTNet
5. Maintenance SWIFTNet programmée par SWIFT Inc. étendue
6. Expiration ou révocation des credentials SWIFT

## Diagnostic

### Étape 1 – Vérifier l'état de SWIFT Alliance Access

```bash
# Statut du processus Alliance
systemctl status swift-alliance

# Logs Alliance (fichier principal)
tail -200 /opt/swift/alliance/logs/alliance.log | grep -E "ERROR|WARN|DISCONNECT|CERT"

# Vérifier la date d'expiration du certificat PKI
openssl x509 -in /opt/swift/certs/swiftnet-prod.pem -noout -dates
```

### Étape 2 – Vérifier les sessions FIN actives

```bash
# Via l'API SWIFT monitoring interne
curl http://swift-monitoring:8080/api/sessions | jq '.fin_sessions'

# Logs swift-gateway
kubectl logs deployment/swift-gateway -n swift --tail=100 | grep -E "FIN|SESSION|CONNECT"
```

### Étape 3 – Vérifier le HSM

```bash
# Test de connectivité HSM
/opt/hsm/bin/hsm_test --ping

# Statut des sessions HSM
/opt/hsm/bin/hsm_status --sessions

# Si erreur HSM_CONNECTION_TIMEOUT : vérifier saturation du pool
/opt/hsm/bin/hsm_status --pool | grep "active_sessions"
```

### Étape 4 – Vérifier la connectivité réseau SWIFTNet

```bash
# Ping vers le point d'entrée SWIFTNet (adresse dédiée SWIFT)
ping -c 5 <swiftnet-entry-point-ip>

# Test port SWIFT (443 ou port dédié)
telnet <swiftnet-entry-point-ip> 443

# Tracer la route réseau
traceroute <swiftnet-entry-point-ip>
```

### Étape 5 – Consulter le tableau de bord SWIFT

Accéder au portail SWIFT Alliance Web Platform :
- URL interne : `https://alliance-web.banque-swift.fr`
- Vérifier : Sessions FIN actives, statut SWIFTNet, files d'attente

## Résolution

### Cas 1 – Certificat PKI expiré

> **Prérequis** : accès admin sur le serveur SWIFT Alliance, credentials SWIFT valides

```bash
# 1. Générer une nouvelle demande de certificat (CSR)
/opt/swift/bin/swift_cert_manager --generate-csr \
  --cn "BANKFR-SWIFT-PROD-01" \
  --out /opt/swift/certs/renewal.csr

# 2. Soumettre le CSR sur le portail SWIFT (https://www2.swift.com/mkslweb/)
# 3. Télécharger le certificat renouvelé

# 4. Installer le nouveau certificat
/opt/swift/bin/swift_cert_manager --install \
  --cert /opt/swift/certs/new-certificate.pem \
  --restart-alliance

# 5. Vérifier la reconnexion
sleep 30
curl http://swift-monitoring:8080/api/sessions
```

### Cas 2 – Redémarrage SWIFT Alliance Access

```bash
# Arrêt propre (attendre fin des traitements en cours – max 5 min)
systemctl stop swift-alliance
sleep 60

# Vérifier qu'aucun processus ne reste
ps aux | grep alliance

# Redémarrage
systemctl start swift-alliance

# Vérifier rétablissement (compter 2-3 minutes pour reconnexion FIN)
watch -n 10 'curl -s http://swift-monitoring:8080/api/sessions | jq ".fin_sessions_active"'
```

### Cas 3 – Redémarrage HSM

```bash
# Réinitialiser le pool de sessions HSM (sans redémarrage physique)
/opt/hsm/bin/hsm_admin --reset-pool

# Si insuffisant : redémarrer le service HSM
systemctl restart thales-hsm-service

# Test post-redémarrage
/opt/hsm/bin/hsm_test --sign-test
```

### Cas 4 – Incident réseau (coupure vers SWIFTNet)

1. Contacter l'équipe réseau (team-infra) pour investigation
2. Vérifier le lien de secours SWIFTNet (liaison backup)
3. Basculer sur le lien de secours si le lien principal ne revient pas

```bash
# Basculement sur lien de secours
/opt/swift/bin/swift_link_manager --switch-to-backup
```

### Cas 5 – Maintenance SWIFTNet SWIFT Inc. dépassée

1. Consulter le portail SWIFT pour les informations d'incident : `https://www.swift.com/about-us/swift-news/operational-status`
2. Ouvrir un ticket SWIFT support si la maintenance dépasse l'heure prévue
3. Contact SWIFT Support : `support@swift.com` ou `+32 2 655 3111`

## Gestion de la file d'attente après rétablissement

```bash
# Vérifier la taille de la file FIN
curl http://fin-processor:8080/api/queue/status | jq '.queue_size'

# Lancer le draining de la file (ordre chronologique)
curl -X POST http://fin-processor:8080/api/queue/drain \
  --data '{"mode": "chronological", "batch_size": 50}'

# Surveiller le traitement
watch -n 30 'curl -s http://fin-processor:8080/api/queue/status'
```

## Escalade

| Situation | Action |
| --- | --- |
| Coupure > 15 min en heures ouvrées | Escalader team-swift + team-infra en parallèle |
| Coupure > 30 min | Notifier le Responsable des Opérations SWIFT |
| Coupure > 1h | Déclarer incident majeur, activer cellule de crise |
| Problème certificat | Contacter immédiatement team-infra + SWIFT support |
| Problème HSM | Escalader team-infra + fournisseur HSM (Thales support) |

Contact SWIFT support 24/7 : `+32 2 655 3111` – référence contrat client banque

## Prévention

- Monitorer les dates d'expiration des certificats PKI (alerte à J-30 et J-7)
- Tester le mécanisme de basculement sur lien secondaire une fois par trimestre
- Vérifier les annonces de maintenance SWIFT Inc. chaque lundi matin
- Maintenir le firmware SWIFT Alliance à jour (procédure de mise à jour en dehors heures ouvrées)
- Archiver les logs HSM pour détection précoce de dégradation