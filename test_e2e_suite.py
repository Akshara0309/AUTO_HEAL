"""
AutoHeal AI - Comprehensive End-to-End Test Suite
Tests all 6 core evaluation scenarios:
  TEST 1: Normal healthy system
  TEST 2: API failure -> diagnose -> sandbox -> repair -> verify -> resolved
  TEST 3: Database failure -> diagnose -> repair -> verify
  TEST 4: Repair fails -> escalation (Pre-flight failure + Invariant failure)
  TEST 5: High-risk repair -> autonomous action blocked -> human approval
  TEST 6: Similar historical incident -> incident memory used
"""

import sys
import json
import time
from pathlib import Path

# Safe console encoding for Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sandbox_app import SandboxApp, get_default_app, LOG_FILE
from fault_simulator import trigger_failure, reset_all_failures
from incident_manager import IncidentManager, IncidentStatus, IncidentSeverity
from monitor import HealthMonitor
from hypothesis_engine import HypothesisTestingEngine, SafeDiagnosticRunner
from risk_engine import RiskAssessmentEngine, RiskLevel, RiskDecision
from repair_lab import RepairLab
from recovery_verifier import RecoveryVerificationEngine
from incident_memory import IncidentMemory
from autoheal_orchestrator import AutoHealOrchestrator
from incident_copilot import IncidentCopilot


def run_full_e2e_test_suite():
    print("=" * 80)
    print("🚀 AUTOHEAL AI - FULL END-TO-END SYSTEM VERIFICATION SUITE")
    print("=" * 80)

    # Ensure clean isolated test files
    test_incidents_file = Path("logs/test_incidents.json")
    if test_incidents_file.exists():
        try:
            test_incidents_file.unlink()
        except Exception:
            pass
    test_db_file = Path("logs/test_memory.db")
    if test_db_file.exists():
        try:
            test_db_file.unlink()
        except Exception:
            pass

    # Initialize isolated components for end-to-end testing
    app = SandboxApp()
    im = IncidentManager(persistence_file=test_incidents_file)
    mon = HealthMonitor(app=app, incident_manager=im)
    hyp_engine = HypothesisTestingEngine(app=app)
    risk_engine = RiskAssessmentEngine()
    lab = RepairLab()
    verifier = RecoveryVerificationEngine(app=app)
    memory = IncidentMemory(db_path="logs/test_memory.db", json_backup="logs/test_memory.json")
    copilot = IncidentCopilot(incident_memory=memory)

    orchestrator = AutoHealOrchestrator(
        app=app,
        incident_manager=im,
        monitor=mon,
        hypothesis_engine=hyp_engine,
        risk_engine=risk_engine,
        repair_lab=lab,
        recovery_verifier=verifier,
        incident_memory=memory
    )

    # Reset any previous state
    reset_all_failures(app=app)

    # ========================================================================
    # TEST 1: NORMAL HEALTHY SYSTEM
    # ========================================================================
    print("\n" + "#" * 70)
    print("▶️ TEST 1: NORMAL HEALTHY SYSTEM BASELINE VERIFICATION")
    print("#" * 70)

    # 1. Verify subsystem states
    status = app.get_status()
    health = app.get_health()
    print(f"  • Service status:    {status['subsystems']['service']} (running)")
    print(f"  • Database status:   {status['subsystems']['database']} (connected)")
    print(f"  • Configuration:     {status['subsystems']['config']} (valid)")
    print(f"  • Error rate:        {health['metrics']['error_rate_pct']}% (0.0%)")
    print(f"  • Response latency:  {health['metrics']['latency_ms']}ms (< 250ms)")
    assert status['subsystems']['service'] == "running"
    assert status['subsystems']['database'] == "connected"
    assert health['status'] == "UP"
    assert health['http_code'] == 200

    # 2. Verify HealthMonitor inspection
    scan = mon.inspect_now()
    print(f"  • Health inspection: {'HEALTHY' if scan['healthy'] else 'UNHEALTHY'}")
    assert scan['healthy'] is True
    assert len(im.get_active_incidents()) == 0

    # 3. Verify Live Canary Endpoint probe
    orders = app.handle_api_request("/api/orders", method="GET")
    print(f"  • Canary probe:      HTTP {orders['http_code']} ({orders['data']['count']} records retrieved)")
    assert orders['ok'] is True
    assert orders['http_code'] == 200
    assert orders['data']['count'] == 4

    print("  ✅ TEST 1 PASSED: Normal healthy system verified across all invariants.\n")

    # ========================================================================
    # TEST 2: API FAILURE -> DIAGNOSE -> SANDBOX -> REPAIR -> VERIFY -> RESOLVED
    # ========================================================================
    print("#" * 70)
    print("▶️ TEST 2: API FAILURE AUTONOMOUS RECOVERY WORKFLOW")
    print("#" * 70)

    # 1. Trigger API Failure
    print("  • Injecting API_DOWN fault into application...")
    trigger_failure("API_DOWN", app=app)
    assert app.faults["api_service_failure"] is True
    assert app.service_status == "down"

    # Verify detection flags outage
    scan = mon.inspect_now()
    active_incs = im.get_active_incidents()
    print(f"  • Incident detected: {active_incs[-1].id} ({active_incs[-1].failure_type})")
    assert len(active_incs) > 0
    assert active_incs[-1].failure_type == "API_DOWN"

    # 2. Run full autonomous autoheal cycle
    events_captured = []
    def record_event(stage, entry):
        events_captured.append(stage)

    rep2 = orchestrator.run_autoheal_cycle(fault_type="API_DOWN", event_callback=record_event)
    print(f"  • AutoHeal cycle final status: {rep2['final_status']}")
    print(f"  • Event stream: {' → '.join(rep2['event_stream'])}")

    # Verify pipeline stages executed
    expected_stages = [
        "DETECTED", "INVESTIGATING", "HYPOTHESIS_GENERATION", "HYPOTHESIS_TESTING",
        "DIAGNOSED", "REPAIR_PROPOSED", "RISK_ASSESSED", "SANDBOX_VALIDATED",
        "HEALING", "VERIFYING", "RESOLVED"
    ]
    for stg in expected_stages:
        assert stg in rep2['event_stream'], f"Missing required pipeline stage '{stg}'"

    # Verify AI reasoning / diagnosis
    winning_hyp = rep2['hyp_eval']['winning_hypothesis']
    print(f"  • Root Cause Identified: {winning_hyp['description']} (Confidence: {winning_hyp['confidence']})")
    print(f"  • Proposed Repair:       {rep2['validation_report']['repair']}")
    assert winning_hyp['candidate_fix'] == "restart_service"
    assert winning_hyp['confidence'] >= 0.90

    # Verify Risk calculation
    risk2 = rep2['risk_assessment']
    print(f"  • Evaluated Risk Score:  {risk2['risk_score']}/100 ({risk2['risk_level']}) -> Decision: {risk2['decision']}")
    assert risk2['risk_level'] == "LOW"
    assert risk2['risk_score'] <= 30
    assert risk2['decision'] == "AUTO_EXECUTE"

    # Verify Pre-flight Sandbox validation
    val2 = rep2['validation_report']
    print(f"  • Repair Lab Sandbox:    {val2['sandbox_status']} (Health: {val2['health_check']}, Canary: {val2['functional_test']})")
    assert val2['sandbox_status'] == "PASSED"

    # Verify Recovery Verification
    ver2 = rep2['verification_report']
    print(f"  • Invariant Verification: {'PROVEN' if ver2['recovered'] else 'FAILED'} (6/6 checks passed)")
    assert ver2['recovered'] is True
    assert len(ver2['checks']) == 6
    for chk in ver2['checks']:
        assert chk['passed'] is True, f"Check failed: {chk['name']}"

    assert rep2['final_status'] == "RESOLVED"
    assert rep2['recovered'] is True

    # Verify saved to Incident Memory
    history2 = memory.get_all_history()
    assert len(history2) >= 1
    assert history2[0]['failure_type'] == "API_DOWN"
    assert history2[0]['success'] == 1

    print("  ✅ TEST 2 PASSED: API Failure fully diagnosed, sandbox validated, auto-repaired, and verified resolved.\n")
    reset_all_failures(app=app)

    # ========================================================================
    # TEST 3: DATABASE FAILURE -> DIAGNOSE -> REPAIR -> VERIFY
    # ========================================================================
    print("#" * 70)
    print("▶️ TEST 3: DATABASE FAILURE GATED RECOVERY WORKFLOW")
    print("#" * 70)

    # 1. Trigger Database Down
    trigger_failure("DATABASE_DOWN", app=app)
    assert app.db.connected is False

    # 2. Run AutoHeal cycle (High risk requires human approval)
    rep3 = orchestrator.run_autoheal_cycle(fault_type="DATABASE_DOWN")
    print(f"  • Initial cycle result:  {rep3['final_status']} (Expected ESCALATED for approval)")
    assert rep3['final_status'] == "ESCALATED"

    # Verify AI Diagnosis
    win3 = rep3['hyp_eval']['winning_hypothesis']
    print(f"  • Root Cause Identified: {win3['description']} (Candidate Fix: {win3['candidate_fix']})")
    assert win3['candidate_fix'] == "repair_database"

    # Verify Risk calculation
    risk3 = rep3['risk_assessment']
    print(f"  • Risk Score:            {risk3['risk_score']}/100 ({risk3['risk_level']}) -> Mandates Approval")
    assert risk3['risk_score'] > 60
    assert risk3['risk_level'] == "HIGH"
    assert risk3['decision'] == "REQUIRE_APPROVAL"

    # Verify Sandbox validated before pausing
    assert rep3['validation_report']['sandbox_status'] == "PASSED"

    # 3. Simulate Operator Approval
    inc3_id = rep3['incident_id']
    print(f"  • Operator approving repair for incident: {inc3_id}...")
    appr3 = orchestrator.approve_and_heal(inc3_id, approver="Hackathon Judge/Admin")
    print(f"  • Post-approval status:  {appr3['final_status']} (Recovered: {appr3['recovered']})")
    assert appr3['final_status'] == "RESOLVED"
    assert appr3['recovered'] is True
    assert app.db.connected is True

    # Verify Audit log
    audit_trail = memory.get_approval_audit_trail()
    assert len(audit_trail) >= 1
    assert audit_trail[0]['decision'] == "APPROVED"
    assert audit_trail[0]['incident_id'] == inc3_id

    print("  ✅ TEST 3 PASSED: Database failure diagnosed, high risk paused for approval, approved, repaired, and verified.\n")
    reset_all_failures(app=app)

    # ========================================================================
    # TEST 4: REPAIR FAILS -> ESCALATION
    # ========================================================================
    print("#" * 70)
    print("▶️ TEST 4: REPAIR FAILS -> ESCALATION (SAFETY GUARANTEE)")
    print("#" * 70)

    # Scenario 4A: Pre-flight Repair Lab validation fails for ineffective repair
    print("  --- [4A] Testing Sandbox Pre-Flight Failure Protection ---")
    trigger_failure("DATABASE_DOWN", app=app)
    # Validate with an incorrect fix (e.g. attempting to restart service when DB pool is down)
    ineffective_val = lab.validate_repair(repair="restart_service", fault_type="DATABASE_DOWN", live_app=app)
    print(f"  • Pre-flight result for ineffective fix: {ineffective_val['sandbox_status']}")
    print(f"  • Summary: {ineffective_val['validation_summary']}")
    assert ineffective_val['sandbox_status'] == "FAILED"
    assert ineffective_val['functional_test'] is False

    # Scenario 4B: Post-repair recovery verification fails to satisfy invariants
    print("\n  --- [4B] Testing Recovery Invariant Failure Escalation ---")
    # Take snapshot while broken
    broken_snapshot = {
        "service_status": "running",
        "health_status": "DOWN",
        "database_status": "disconnected",
        "error_rate_pct": 70.0,
        "latency_ms": 22.0,
        "active_faults": ["database_connection_failure"]
    }
    # Verify against app that has NOT recovered
    failed_verification = verifier.verify_recovery(
        before_snapshot=broken_snapshot,
        target_fault_type="DATABASE_DOWN",
        repair_action="repair_database",
        app=app # app is still in failure state
    )
    print(f"  • Invariant verification: {'RECOVERED' if failed_verification['recovered'] else 'FAILED'}")
    print(f"  • Summary: {failed_verification['verification_summary']}")
    assert failed_verification['recovered'] is False

    # Verify escalation handling in IncidentManager
    failed_inc = im.create_incident(
        service="database",
        failure_type="DATABASE_DOWN",
        severity=IncidentSeverity.CRITICAL.value,
        description="Database failure for escalation test"
    )
    im.escalate_incident(failed_inc.id, failed_verification['verification_summary'])
    assert failed_inc.status == IncidentStatus.ESCALATED.value

    # Store failed recovery into memory
    memory.save_incident(
        incident_id=failed_inc.id,
        failure_type=failed_inc.failure_type,
        root_cause="Database connection pool timeout",
        evidence=["Connection timed out to postgresql-primary:5432"],
        selected_repair="repair_database",
        risk_score=63,
        sandbox_result="FAILED",
        recovery_result=failed_verification['verification_summary'],
        recovery_time=1.2,
        success=False
    )
    history_failed = memory.get_all_history()
    assert history_failed[0]['success'] is False

    print("  ✅ TEST 4 PASSED: When repair or invariants fail, autonomous completion is aborted and safely escalated.\n")
    reset_all_failures(app=app)

    # ========================================================================
    # TEST 5: HIGH-RISK REPAIR -> AUTONOMOUS ACTION BLOCKED -> HUMAN APPROVAL
    # ========================================================================
    print("#" * 70)
    print("▶️ TEST 5: HIGH-RISK REPAIR BLOCKED -> MANDATORY HUMAN APPROVAL")
    print("#" * 70)

    # 1. Trigger Persistent Data Mutation Risk
    trigger_failure("DATA_MUTATION_RISK", app=app)
    assert app.faults["persistent_data_mutation"] is True

    # 2. Run AutoHeal cycle
    rep5 = orchestrator.run_autoheal_cycle(fault_type="DATA_MUTATION_RISK")
    print(f"  • Autonomous execution result: {rep5['final_status']} (Must be ESCALATED)")
    print(f"  • Summary:                     {rep5['summary']}")
    assert rep5['final_status'] == "ESCALATED"
    assert "AUTONOMOUS ACTION BLOCKED" in rep5['summary']
    assert "87/100" in rep5['summary']

    # Verify AI identified repair
    win5 = rep5['hyp_eval']['winning_hypothesis']
    print(f"  • Identified Repair:           {win5['candidate_fix']}")
    assert win5['candidate_fix'] == "database_data_resync"

    # Verify Risk calculation
    risk5 = rep5['risk_assessment']
    print(f"  • Calculated Risk Score:       {risk5['risk_score']}/100 ({risk5['risk_level']})")
    print(f"  • Risk Reason:                 {risk5['reasons'][0]}")
    assert risk5['risk_score'] == 87
    assert risk5['risk_level'] == "CRITICAL"
    assert "Potential persistent data impact." in risk5['reasons'][0]
    assert risk5['decision'] == "BLOCK"

    # Verify Pre-flight sandbox validated in replica
    assert rep5['validation_report']['sandbox_status'] == "PASSED"

    # 3. Simulate Human Operator Approval
    inc5_id = rep5['incident_id']
    print(f"  • Operator approving repair for: {inc5_id}...")
    appr5 = orchestrator.approve_and_heal(inc5_id, approver="Hackathon Judge/Admin")
    print(f"  • Post-approval recovery status: {appr5['final_status']} (Recovered: {appr5['recovered']})")
    assert appr5['final_status'] == "RESOLVED"
    assert appr5['recovered'] is True
    assert app.faults["persistent_data_mutation"] is False

    print("  ✅ TEST 5 PASSED: Score 87/100 high risk repair blocked autonomous execution, requested approval, and recovered safely.\n")
    reset_all_failures(app=app)

    # ========================================================================
    # TEST 6: SIMILAR HISTORICAL INCIDENT -> INCIDENT MEMORY USED
    # ========================================================================
    print("#" * 70)
    print("▶️ TEST 6: SIMILAR HISTORICAL INCIDENT -> INCIDENT MEMORY USED")
    print("#" * 70)

    # Verify Incident Memory contains precedents from previous tests
    mem_search = memory.search_similar_incidents("API_DOWN")
    print(f"  • Querying Incident Memory for 'API_DOWN':")
    print(f"    - Similar incidents found: {mem_search['count']}")
    print(f"    - Historical best repair:   '{mem_search['best_repair']}'")
    print(f"    - Historical success rate:  {mem_search['best_success_rate']}%")
    print(f"    - Formatted summary:        \"{mem_search['formatted_summary']}\"")
    assert mem_search['count'] >= 1
    assert mem_search['best_repair'] == "restart_service"
    assert mem_search['best_success_rate'] == 100.0

    # Trigger a second API_DOWN incident and verify orchestrator incorporates memory
    trigger_failure("API_DOWN", app=app)
    rep6 = orchestrator.run_autoheal_cycle(fault_type="API_DOWN")

    # Check winning hypothesis supporting evidence incorporates memory insight
    winner6 = rep6['hyp_eval']['winning_hypothesis']
    evidence_strings = " ".join(winner6['supporting_evidence'])
    print(f"  • Supporting evidence incorporates memory: {'Historical Precedent' in evidence_strings}")
    assert "Historical Precedent" in evidence_strings
    assert "restart_service" in evidence_strings
    assert rep6['final_status'] == "RESOLVED"

    # Verify AI Copilot can answer questions using memory facts
    print("\n  • Testing AI Incident Copilot answering using Incident Memory:")
    copilot_ctx = {
        "failure_type": "API_DOWN",
        "incident_id": rep6['incident_id'],
        "final_status": "RESOLVED",
        "hyp_eval": rep6['hyp_eval'],
        "risk_assessment": rep6['risk_assessment'],
        "validation_report": rep6['validation_report'],
        "verification_report": rep6['verification_report'],
        "history": mem_search
    }
    q_ans = copilot.ask("Why did the API fail and what historical precedents exist?", context=copilot_ctx)
    print(f"    User Query: 'Why did the API fail and what historical precedents exist?'")
    print(f"    Copilot Answer: \"{q_ans['answer']}\"")
    print(f"    Evidence Citations: {len(q_ans['evidence'])}")
    assert len(q_ans['answer']) > 20
    assert len(q_ans['evidence']) >= 2

    print("\n  ✅ TEST 6 PASSED: Historical incidents successfully retrieved, repair success rate calculated, and used as non-overriding supporting evidence.\n")
    reset_all_failures(app=app)

    print("=" * 80)
    print("🎉 ALL 6 COMPREHENSIVE END-TO-END TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 80)


if __name__ == "__main__":
    run_full_e2e_test_suite()
