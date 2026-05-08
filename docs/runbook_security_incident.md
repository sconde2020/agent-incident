# Runbook — Incident de sécurité SWIFT (accès non autorisé, intrusion HSM)

**Type :** Sécurité  
**Services couverts :** swift-alliance, HSM, SWIFT Alliance Access  
**Équipe principale :** team-infra  
**Escalade sécurité :** team-security (RSSI, SOC)  
**Priorité typique :** P1 (intrusion HSM active) / P2 (tentatives échouées, aucune session établie)

---

## Symptômes couverts

- Tentatives de connexion répétées sur le HSM (Hardware Security Module) SWIFT
- Adresse IP source inconnue ou non répertoriée dans la whitelist
- Credentials inconnus ou comptes de service invalides utilisés
- Activité anormale sur SWIFT Alliance Access en dehors des heures de maintenance
- Alerte sécurité `AUTH_FAILURE_THRESHOLD_EXCEEDED` ou `UNKNOWN_IP_ACCESS`

---

## Étapes de réponse immédiate

### 1. Isoler l'adresse IP source
```bash
# Bloquer l'IP au niveau du firewall périmétrique
firewall-cmd --permanent --add-rich-rule='rule family=ipv4 source address="<IP_SUSPECTE>" drop'
firewall-cmd --reload
```

### 2. Verrouiller le compte compromis (si identifié)
```bash
# Désactiver le compte sur SWIFT Alliance Access
swift_admin --lock-account <USERNAME> --reason "security_incident"
```

### 3. Collecter les logs HSM pour analyse forensique
```bash
# Export des logs HSM des dernières 24h
hsm_audit_export --start "$(date -d '24 hours ago' +%Y-%m-%dT%H:%M:%S)" \
                 --end "$(date +%Y-%m-%dT%H:%M:%S)" \
                 --output /tmp/hsm_audit_$(date +%Y%m%d).log
```

### 4. Notifier le RSSI et le SOC
- **Délai max :** 15 minutes après détection
- Canal : `#security-incidents` (Slack) + email `rssi@bank.internal`
- Inclure : timestamp, IP source, nombre de tentatives, comptes ciblés

### 5. Vérifier l'intégrité des clés HSM
```bash
# Contrôle d'intégrité — aucune clé ne doit être absente ou modifiée
hsm_integrity_check --full --verify-signatures
```

### 6. Vérifier les sessions SWIFT actives
```bash
# S'assurer qu'aucune session SWIFT non autorisée n'est ouverte
swift_admin --list-sessions --filter status=ACTIVE
```

---

## Critères d'escalade P1

Escalader immédiatement à P1 si :
- Une session a été établie par l'IP suspecte
- Des clés HSM manquent ou ont été modifiées (intégrité check KO)
- Des messages SWIFT signés avec des clés compromises ont été émis
- L'attaque est toujours en cours après isolation de l'IP

---

## Notification réglementaire

Conformément aux exigences SWIFT CSP (Customer Security Programme) :
- Incident à signaler à SWIFT KYC-SA dans les 24h si intrusion confirmée
- Conserver les logs HSM pendant 5 ans minimum
- Documenter la timeline complète dans le post-mortem

---

## Références

- SWIFT Customer Security Controls Framework (CSCF) — Contrôle 6.1 (Operator Session Confidentiality)
- Runbook PKI/certificats : voir `runbook_swift_fin_indisponible.md` section "Cas 1 – Certificat PKI expiré"
- Contact RSSI : `rssi@bank.internal`
