"""
AutoHeal AI - Central Auto-Healing Orchestrator
Coordinates the end-to-end autonomous incident remediation lifecycle:

Event Stream:
  DETECTED
  → INVESTIGATING
  → HYPOTHESIS_TESTING
  → DIAGNOSED
  → REPAIR_PROPOSED
  → RISK_ASSESSED
  → SANDBOX_VALIDATED
  → HEALING
  → VERIFYING
  → RESOLVED (or ESCALATED on failure/high risk)

Safety Guarantees:
  - Zero execution of arbitrary shell commands.
  - Strictly executes whitelisted approved repair actions.
  - High/Critical risk actions halt for human operator approval.
  - Full audit timeline stored in incident memory.
"""

import sys
import json
import time
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

# Safe console reconfigure for Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sandbox_app import SandboxApp, get_default_app, LOG_FILE
from incident_manager import Incident, IncidentStatus, IncidentManager, get_incident_manager
from monitor import HealthMonitor, get_monitor
from hypothesis_engine import HypothesisTestingEngine, get_hypothesis_engine
from risk_engine import RiskAssessmentEngine, RiskLevel, RiskDecision, get_risk_engine
from repair_lab import RepairLab, get_repair_lab
from recovery_verifier import RecoveryVerificationEngine, capture_system_snapshot, get_recovery_verifier
from incident_memory import IncidentMemory, get_incident_memory
import fault_simulator


# ============================================================================
# APPROVED REPAIR EXECUTOR (SAFETY WHITELIST ENFORCEMENT)
# ============================================================================

class ApprovedRepairExecutor:
    """
    Executes ONLY whitelisted, non-arbitrary repair actions directly against
    the live application state.
    """

    @staticmethod
    def execute(repair_action: str, app: SandboxApp) -> Dict[str, Any]:
        action = repair_action.strip().lower()

        if action in ("restart_service", "restart service"):
            # Resets service crash, spikes, and associated latency/memory
            app.clear_fault("api_service_failure")
            if app.faults.get("slow_api_response"):
                app.clear_fault("slow_api_response")
            if app.faults.get("high_memory_usage"):
                app.clear_fault("high_memory_usage")
            return {
                "ok": True,
                "action": "restart_service",
                "message": "API service process restarted successfully. Port 8080 active."
            }

        elif action in ("repair_database", "repair database"):
            app.clear_fault("database_connection_failure")
            return {
                "ok": True,
                "action": "repair_database",
                "message": "Database connection pool flushed and re-connected to postgresql-primary:5432."
            }

        elif action in ("database_data_resync", "database data resync", "resync_database_data"):
            app.clear_fault("persistent_data_mutation")
            app.clear_fault("database_connection_failure")
            return {
                "ok": True,
                "action": "database_data_resync",
                "message": "Storage ledger journals resynchronized cleanly. Zero destructive operations performed (safe simulation)."
            }

        elif action in ("rollback_config", "rollback configuration", "rollback deployment"):
            app.clear_fault("configuration_failure")
            return {
                "ok": True,
                "action": "rollback_config",
                "message": "Configuration schema rolled back to stable release v1.4.1."
            }

        elif action in ("reset_latency_profile", "reset latency profile"):
            app.clear_fault("slow_api_response")
            return {
                "ok": True,
                "action": "reset_latency_profile",
                "message": "Latency throttling profile reset. Nominal response times restored."
            }

        elif action in ("flush_cache", "flush cache"):
            app.clear_fault("high_memory_usage")
            return {
                "ok": True,
                "action": "flush_cache",
                "message": "Transient memory caches evicted. Worker heap nominal."
            }

        raise PermissionError(f"Security Violation: '{repair_action}' is not in the approved repair whitelist.")


# ============================================================================
# AUTO-HEALING ORCHESTRATOR
# ============================================================================

class AutoHealOrchestrator:
    """
    Central coordinator orchestrating detection, hypothesis testing,
    risk evaluation, pre-flight sandbox validation, auto-healing, and verification.
    """

    def __init__(
        self,
        app: Optional[SandboxApp] = None,
        incident_manager: Optional[IncidentManager] = None,
        monitor: Optional[HealthMonitor] = None,
        hypothesis_engine: Optional[HypothesisTestingEngine] = None,
        risk_engine: Optional[RiskAssessmentEngine] = None,
        repair_lab: Optional[RepairLab] = None,
        recovery_verifier: Optional[RecoveryVerificationEngine] = None,
        incident_memory: Optional[IncidentMemory] = None
    ):
        self.app = app if app is not None else get_default_app()
        self.im = incident_manager if incident_manager is not None else get_incident_manager()
        self.monitor = monitor if monitor is not None else (HealthMonitor(app=self.app, incident_manager=self.im) if app is not None else get_monitor())
        self.hyp_engine = hypothesis_engine if hypothesis_engine is not None else (HypothesisTestingEngine(app=self.app) if app is not None else get_hypothesis_engine())
        self.risk_engine = risk_engine if risk_engine is not None else get_risk_engine()
        self.repair_lab = repair_lab if repair_lab is not None else get_repair_lab()
        self.verifier = recovery_verifier if recovery_verifier is not None else (RecoveryVerificationEngine(app=self.app) if app is not None else get_recovery_verifier())
        self.memory = incident_memory if incident_memory is not None else get_incident_memory()
        self.executor = ApprovedRepairExecutor()

    def run_autoheal_cycle(
        self,
        incident_id: Optional[str] = None,
        fault_type: Optional[str] = None,
        auto_approve_high_risk: bool = False,
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes the full AutoHeal workflow.
        Returns detailed report and lifecycle timeline.
        """
        event_stream: List[str] = []
        timeline_details: List[Dict[str, Any]] = []
        cycle_start_time = time.time()
        last_step_time = [cycle_start_time]

        def _emit_event(stage: str, details: Optional[Dict[str, Any]] = None):
            now = time.time()
            elapsed_stage = round(max(0.01, now - last_step_time[0]), 2)
            total_elapsed = round(now - cycle_start_time, 2)
            last_step_time[0] = now

            event_stream.append(stage)
            entry = {
                "stage": stage,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_s": elapsed_stage,
                "total_elapsed_s": total_elapsed,
                "details": details or {}
            }
            timeline_details.append(entry)
            print(f"  [EVENT] {stage} (+{elapsed_stage}s)")
            if event_callback:
                try:
                    event_callback(stage, entry)
                except Exception:
                    pass

        print("\n" + "=" * 70)
        print("⚡ AUTOHEAL ORCHESTRATOR - INITIATING AUTONOMOUS RECOVERY CYCLE")
        print("=" * 70)

        # --------------------------------------------------------------------
        # STEP 1: DETECT INCIDENT
        # --------------------------------------------------------------------
        incident: Optional[Incident] = None

        if incident_id:
            incident = self.im.get_incident(incident_id)

        if not incident and fault_type:
            incident = self.im.find_active_by_failure_type(fault_type)

        if not incident:
            # Trigger fresh health inspection to detect active faults
            scan_result = self.monitor.inspect_now()
            active_list = self.im.get_active_incidents()
            if active_list:
                incident = active_list[-1]

        if not incident:
            return {
                "ok": True,
                "status": "HEALTHY",
                "message": "No active incidents detected. System is running within SLO parameters.",
                "event_stream": ["HEALTHY"]
            }

        _emit_event("DETECTED", {
            "incident_id": incident.id,
            "failure_type": incident.failure_type,
            "severity": incident.severity
        })

        # --------------------------------------------------------------------
        # STEP 2: COLLECT EVIDENCE & INVESTIGATE
        # --------------------------------------------------------------------
        self.im.update_status(incident.id, IncidentStatus.INVESTIGATING, "Gathering multi-source evidence.")
        _emit_event("INVESTIGATING", {
            "logs_count": len(incident.logs),
            "metrics": incident.metrics
        })

        # --------------------------------------------------------------------
        # STEP 3 & 4: MULTI-HYPOTHESIS GENERATION & SAFE TESTING
        # --------------------------------------------------------------------
        # Query Incident Memory for historical precedent
        historical_context = self.memory.search_similar_incidents(incident.failure_type)
        if historical_context.get("count", 0) > 0:
            print(f"  [MEMORY] Found {historical_context['count']} similar historical incidents.")
            print(f"  [MEMORY] Historical insight: {historical_context.get('memory_insight', '')}")

        _emit_event("HYPOTHESIS_GENERATION", {
            "historical_similar_count": historical_context.get("count", 0),
            "memory_insight": historical_context.get("memory_insight", "")
        })

        _emit_event("HYPOTHESIS_TESTING", {
            "historical_similar_count": historical_context.get("count", 0)
        })
        hyp_eval = self.hyp_engine.test_and_rank_hypotheses(incident, app=self.app)

        # --------------------------------------------------------------------
        # STEP 5 & 6: SELECT ROOT CAUSE & CANDIDATE REPAIR
        # --------------------------------------------------------------------
        winner = hyp_eval["winning_hypothesis"]
        if historical_context.get("count", 0) > 0:
            mem_summary = historical_context.get("formatted_summary", "")
            winner["supporting_evidence"].append(
                f"Historical Precedent: {mem_summary} (supporting evidence)"
            )
            hyp_eval["memory_precedent"] = historical_context

        proposed_repair = winner["candidate_fix"]
        self.im.update_status(
            incident.id,
            IncidentStatus.DIAGNOSED,
            f"Root cause verified: {winner['description']} (Confidence: {winner['confidence']})"
        )
        _emit_event("DIAGNOSED", {
            "root_cause": winner["description"],
            "confidence": winner["confidence"],
            "why_winner_won": hyp_eval["why_winner_won"]
        })

        self.im.update_status(
            incident.id,
            IncidentStatus.REPAIR_PROPOSED,
            f"Proposed whitelisted repair action: '{proposed_repair}'"
        )
        _emit_event("REPAIR_PROPOSED", {
            "proposed_repair": proposed_repair
        })

        # --------------------------------------------------------------------
        # STEP 7: RISK ASSESSMENT
        # --------------------------------------------------------------------
        preliminary_risk = self.risk_engine.assess_risk(proposed_repair, context={"sandbox_validated": False})
        _emit_event("RISK_ASSESSED", preliminary_risk)

        # --------------------------------------------------------------------
        # STEP 8: PRE-FLIGHT VALIDATION IN REPAIR LAB
        # --------------------------------------------------------------------
        validation_report = self.repair_lab.validate_repair(
            repair=proposed_repair,
            fault_type=incident.failure_type,
            live_app=self.app
        )

        sandbox_passed = (validation_report.get("sandbox_status") == "PASSED")
        _emit_event("SANDBOX_VALIDATED", validation_report)

        if not sandbox_passed:
            # Pre-flight failed! Escalate to human operator immediately
            escalation_reason = (
                f"Pre-flight Repair Lab validation FAILED for '{proposed_repair}'. "
                f"Aborting autonomous execution to protect live application. Details: {validation_report['validation_summary']}"
            )
            self.im.escalate_incident(incident.id, escalation_reason)
            _emit_event("ESCALATED", {"reason": escalation_reason})
            self.memory.save_incident(
                incident_id=incident.id,
                failure_type=incident.failure_type,
                root_cause=winner.get("description", "Unknown"),
                evidence=winner.get("supporting_evidence", []),
                selected_repair=proposed_repair,
                risk_score=preliminary_risk.get("risk_score", 0),
                sandbox_result=validation_report.get("sandbox_status", "FAILED"),
                recovery_result="ESCALATED: Sandbox validation failed",
                recovery_time=round(time.time() - cycle_start_time, 2),
                success=False
            )
            return self._build_report(
                incident, event_stream, timeline_details, False, escalation_reason,
                hyp_eval=hyp_eval, risk_assessment=preliminary_risk, validation_report=validation_report
            )

        # Re-assess risk with sandbox validation confirmed (-10 risk deduction)
        final_risk = self.risk_engine.assess_risk(proposed_repair, context={"sandbox_validated": True})

        # --------------------------------------------------------------------
        # STEP 9 & 10: DECISION BRANCHING (AUTO_EXECUTE vs HUMAN APPROVAL)
        # --------------------------------------------------------------------
        is_low_risk = (final_risk["risk_level"] == RiskLevel.LOW.value)
        can_auto_heal = is_low_risk and sandbox_passed

        if not can_auto_heal and not auto_approve_high_risk:
            # Medium/High/Critical risk requires Human Approval
            primary_reason = final_risk['reasons'][0] if final_risk.get('reasons') else 'High operational risk'
            approval_msg = (
                f"🛑 AUTONOMOUS ACTION BLOCKED: Candidate repair '{proposed_repair}' has {final_risk['risk_level']} risk "
                f"(Score: {final_risk['risk_score']}/100). Reason: {primary_reason}. Human approval required."
            )
            self.im.escalate_incident(incident.id, approval_msg)
            _emit_event("ESCALATED", {
                "reason": approval_msg,
                "risk_level": final_risk["risk_level"],
                "risk_score": final_risk["risk_score"]
            })
            return self._build_report(
                incident, event_stream, timeline_details, False, approval_msg,
                hyp_eval=hyp_eval, risk_assessment=final_risk, validation_report=validation_report
            )

        # --------------------------------------------------------------------
        # STEP 11: HEALING (EXECUTE APPROVED REPAIR)
        # --------------------------------------------------------------------
        # Capture BEFORE snapshot for recovery differential analysis
        before_snapshot = capture_system_snapshot(self.app)

        self.im.update_status(incident.id, IncidentStatus.HEALING, f"Executing approved repair: '{proposed_repair}'.")
        _emit_event("HEALING", {"action": proposed_repair})

        try:
            exec_result = self.executor.execute(proposed_repair, self.app)
            print(f"  [EXECUTE] {exec_result['message']}")
        except Exception as e:
            escalation_msg = f"Repair execution encountered runtime error: {str(e)}"
            self.im.escalate_incident(incident.id, escalation_msg)
            _emit_event("ESCALATED", {"reason": escalation_msg})
            self.memory.save_incident(
                incident_id=incident.id,
                failure_type=incident.failure_type,
                root_cause=winner.get("description", "Unknown"),
                evidence=winner.get("supporting_evidence", []),
                selected_repair=proposed_repair,
                risk_score=final_risk.get("risk_score", 0),
                sandbox_result=validation_report.get("sandbox_status", "UNKNOWN"),
                recovery_result=escalation_msg,
                recovery_time=round(time.time() - cycle_start_time, 2),
                success=False
            )
            return self._build_report(
                incident, event_stream, timeline_details, False, escalation_msg,
                hyp_eval=hyp_eval, risk_assessment=final_risk, validation_report=validation_report
            )

        # --------------------------------------------------------------------
        # STEP 12: VERIFY RECOVERY (6-POINT INVARIANT PROVING)
        # --------------------------------------------------------------------
        self.im.update_status(incident.id, IncidentStatus.VERIFYING, "Verifying 6-point recovery invariants.")
        _emit_event("VERIFYING")

        verification_report = self.verifier.verify_recovery(
            before_snapshot=before_snapshot,
            target_fault_type=incident.failure_type,
            repair_action=proposed_repair,
            app=self.app
        )

        recovery_ok = verification_report.get("recovered", False)
        recovery_time = round(time.time() - cycle_start_time, 2)

        # --------------------------------------------------------------------
        # STEP 13: RESOLVE OR ESCALATE & STORE INCIDENT IN MEMORY
        # --------------------------------------------------------------------
        if recovery_ok:
            resolution_summary = verification_report.get("verification_summary", "Incident resolved successfully.")
            self.im.resolve_incident(incident.id, resolution_summary)
            _emit_event("RESOLVED", {
                "resolution": resolution_summary,
                "verification_checks": verification_report.get("checks", []),
                "recovery_time": recovery_time
            })
            self.memory.save_incident(
                incident_id=incident.id,
                failure_type=incident.failure_type,
                root_cause=winner.get("description", "Unknown"),
                evidence=winner.get("supporting_evidence", []),
                selected_repair=proposed_repair,
                risk_score=final_risk.get("risk_score", 0),
                sandbox_result=validation_report.get("sandbox_status", "UNKNOWN"),
                recovery_result=resolution_summary,
                recovery_time=recovery_time,
                success=True
            )
            return self._build_report(
                incident, event_stream, timeline_details, True, resolution_summary,
                hyp_eval=hyp_eval, risk_assessment=final_risk, validation_report=validation_report, verification_report=verification_report
            )
        else:
            escalation_msg = verification_report.get("verification_summary", "Verification failed to prove recovery.")
            self.im.escalate_incident(incident.id, escalation_msg)
            _emit_event("ESCALATED", {
                "reason": escalation_msg,
                "verification_checks": verification_report.get("checks", []),
                "recovery_time": recovery_time
            })
            self.memory.save_incident(
                incident_id=incident.id,
                failure_type=incident.failure_type,
                root_cause=winner.get("description", "Unknown"),
                evidence=winner.get("supporting_evidence", []),
                selected_repair=proposed_repair,
                risk_score=final_risk.get("risk_score", 0),
                sandbox_result=validation_report.get("sandbox_status", "UNKNOWN"),
                recovery_result=escalation_msg,
                recovery_time=recovery_time,
                success=False
            )
            return self._build_report(
                incident, event_stream, timeline_details, False, escalation_msg,
                hyp_eval=hyp_eval, risk_assessment=final_risk, validation_report=validation_report, verification_report=verification_report
            )

    def approve_and_heal(
        self,
        incident_id: str,
        approver: str = "Hackathon Judge/Admin",
        event_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Allows human operator / dashboard to approve and execute a paused
        Medium/High risk repair.
        Records: who approved, timestamp, decision, repair, result.
        """
        incident = self.im.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found.")

        print(f"\n[OPERATOR APPROVAL] Human approval granted by '{approver}' for {incident_id} ({incident.failure_type})")
        report = self.run_autoheal_cycle(incident_id=incident_id, auto_approve_high_risk=True, event_callback=event_callback)

        # Determine result string
        result_desc = report.get("summary", "Execution completed.")
        result_str = f"SUCCESS: {result_desc}" if report.get("recovered") else f"FAILED: {result_desc}"

        proposed_repair = (report.get("validation_report") or {}).get("repair", incident.failure_type)
        risk_data = report.get("risk_assessment") or {}

        self.memory.record_approval(
            incident_id=incident_id,
            approver=approver,
            decision="APPROVED",
            repair=proposed_repair,
            risk_level=risk_data.get("risk_level", "HIGH"),
            risk_score=risk_data.get("risk_score", 60),
            result=result_str
        )
        return report

    def reject_repair(
        self,
        incident_id: str,
        approver: str = "Hackathon Judge/Admin",
        reason: str = "Operator declined execution"
    ) -> Dict[str, Any]:
        """
        Allows human operator / dashboard to reject execution of a proposed repair.
        Records: who rejected, timestamp, decision, repair, result.
        """
        incident = self.im.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found.")

        print(f"\n[OPERATOR REJECTION] Repair rejected by '{approver}' for {incident_id} ({incident.failure_type}): {reason}")
        escalation_msg = f"Repair rejected by human operator ({approver}): {reason}. Autonomous execution halted."
        self.im.escalate_incident(incident_id, escalation_msg)

        self.memory.record_approval(
            incident_id=incident_id,
            approver=approver,
            decision="REJECTED",
            repair=incident.failure_type,
            risk_level="HIGH",
            risk_score=60,
            result=f"REJECTED - {reason}"
        )

        return {
            "incident_id": incident_id,
            "decision": "REJECTED",
            "approver": approver,
            "status": "ESCALATED",
            "message": escalation_msg
        }

    def _build_report(
        self,
        incident: Incident,
        event_stream: List[str],
        timeline_details: List[Dict[str, Any]],
        recovered: bool,
        final_message: str,
        hyp_eval: Optional[Dict[str, Any]] = None,
        risk_assessment: Optional[Dict[str, Any]] = None,
        validation_report: Optional[Dict[str, Any]] = None,
        verification_report: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Formats the final summary report with full artifact inspection data."""
        stream_visual = " → ".join(event_stream)
        print("\n" + "=" * 70)
        print(f"🏁 AUTOHEAL LIFECYCLE COMPLETE: {'✅ RESOLVED' if recovered else '🚨 ESCALATED'}")
        print(f"   Event Stream: {stream_visual}")
        print(f"   Summary:      {final_message}")
        print("=" * 70 + "\n")

        return {
            "incident_id": incident.id,
            "incident": incident.to_dict(),
            "failure_type": incident.failure_type,
            "recovered": recovered,
            "final_status": incident.status,
            "event_stream": event_stream,
            "event_stream_visual": stream_visual,
            "timeline": timeline_details,
            "summary": final_message,
            "hyp_eval": hyp_eval,
            "risk_assessment": risk_assessment,
            "validation_report": validation_report,
            "verification_report": verification_report
        }


# Singleton global orchestrator
_global_orchestrator: Optional[AutoHealOrchestrator] = None

def get_orchestrator() -> AutoHealOrchestrator:
    global _global_orchestrator
    if _global_orchestrator is None:
        _global_orchestrator = AutoHealOrchestrator()
    return _global_orchestrator


# ============================================================================
# SELF-TEST & VERIFICATION
# ============================================================================

def verify_orchestrator():
    print("\n" + "=" * 70)
    print("[TEST] AUTOHEAL CENTRAL ORCHESTRATOR - FULL LIFECYCLE TEST")
    print("=" * 70)

    app = SandboxApp()
    im = IncidentManager(persistence_file=Path("logs") / "test_orchestrator_incidents.json")
    im.clear_all()
    monitor = HealthMonitor(app=app, incident_manager=im)
    hyp_engine = HypothesisTestingEngine(app=app)
    risk_engine = RiskAssessmentEngine()
    repair_lab = RepairLab()

    orchestrator = AutoHealOrchestrator(
        app=app,
        incident_manager=im,
        monitor=monitor,
        hypothesis_engine=hyp_engine,
        risk_engine=risk_engine,
        repair_lab=repair_lab
    )

    # ------------------------------------------------------------------------
    # SCENARIO 1: LOW RISK AUTONOMOUS HEALING (API_DOWN)
    # ------------------------------------------------------------------------
    print("\n>>> TEST 1: Full Autonomous Healing on API_DOWN (Low Risk)")
    fault_simulator.trigger_failure("API_DOWN", app=app)

    res1 = orchestrator.run_autoheal_cycle(fault_type="API_DOWN")

    print(f"Scenario 1 Result: Recovered = {res1['recovered']}, Final Status = {res1['final_status']}")
    print(f"Event Stream: {res1['event_stream_visual']}")

    expected_stream = [
        "DETECTED", "INVESTIGATING", "HYPOTHESIS_GENERATION", "HYPOTHESIS_TESTING", "DIAGNOSED",
        "REPAIR_PROPOSED", "RISK_ASSESSED", "SANDBOX_VALIDATED",
        "HEALING", "VERIFYING", "RESOLVED"
    ]
    assert res1["recovered"] is True, "API_DOWN must be autonomously recovered"
    assert res1["final_status"] == "RESOLVED", "Final status must be RESOLVED"
    assert res1["event_stream"] == expected_stream, f"Event stream mismatch: {res1['event_stream']}"
    print("[PASS] Scenario 1 full autonomous event stream verified!")

    # Verify live app is back to UP
    health1 = app.get_health()
    assert health1["status"] == "UP"

    # ------------------------------------------------------------------------
    # SCENARIO 2: HIGH RISK ESCALATION & HUMAN APPROVAL (DATABASE_DOWN)
    # ------------------------------------------------------------------------
    print("\n>>> TEST 2: High Risk Escalation & Human Approval on DATABASE_DOWN")
    fault_simulator.trigger_failure("DATABASE_DOWN", app=app)

    # First cycle without auto-approval -> Must pause and ESCALATE to human
    res2 = orchestrator.run_autoheal_cycle(fault_type="DATABASE_DOWN", auto_approve_high_risk=False)

    print(f"Scenario 2 Pre-Approval: Recovered = {res2['recovered']}, Status = {res2['final_status']}")
    print(f"Event Stream: {res2['event_stream_visual']}")
    assert res2["recovered"] is False, "High risk repair must NOT auto-execute without approval"
    assert res2["final_status"] == "ESCALATED", "Status must be ESCALATED pending approval"
    assert "ESCALATED" in res2["event_stream"]
    print("  -> High risk repair safely paused and paged human operator! [PASSED]")

    # Second step: Operator reviews risk and grants approval!
    print("\n>>> TEST 2 (Part B): Human Operator Grants Approval for Repair")
    res2_approved = orchestrator.approve_and_heal(res2["incident_id"])
    print(f"Scenario 2 Post-Approval: Recovered = {res2_approved['recovered']}, Status = {res2_approved['final_status']}")
    print(f"Event Stream: {res2_approved['event_stream_visual']}")
    assert res2_approved["recovered"] is True, "Must recover after human approval"
    assert res2_approved["final_status"] == "RESOLVED", "Status must be RESOLVED after approval"
    print("  -> Human-in-the-loop approval workflow successfully healed database! [PASSED]")

    # Verify live app is healthy
    health2 = app.get_health()
    assert health2["status"] == "UP"

    # Clean up test database
    im.clear_all()

    print("\n" + "=" * 70)
    print("[SUCCESS] AUTO-HEALING ORCHESTRATOR FULLY VERIFIED ON ALL WORKFLOWS!")
    print("=" * 70)


if __name__ == "__main__":
    verify_orchestrator()
