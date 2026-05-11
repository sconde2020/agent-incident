"""
test_performance.py — 25 × POST /create + POST /qualify → métriques dans demo.md
Usage : python test_performance.py [--url http://localhost:8080]
"""
import argparse
import json
import pathlib
import re
import sys
import time

import requests
from dotenv import dotenv_values

# ── Couleurs ANSI ──────────────────────────────────────────────────────────────
RED = "\033[0;31m"; GREEN = "\033[0;32m"; YELLOW = "\033[1;33m"
CYAN = "\033[0;36m"; BOLD = "\033[1m"; NC = "\033[0m"

ROOT = pathlib.Path(__file__).parent
DEMO_MD = ROOT / "demo.md"

# ── 25 tickets — 1 service unique par ticket (évite la détection de doublons) ──
# Services 1-18 : présents dans le CMDB (appel LLM + RAG complet)
# Services 19-25 : hors corpus (teste la robustesse sur services inconnus)
TICKETS = [
    {
        "title": "SWIFTNet FIN indisponible – aucune session active sur swift-gateway",
        "description": (
            "Aucune session FIN active depuis 08h10. Alerte SWIFTNet FIN connectivity lost "
            "déclenchée. Tous les messages MT103 et MT202 sortants sont bloqués en file "
            "fin-processor. SWIFT Alliance Access retourne SESSION_TIMEOUT. "
            "Tableau de bord : fin_sessions_active = 0."
        ),
        "service": "swift-gateway",
    },
    {
        "title": "File MT103 bloquée – 1200 messages en attente dans fin-processor",
        "description": (
            "La file de traitement MT103 de fin-processor accumule 1 200 messages depuis 09h30. "
            "Le workers pool ne consomme plus la file. Latence dépassant 45 minutes. "
            "Les paiements clients urgents sont bloqués en attente de traitement."
        ),
        "service": "fin-processor",
    },
    {
        "title": "payment-hub – tous les paiements sortants bloqués en contrôle sanctions",
        "description": (
            "Le payment-hub bloque tous les paiements sortants en attente de validation par "
            "sanctions-screening depuis 09h45. Le service ne répond plus. "
            "File de 890 paiements en statut PENDING_SANCTIONS depuis 20 minutes."
        ),
        "service": "payment-hub",
    },
    {
        "title": "sanctions-screening – listes OFAC non mises à jour depuis 72 heures",
        "description": (
            "Le job automatique de mise à jour des listes OFAC SDN n'a pas tourné depuis vendredi "
            "08h00. Les listes utilisées datent de 72 heures. Non-conformité réglementaire "
            "potentielle détectée par l'équipe Compliance. Notification urgente envoyée au RCCI."
        ),
        "service": "sanctions-screening",
    },
    {
        "title": "Écart nostro 180K EUR Deutsche Bank – MT940 non réconciliés",
        "description": (
            "La réconciliation EOD du compte nostro Deutsche Bank DEUTDEDB présente un écart de "
            "180 000 EUR non réconcilié depuis le traitement de 16h00. 350 messages MT940 restent "
            "en attente de parsing dans fin-processor. La clôture comptable est bloquée."
        ),
        "service": "nostro-reconciliation",
    },
    {
        "title": "Batch EOD cut-off 17h00 échoué – DB_CONNECTION_FAILED sur swift-messages-db",
        "description": (
            "Le cut-off-manager a échoué à déclencher le batch de fin de journée à 17h05 avec "
            "DB_CONNECTION_FAILED vers swift-messages-db. 280 paiements SWIFT en statut QUEUED "
            "non émis avant le cut-off officiel. Relance manuelle en échec avec la même erreur."
        ),
        "service": "cut-off-manager",
    },
    {
        "title": "gpi-tracker – statuts UETR bloqués en ACSP depuis 2 heures",
        "description": (
            "Le gpi-tracker n'émet plus de mises à jour de statut UETR depuis 11h30. 45 paiements "
            "gpi restent en statut ACSP sans transition vers ACCC ou RJCT. Les clients en attente "
            "de confirmation signalent des incidents au service client."
        ),
        "service": "gpi-tracker",
    },
    {
        "title": "Synchronisation BIC Directory échouée – répertoire BIC obsolète depuis 14 jours",
        "description": (
            "Le job hebdomadaire de synchronisation du BIC Directory a échoué vendredi à 02h00. "
            "Erreur SYNC_TIMEOUT lors de la connexion au serveur SWIFT officiel. Le répertoire "
            "local date de 14 jours. Risque de rejets sur les BIC récemment créés ou modifiés."
        ),
        "service": "bic-validator",
    },
    {
        "title": "payment-router – routage SEPA SCT échoué, CORRESPONDENT_NOT_FOUND Belfius",
        "description": (
            "payment-router retourne CORRESPONDENT_NOT_FOUND sur les paiements SEPA vers la Belgique "
            "depuis 10h00. Le correspondant Belfius GEBABEBB a disparu du référentiel "
            "correspondent-service. 45 virements SEPA en attente de routage non exécutés ce matin."
        ),
        "service": "payment-router",
    },
    {
        "title": "RMA expiré avec Citibank CITIUS33 – paiements USD bloqués depuis 08h00",
        "description": (
            "Le RMA avec Citibank CITIUS33 a expiré durant le weekend. Les paiements USD en "
            "direction de Citibank sont bloqués avec erreur RMA_EXPIRED depuis 08h00 lundi. "
            "Impact majeur sur les paiements internationaux USD vers les États-Unis."
        ),
        "service": "correspondent-service",
    },
    {
        "title": "Parsing MT202COV échoué – champ 58A manquant sur tous les messages entrants",
        "description": (
            "mt-parser lève FIELD_58A_MISSING sur tous les messages MT202COV entrants depuis 12h15. "
            "78 messages MT202COV non parsés bloqués en file d'erreur. Les paiements de couverture "
            "sont impactés. Possible régression introduite lors du déploiement de 06h00."
        ),
        "service": "mt-parser",
    },
    {
        "title": "SWIFT Alliance Access – échec authentification PKI, toutes sessions FIN fermées",
        "description": (
            "SWIFT Alliance Access ne parvient plus à s'authentifier auprès de SWIFTNet depuis 07h50. "
            "Erreur PKI_AUTH_FAILED sur toutes les tentatives. Toutes les sessions FIN ont été "
            "fermées par SWIFTNet. Aucun message SWIFT ne peut être émis ni reçu."
        ),
        "service": "swift-alliance",
    },
    {
        "title": "payments-api inaccessible – erreurs HTTP 503 sur toutes les transactions CB",
        "description": (
            "Le service payments-api retourne des erreurs 503 sur toutes les transactions par carte "
            "bancaire depuis 14h30. Environ 2 000 utilisateurs impactés. Les logs montrent des "
            "connexions refusées vers payments-db. Taux d'échec transaction : 100% depuis 14h32."
        ),
        "service": "payments-api",
    },
    {
        "title": "auth-service – échec validation JWT sur 30 pourcent des logins depuis 11h55",
        "description": (
            "Le service auth-service retourne des erreurs JWT_VALIDATION_FAILED sur environ 30% des "
            "tentatives de connexion depuis 11h55. Les logs indiquent des NullPointerException dans "
            "le module de vérification de signature RSA. Impact sur payments-api et orders-api."
        ),
        "service": "auth-service",
    },
    {
        "title": "liquidity-manager – seuil nostro JPMorgan dépassé, alerte trésorerie critique",
        "description": (
            "Le service liquidity-manager a déclenché une alerte critique : le compte nostro JPMorgan "
            "CHASGB2L est passé sous le seuil minimal de 1 million EUR. Solde actuel de 450 000 EUR. "
            "Les paiements vers les USA sont à risque. Intervention desk Treasury requise en urgence."
        ),
        "service": "liquidity-manager",
    },
    {
        "title": "orders-api – latence supérieure à 8 s, timeouts B2B clients depuis 09h10",
        "description": (
            "Le service orders-api répond en plus de 8 secondes depuis 09h10. Le SLA de 2 secondes "
            "est dépassé. Les clients B2B signalent des timeouts sur leurs intégrations API. Les logs "
            "montrent des requêtes lentes sur orders-db avec des full table scans détectés."
        ),
        "service": "orders-api",
    },
    {
        "title": "catalog-service – pool connexions PostgreSQL saturé, requêtes refusées",
        "description": (
            "Le pool de connexions PostgreSQL du service catalogue est saturé depuis 13h20. "
            "Les requêtes sont refusées avec l'erreur 'too many clients already'. "
            "Les pages produit ne se chargent plus. Environ 500 clients impactés sur le site."
        ),
        "service": "catalog-service",
    },
    {
        "title": "notification-service – workers CPU 100%, files push notifications à l'arrêt",
        "description": (
            "Les workers du service notification sont à 100% CPU depuis 30 minutes. "
            "La file de messages s'accumule, les notifications push ne partent plus. "
            "Les clients ne reçoivent plus les confirmations de commande et de paiement."
        ),
        "service": "notification-service",
    },
    # ── Hors corpus CMDB — robustesse sur services inconnus ───────────────────
    {
        "title": "core-banking – virements internes en timeout, transactions suspendues depuis 10h",
        "description": (
            "Le système core-banking ne répond plus aux demandes de virement interne depuis 10h00. "
            "Les transactions retournent CORE_TIMEOUT après 30 secondes. Les agences ne peuvent "
            "plus exécuter d'opérations bancaires. Aucune équipe de support clairement identifiée."
        ),
        "service": "core-banking",
    },
    {
        "title": "portail-client – portail web inaccessible, erreur 502 Bad Gateway depuis 09h30",
        "description": (
            "Le portail client retourne une erreur 502 Bad Gateway sur toutes les pages depuis 09h30. "
            "Les clients ne peuvent plus consulter leurs soldes ni initier de virements en ligne. "
            "Environ 15 000 clients potentiellement impactés. Aucun runbook référencé."
        ),
        "service": "portail-client",
    },
    {
        "title": "reporting-service – rapports EOD non générés, clôture comptable bloquée",
        "description": (
            "Le service reporting-service n'a pas généré les rapports de fin de journée attendus "
            "à 18h00. La clôture comptable est bloquée. Les équipes Finance et Compliance attendent "
            "les récapitulatifs de transactions. Service non documenté dans la base de connaissances."
        ),
        "service": "reporting-service",
    },
    {
        "title": "alerting-service – alertes de liquidité non transmises au desk Treasury",
        "description": (
            "L'alerting-service n'a pas transmis les alertes de seuil de liquidité depuis 08h00. "
            "Le desk Treasury n'a reçu aucune notification malgré plusieurs dépassements de seuil "
            "détectés par liquidity-manager. Risque de découvert non détecté sur comptes nostro."
        ),
        "service": "alerting-service",
    },
    {
        "title": "fx-rates-feed – flux taux de change interrompu depuis 15 minutes",
        "description": (
            "Le service fx-rates-feed ne publie plus de taux de change depuis 11h22. "
            "Les applications consommatrices utilisent les derniers taux en cache, désormais périmés "
            "de plus de 15 minutes. Impact potentiel sur les cotations et la valorisation des portefeuilles."
        ),
        "service": "fx-rates-feed",
    },
    {
        "title": "trade-finance-engine – lettres de crédit bloquées, DOCUMENT_VALIDATION_FAILED",
        "description": (
            "Le service trade-finance-engine retourne DOCUMENT_VALIDATION_FAILED sur toutes les "
            "demandes de lettres de crédit documentaires depuis 10h15. Environ 40 dossiers LC en "
            "attente. Les correspondants bancaires signalent des délais inhabituels."
        ),
        "service": "trade-finance-engine",
    },
    {
        "title": "infrastructure-monitoring – service hors ligne, alertes ops silencieuses",
        "description": (
            "Le service infrastructure-monitoring ne répond plus depuis 07h45. Aucune alerte "
            "d'infrastructure n'est émise depuis lors. Les équipes ops sont aveugles sur l'état "
            "des serveurs de production. Risque de non-détection d'incidents critiques en cours."
        ),
        "service": "infrastructure-monitoring",
    },
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_api_key() -> str:
    env = dotenv_values(ROOT / ".env")
    key = env.get("API_KEY", "").strip()
    if not key:
        print(f"{RED}❌  API_KEY absent dans .env{NC}", file=sys.stderr)
        sys.exit(1)
    return key


def make_session(api_key: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    return s


def health_check(session: requests.Session, base_url: str) -> None:
    try:
        r = session.get(f"{base_url}/health", timeout=5)
        r.raise_for_status()
    except Exception as exc:
        print(f"{RED}❌  Serveur inaccessible ({base_url}/health) : {exc}{NC}", file=sys.stderr)
        print(f"    Démarrez le serveur : {CYAN}python main.py serve --port 8080{NC}", file=sys.stderr)
        sys.exit(1)


# ── Résultat d'un run ──────────────────────────────────────────────────────────

class RunResult:
    def __init__(self, idx: int, service: str):
        self.idx = idx
        self.service = service
        self.inc_id: str = "—"
        self.create_code: int = 0
        self.qualify_code: int = 0
        self.latency_ms: int = 0

    @property
    def create_ok(self) -> bool:
        return 200 <= self.create_code < 300

    @property
    def qualify_ok(self) -> bool:
        return self.qualify_code == 200

    @property
    def qualify_skipped(self) -> bool:
        return self.inc_id == "—"


# ── Boucle principale ──────────────────────────────────────────────────────────

def run_all(session: requests.Session, base_url: str) -> list[RunResult]:
    header = f"{'#':<4} {'ID':<12} {'Service':<30} {'CREATE':>8} {'QUALIFY':>8} {'Latence':>10}"
    print(f"{BOLD}{header}{NC}")
    print("─" * 76)

    results: list[RunResult] = []

    for i, ticket in enumerate(TICKETS):
        res = RunResult(idx=i + 1, service=ticket["service"])

        # POST /create
        try:
            r = session.post(f"{base_url}/create", json=ticket, timeout=30)
            res.create_code = r.status_code
            if res.create_ok:
                res.inc_id = r.json().get("id", "—")
        except requests.RequestException as exc:
            res.create_code = 0
            print(f"  {RED}create error: {exc}{NC}", file=sys.stderr)

        # POST /qualify
        if res.create_ok and res.inc_id != "—":
            t0 = time.monotonic()
            try:
                r = session.post(
                    f"{base_url}/qualify",
                    json={"id": res.inc_id},
                    timeout=120,
                )
                res.qualify_code = r.status_code
            except requests.RequestException as exc:
                res.qualify_code = 0
                print(f"  {RED}qualify error: {exc}{NC}", file=sys.stderr)
            res.latency_ms = int((time.monotonic() - t0) * 1000)

        # Affichage
        c_color = GREEN if res.create_ok else RED
        q_color = (
            GREEN if res.qualify_ok
            else YELLOW if res.qualify_skipped
            else RED
        )
        q_disp = "skip" if res.qualify_skipped else str(res.qualify_code)
        print(
            f"{res.idx:<4} {res.inc_id:<12} {res.service:<30} "
            f"{c_color}{res.create_code:>8}{NC} "
            f"{q_color}{q_disp:>8}{NC} "
            f"{res.latency_ms:>9} ms"
        )

        results.append(res)

    return results


# ── Mise à jour demo.md ────────────────────────────────────────────────────────

def _metrics_section(run_date: str, results: list[RunResult], m: dict) -> str:
    # Tableau par run
    run_rows = []
    for res in results:
        c_icon = "✅" if res.create_ok else "❌"
        q_icon = "✅" if res.qualify_ok else ("⏭" if res.qualify_skipped else "❌")
        q_code = "skip" if res.qualify_skipped else str(res.qualify_code)
        run_rows.append(
            f"| {res.idx} | `{res.inc_id}` | `{res.service}` "
            f"| {c_icon} `{res.create_code}` | {q_icon} `{q_code}` | {res.latency_ms} ms |"
        )

    total = m["qualifications_total"]
    ok = m["qualifications_success"]
    errors = m["errors_total"]
    rate = f"{ok / total * 100:.1f}%" if total else "—"
    tok = m["tokens"]
    avg_ms = m["avg_latency_ms"]
    rag_ms = m["latency_breakdown"]["avg_rag_ms"]
    llm_ms = m["latency_breakdown"]["avg_llm_ms"]
    cost = m["estimated_cost_usd"]
    model = m["model"]

    metrics_table = "\n".join([
        "| Métrique | Valeur |",
        "|---|---|",
        f"| Qualifications (total) | {total} |",
        f"| Succès | {ok} |",
        f"| Erreurs | {errors} |",
        f"| Taux de succès | {rate} |",
        f"| Latence moyenne end-to-end | {avg_ms} ms · {avg_ms / 1000:.2f} s |",
        f"| dont RAG (moy.) | {rag_ms} ms · {rag_ms / 1000:.2f} s |",
        f"| dont LLM (moy.) | {llm_ms} ms · {llm_ms / 1000:.2f} s |",
        f"| Tokens prompt (total) | {tok['prompt_total']:,} |",
        f"| Tokens completion (total) | {tok['completion_total']:,} |",
        f"| Tokens total | {tok['total']:,} |",
        f"| Coût estimé | ${cost:.6f} |",
        f"| Modèle | `{model}` |",
    ])

    return (
        "\n\n---\n\n"
        f"## Métriques de performance — {run_date}\n\n"
        "> Résultats de `test_performance.py` : "
        "25 × `POST /create` + `POST /qualify`, données `/metrics`\n\n"
        "### Résultats par run\n\n"
        "| # | ID | Service | /create | /qualify | Latence |\n"
        "|---|----|---------|---------|----|---|\n"
        + "\n".join(run_rows)
        + "\n\n### Agrégats `/metrics`\n\n"
        + metrics_table
        + "\n"
    )


def update_demo_md(results: list[RunResult], metrics: dict) -> None:
    from datetime import datetime
    run_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    section = _metrics_section(run_date, results, metrics)

    content = DEMO_MD.read_text(encoding="utf-8")
    marker = "\n---\n\n## Métriques de performance"
    pos = content.find(marker)
    if pos != -1:
        content = content[:pos] + section
    else:
        content = content.rstrip() + section

    DEMO_MD.write_text(content, encoding="utf-8")


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Test de performance — Agent SWIFT")
    parser.add_argument("--url", default="http://localhost:8080", metavar="URL")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    api_key = load_api_key()
    session = make_session(api_key)

    print(f"{BOLD}=== Test de performance — Agent de qualification SWIFT ==={NC}")
    print(f"  URL     : {CYAN}{base_url}{NC}")
    print(f"  API key : {CYAN}{api_key[:6]}…{NC}")
    print(f"  Tickets : {CYAN}{len(TICKETS)}{NC}")
    print()

    health_check(session, base_url)
    results = run_all(session, base_url)

    ok_c  = sum(1 for r in results if r.create_ok)
    ok_q  = sum(1 for r in results if r.qualify_ok)
    skip  = sum(1 for r in results if r.qualify_skipped)
    err_c = len(results) - ok_c
    err_q = len(results) - ok_q - skip

    print()
    print(f"  Créations     : {GREEN}{ok_c} ✅{NC}  {RED}{err_c} ❌{NC}")
    print(f"  Qualifications: {GREEN}{ok_q} ✅{NC}  {RED}{err_q} ❌{NC}  {YELLOW}{skip} ⏭{NC}")
    print()

    # GET /metrics
    print(f"{CYAN}▶  GET /metrics…{NC}")
    try:
        r = session.get(f"{base_url}/metrics", timeout=10)
        r.raise_for_status()
        metrics = r.json()
    except Exception as exc:
        print(f"{RED}❌  /metrics : {exc}{NC}", file=sys.stderr)
        sys.exit(1)
    print(f"{GREEN}✅  Métriques reçues{NC}")
    print()

    # demo.md
    print(f"{CYAN}▶  Mise à jour de demo.md…{NC}")
    update_demo_md(results, metrics)
    print(f"{GREEN}✅  demo.md mis à jour{NC}")
    print()
    print(f"{GREEN}{BOLD}✅  Test terminé. Consultez demo.md (section Métriques de performance).{NC}")


if __name__ == "__main__":
    main()
