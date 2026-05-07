# Rapport — Tests unitaires

**Date :** 2026-05-07  
**Projet :** Agent de qualification des incidents SWIFT  
**Commande :** `pytest tests/test_unitaires.py -v`  
**Résultat global :** ✅ 60 / 60 passed — 0.23 s

---

## Résumé par classe de test

| Classe | Tests | Résultat | Durée |
|--------|-------|----------|-------|
| `TestConversationMemory` | 11 | ✅ Pass | < 0.01 s |
| `TestSearchCMDB` | 3 | ✅ Pass | < 0.01 s |
| `TestSearchMonitoring` | 4 | ✅ Pass | < 0.01 s |
| `TestSearchIncidents` | 3 | ✅ Pass | < 0.01 s |
| `TestDetectDuplicate` | 5 | ✅ Pass | < 0.01 s |
| `TestDetectMajorIncident` | 5 | ✅ Pass | < 0.01 s |
| `TestUpdateIncident` | 3 | ✅ Pass | < 0.01 s |
| `TestClassify` | 6 | ✅ Pass | < 0.01 s |
| `TestRoute` | 5 | ✅ Pass | < 0.01 s |
| `TestCreateIncident` | 3 | ✅ Pass | < 0.01 s |
| `TestInputValidator` | 12 | ✅ Pass | < 0.01 s |
| **Total** | **60** | **✅ 100 %** | **0.23 s** |

---

## Détail par classe

### TestConversationMemory (11 tests)

Couvre le module `memory/store.py` — `ConversationMemory` et `MemoryEntry`.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_add_and_recall_basic` | `add()` + `get_recent()` renvoient l'entrée ajoutée |
| `test_len_tracks_size` | `__len__` reflète le nombre d'entrées |
| `test_to_context_contains_required_fields` | `to_context()` inclut tous les champs clés |
| `test_get_recent_with_k_limits_results` | `get_recent(k=2)` renvoie au plus 2 entrées |
| `test_max_memory_not_exceeded` | La deque n'excède jamais `max_size` |
| `test_eviction_is_fifo_oldest_dropped` | La plus ancienne entrée est effacée en premier |
| `test_newest_entry_always_present` | La dernière entrée ajoutée est toujours présente |
| `test_clear_empties_memory` | `clear()` vide complètement la mémoire |
| `test_clear_then_add_works` | `add()` fonctionne après `clear()` |
| `test_empty_memory_to_context_returns_empty_list` | `to_context()` renvoie `[]` quand vide |
| `test_empty_get_recent_returns_empty_list` | `get_recent()` renvoie `[]` quand vide |

---

### TestSearchCMDB (3 tests)

Couvre `tools/search_cmdb.py` — `SearchCMDB.execute()`.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_nominal_returns_service_data` | Retourne les données du service depuis la DB |
| `test_service_not_found_returns_error_dict` | Retourne `{"error": ...}` si service inconnu |
| `test_empty_name_no_crash` | Pas de crash sur un nom de service vide |

---

### TestSearchMonitoring (4 tests)

Couvre `tools/search_monitoring.py` — `SearchMonitoring.execute()`.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_nominal_returns_counts_and_alerts` | `alert_count` correct, liste d'alertes peuplée |
| `test_no_alerts_returns_zero_count` | `alert_count = 0` quand aucune alerte |
| `test_critical_alert_sets_flag_to_true` | `has_critical_alerts = True` si une alerte est critique |
| `test_mixed_severities_critical_wins` | `has_critical_alerts = True` dès qu'une alerte critique est présente |

---

### TestSearchIncidents (3 tests)

Couvre `tools/search_incidents.py` — `SearchIncidents.execute()`.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_nominal_returns_list` | Retourne la liste d'incidents similaires |
| `test_empty_result_no_crash` | `[]` si aucun incident similaire |
| `test_search_limit_forwarded_to_db` | Le paramètre `limit` est bien transmis à la DB |

---

### TestDetectDuplicate (5 tests)

Couvre `tools/detect_duplicate.py` — `DetectDuplicate.execute()` et `_filter_candidates()`.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_duplicate_detected_within_window` | Doublon détecté si l'incident est dans la fenêtre temporelle |
| `test_no_duplicate_when_incident_too_old` | Pas de doublon si l'incident est trop ancien |
| `test_empty_db_returns_no_duplicate` | `is_duplicate = False` si la DB est vide |
| `test_invalid_date_excluded_no_crash` | Une date malformée est ignorée sans crash |
| `test_candidates_list_populated` | La liste `candidates` contient les incidents récents |

---

### TestDetectMajorIncident (5 tests)

Couvre `tools/detect_major_incident.py` — `DetectMajorIncident.execute()` et `_scan_services()`.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_not_major_when_below_threshold` | `is_major_incident = False` sous le seuil |
| `test_major_detected_when_threshold_reached` | `is_major_incident = True` au seuil |
| `test_no_dependencies_only_one_db_call` | Sans dépendances, un seul appel DB |
| `test_related_incidents_are_deduplicated` | Les IDs dupliqués sont dédupliqués |
| `test_empty_db_returns_not_major` | Pas d'incident majeur si la DB est vide |

---

### TestUpdateIncident (3 tests)

Couvre `tools/update_incident.py` — `UpdateIncident.execute()`.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_nominal_returns_success` | `{"success": True}` en cas nominal |
| `test_db_called_with_correct_args` | La DB est appelée avec l'ID et la qualification corrects |
| `test_db_error_returns_failure_dict` | `{"success": False}` si la DB lève une exception |

---

### TestClassify (6 tests)

Couvre `tools/classify.py` — `Classify.execute()` et la logique de mapping LLM.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_nominal_returns_all_fields` | Tous les champs obligatoires sont présents dans le résultat |
| `test_all_priorities_accepted[P1..P4]` | Les 4 niveaux de priorité sont acceptés (paramétrisé) |
| `test_confidence_score_preserved` | Le `confidence_score` LLM est transmis sans altération |

---

### TestRoute (5 tests)

Couvre `tools/route.py` — `Route.execute()` et la matrice de routage.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_llm_suggestion_preferred_over_matrix` | La suggestion LLM prime sur la matrice locale |
| `test_matrix_used_when_no_llm_suggestion` | La matrice est utilisée si le LLM ne suggère rien |
| `test_unknown_service_defaults_to_team_ops` | Service inconnu → `team-ops` par défaut |
| `test_llm_suggestion_without_team_prefix_falls_back` | Suggestion LLM sans préfixe `team-` → fallback matrice |
| `test_known_payment_service_routes_correctly` | `payment-hub` → `team-payments` |

---

### TestCreateIncident (3 tests)

Couvre `tools/create_incident.py` — `CreateIncident.execute()`.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_nominal_returns_success_with_id` | L'ID de l'incident créé est retourné |
| `test_db_called_with_incident_data` | La DB reçoit les bonnes données |
| `test_db_error_returns_failure_dict` | `{"success": False}` si la DB lève une exception |

---

### TestInputValidator (12 tests)

Couvre `security/input_validator.py` — `validate_incident_input()`.

| Test | Ce qui est vérifié |
|------|--------------------|
| `test_valid_payload_accepted` | Un payload valide passe sans erreur |
| `test_prompt_injection_in_title_blocked` | `Ignore all previous` dans le titre → rejet |
| `test_prompt_injection_inst_tag_in_description_blocked` | Tag `<INST>` dans la description → rejet |
| `test_iban_in_description_blocked` | IBAN (`FR76...`) dans la description → rejet |
| `test_api_key_in_description_blocked` | Clé API (`sk-...`) dans la description → rejet |
| `test_invalid_incident_id_format_blocked` | ID hors format `INCxxxxxxx` → rejet |
| `test_sql_injection_in_service_blocked` | SQL injection dans le service → rejet |
| `test_description_too_short_blocked` | Description < 10 caractères → rejet |
| `test_title_too_short_blocked` | Titre < 5 caractères → rejet |
| `test_missing_required_field_title_blocked` | Titre absent → rejet |
| `test_invalid_priority_blocked` | Priorité hors `P1–P4` → rejet |
| `test_none_id_accepted` | `id = null` accepté (généré automatiquement) |

---

## Propriétés des tests

| Propriété | Valeur |
|-----------|--------|
| Appels LLM réels | 0 — tous mocké via `unittest.mock.MagicMock` |
| Appels DB réels | 0 — tous mocké |
| Appels réseau | 0 |
| Fichiers temporaires | 0 |
| Dépendances externes requises | `pytest`, `pydantic` |
| Compatibilité | Python 3.12+ |
| Durée totale | 0.23 s |

---

## Couverture fonctionnelle

| Module | Couvert |
|--------|---------|
| `memory/store.py` | ✅ Complet |
| `tools/search_cmdb.py` | ✅ Nominal + erreurs |
| `tools/search_monitoring.py` | ✅ Nominal + cas limites |
| `tools/search_incidents.py` | ✅ Nominal + limite |
| `tools/detect_duplicate.py` | ✅ Fenêtre temporelle + date invalide |
| `tools/detect_major_incident.py` | ✅ Seuil + déduplication |
| `tools/update_incident.py` | ✅ Nominal + erreur DB |
| `tools/classify.py` | ✅ Toutes priorités + score |
| `tools/route.py` | ✅ LLM vs matrice + fallback |
| `tools/create_incident.py` | ✅ Nominal + erreur DB |
| `security/input_validator.py` | ✅ Injection + PII + format |
