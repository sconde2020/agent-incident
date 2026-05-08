"""
LLM-as-Judge : évaluation de la qualité des qualifications.

Pipeline :
  1. Charge tests/questions.json (11 questions couvrant 10 catégories).
  2. Appelle l'agent RÉEL (gpt-4o-mini, DB SQLite + RAG ChromaDB réels, sans mock).
  3. Appelle le JUGE (gpt-4o via OpenAI) avec la réponse + les éléments factuels.
  4. Parse le JSON du juge et calcule un score moyen par question.
  5. Assert score_moyen_question >= 3.0.
  6. Génère tests/reports/rapport_qualite.md à la fin de la session.

Lancer : pytest tests/quality/test_quality.py -v -s
"""
import pytest

from agent import Agent
from db.models import IncidentIn

from .judge import (
    QUESTIONS,
    SCORE_GLOBAL_CIBLE,
    SCORE_MIN_PAR_QUESTION,
    format_agent_line,
    judge_result,
)


def _run_and_judge(
    q: dict,
    agent: Agent,
    score_collector: list[dict],
    memory_context: str = "Aucun",
) -> dict:
    inc = IncidentIn(**q["incident"])
    result = agent.qualify(inc)
    scores = judge_result(q, result, memory_context=memory_context)
    avg = round((scores["pertinence"] + scores["fidelite"] + scores["coherence"]) / 3, 2)
    entry = {
        "id": q["id"],
        "categorie": q["categorie"],
        "question": q["question"][:80] + "...",
        **scores,
        "avg": avg,
    }
    score_collector.append(entry)
    print(f"\n{q['id']}")
    print(f"Question : {q['question']}")
    print(f"Agent    : {format_agent_line(result)}")
    print(
        f"Juge     : [P={scores['pertinence']} F={scores['fidelite']} "
        f"C={scores['coherence']} moy={avg:.2f}] {scores['justification']}"
    )
    return entry


class TestQualiteAgent:

    def test_q01_factuelle_swiftnet_down(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q01")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q01 factuelle: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q02_factuelle_pki_expiry(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q02")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q02 factuelle PKI: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q03_complexe_nostro_et_backlog(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q03")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q03 complexe: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q04_ambigue_description_vague(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q04")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q04 ambiguë: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q05_hors_sujet_imprimante(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q05")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q05 hors sujet: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q06_securite_hsm_acces_non_autorise(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q06")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q06 sécurité: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q07_piege_p1_auto_declare(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q07")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q07 piège: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q08_format_cutoff_batch_failure(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q08")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q08 format: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q09_memoire_second_incident_gpi(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q09")
        pre_inc = IncidentIn(**q["pre_incident"])
        pre_result = real_agent.qualify(pre_inc)
        memory_context = (
            f"Tour précédent sur gpi-tracker: priorité={pre_result.priority}, "
            f"équipe={pre_result.assigned_to}, confidence={pre_result.confidence_score:.2f}"
        )
        entry = _run_and_judge(q, real_agent, score_collector, memory_context=memory_context)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q09 mémoire: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q10_multi_tools_bic_validator(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q10")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q10 multi-tools: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_q11_bord_domaine_ups(self, real_agent: Agent, score_collector):
        q = next(x for x in QUESTIONS if x["id"] == "Q11")
        entry = _run_and_judge(q, real_agent, score_collector)
        assert entry["avg"] >= SCORE_MIN_PAR_QUESTION, (
            f"Q11 bord domaine: score {entry['avg']} < {SCORE_MIN_PAR_QUESTION}. "
            f"Juge: {entry['justification']}"
        )

    def test_score_global_moyen(self, score_collector):
        assert score_collector, "Aucun score collecté — les tests précédents ont-ils tous tourné ?"
        global_avg = round(sum(e["avg"] for e in score_collector) / len(score_collector), 2)
        print(f"\n{'='*50}")
        print(f"SCORE GLOBAL : {global_avg:.2f} / 5.0  (cible >= {SCORE_GLOBAL_CIBLE})")
        print(f"Questions evaluees : {len(score_collector)}")
        print(f"{'='*50}")
        assert global_avg >= SCORE_GLOBAL_CIBLE, (
            f"Score global {global_avg} < {SCORE_GLOBAL_CIBLE}. "
            f"Detail : " + ", ".join(f"{e['id']}={e['avg']}" for e in score_collector)
        )
