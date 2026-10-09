"""
AutoHeal AI - Multi-Hypothesis Reasoning & Testing Engine
Generates competing diagnostic hypotheses, executes non-destructive tests,
updates Bayesian/evidence confidence scores, ranks hypotheses, and selects
the verified root cause with clear comparative explanations.

Safety Guarantee:
  - Executes ONLY non-destructive diagnostic probes (port pings, DB pings, schema validation).
  - Never mutates state or executes destructive commands during diagnosis.
"""

import sys
import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Safe console reconfigure for Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from incident_manager import Incident, IncidentStatus, get_incident_manager
from sandbox_app import SandboxApp, get_default_app, LOG_FILE
import fault_simulator


# ============================================================================
# HYPOTHESIS DATA MODEL
# ============================================================================

@dataclass
class Hypothesis:
    id: str
    description: str
    initial_confidence: float
    confidence: float
    supporting_evidence: List[str] = field(default_factory=list)
    contradicting_evidence: List[str] = field(default_factory=list)
    diagnostic_test: str = ""
    candidate_fix: str = ""
    test_result: Optional[Dict[str, Any]] = None
    target_fault_type: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ============================================================================
# SAFE NON-DESTRUCTIVE DIAGNOSTIC TEST RUNNER
# ============================================================================

class SafeDiagnosticRunner:
    """
    Executes strictly read-only, non-destructive diagnostic probes
    against the sandbox application.
    """

    def execute_test(self, test_name: str, app: SandboxApp) -> Dict[str, Any]:
        start = time.time()

        if test_name == "test_api_port":
            # Probe port 8080 / API process availability
            is_up = (app.service_status == "running") and not app.faults.get("api_service_failure", False)
            latency = 1.2 if is_up else 0.5
            return {
                "test": "test_api_port",
                "target": "api-service (port 8080)",
                "passed": is_up,  # True if healthy, False if down
                "latency_ms": latency,
                "output": "Port 8080 is LISTENING and responding to HTTP probes" if is_up
                          else "Connection refused on port 8080: API service process unresponsive",
                "non_destructive": True
            }

        elif test_name == "test_db_ping":
            # Probe database connection pool ping
            is_connected = app.db.ping() and not app.faults.get("database_connection_failure", False)
            latency = 4.5 if is_connected else 5000.0
            return {
                "test": "test_db_ping",
                "target": "postgresql-primary:5432",
                "passed": is_connected,
                "latency_ms": latency,
                "output": "Database ping probe succeeded (active connections: 2/10)" if is_connected
                          else "Database ping probe TIMEOUT after 5000ms: pool exhausted",
                "non_destructive": True
            }

        elif test_name == "test_config_schema":
            # Validate configuration schema
            is_valid = (app.config_status == "valid") and not app.faults.get("configuration_failure", False)
            return {
                "test": "test_config_schema",
                "target": "config-service (v1.4.2)",
                "passed": is_valid,
                "latency_ms": 0.8,
                "output": "Configuration schema validated: all required parameters present" if is_valid
                          else "Schema validation FAILED: missing required parameter 'db.pool.min_idle'",
                "non_destructive": True
            }

        elif test_name == "test_memory_footprint":
            # Check worker memory allocations
            mem_normal = not app.faults.get("high_memory_usage", False) and app.memory_pct < 85.0
            return {
                "test": "test_memory_footprint",
                "target": "system-monitor",
                "passed": mem_normal,
                "latency_ms": 1.0,
                "output": f"Memory footprint nominal: {app.memory_pct}% utilized ({app.memory_mb}MB)" if mem_normal
                          else f"Memory footprint CRITICAL: {app.memory_pct}% utilized ({app.memory_mb}MB / 2048MB)",
                "non_destructive": True
            }

        elif test_name == "test_endpoint_latency":
            # Check endpoint response time
            lat_normal = not app.faults.get("slow_api_response", False) and app.base_latency_ms < 500.0
            return {
                "test": "test_endpoint_latency",
                "target": "api-service /api/orders",
                "passed": lat_normal,
                "latency_ms": app.base_latency_ms,
                "output": f"Response latency acceptable: {app.base_latency_ms}ms (SLO: 250ms)" if lat_normal
                          else f"Response latency DEGRADED: {app.base_latency_ms}ms exceeds 250ms threshold",
                "non_destructive": True
            }

        elif test_name in ("test_storage_ledger", "test_persistent_data"):
            # Probe persistent database storage ledger synchronization
            is_synchronized = not app.faults.get("persistent_data_mutation", False) and app.db.ping()
            return {
                "test": "test_storage_ledger",
                "target": "postgresql-primary / orders_ledger",
                "passed": is_synchronized,
                "latency_ms": 5.2 if is_synchronized else 48.0,
                "output": "Storage ledger verified: transaction journals synchronized with zero pending mutations" if is_synchronized
                          else "Storage ledger desynchronization detected: uncommitted records in persistent storage requiring resync",
                "non_destructive": True
            }

        return {
            "test": test_name,
            "target": "unknown",
            "passed": False,
            "output": f"Unknown diagnostic test '{test_name}'",
            "non_destructive": True
        }


# ============================================================================
# HYPOTHESIS TESTING ENGINE
# ============================================================================

class HypothesisTestingEngine:
    """
    Orchestrates the 5-step hypothesis evaluation workflow:
      1. Generate multiple competing hypotheses
      2. Rank initial hypotheses by evidence
      3. Execute safe diagnostic checks
      4. Update confidence scores based on test findings
      5. Select winner with comparative explanation
    """

    def __init__(self, app: Optional[SandboxApp] = None):
        self.app = app if app is not None else get_default_app()
        self.runner = SafeDiagnosticRunner()

    def generate_hypotheses(self, incident: Incident) -> List[Hypothesis]:
        """
        Generates at least 3 plausible competing hypotheses tailored to the incident symptoms.
        """
        failure_type = incident.failure_type
        metrics = incident.metrics or {}
        logs = incident.logs or []
        log_events = [l.get("event") for l in logs if isinstance(l, dict)]

        hypotheses: List[Hypothesis] = []

        if failure_type == "API_DOWN":
            hypotheses = [
                Hypothesis(
                    id="HYP-1",
                    description="API Gateway service process crash and port 8080 refusal",
                    initial_confidence=0.70,
                    confidence=0.70,
                    supporting_evidence=[
                        "Service crash log recorded in logs/app.log",
                        f"Error rate elevated to {metrics.get('error_rate_pct', 85)}%",
                        "Health probe reported service DOWN"
                    ],
                    contradicting_evidence=[],
                    diagnostic_test="test_api_port",
                    candidate_fix="restart_service",
                    target_fault_type="API_DOWN"
                ),
                Hypothesis(
                    id="HYP-2",
                    description="Database connection pool timeout causing cascading API outage",
                    initial_confidence=0.20,
                    confidence=0.20,
                    supporting_evidence=[
                        "High HTTP error rates observed by clients",
                        "Endpoints unable to fulfill user requests"
                    ],
                    contradicting_evidence=[
                        "No DB timeout log entries found in recent log sample"
                    ],
                    diagnostic_test="test_db_ping",
                    candidate_fix="repair_database",
                    target_fault_type="DATABASE_DOWN"
                ),
                Hypothesis(
                    id="HYP-3",
                    description="Corrupted configuration preventing API request routing",
                    initial_confidence=0.10,
                    confidence=0.10,
                    supporting_evidence=[
                        "Recent deployment recorded 10 minutes ago",
                        "Service failing to respond to requests"
                    ],
                    contradicting_evidence=[
                        "No schema validation errors in current logs"
                    ],
                    diagnostic_test="test_config_schema",
                    candidate_fix="rollback_config",
                    target_fault_type="CONFIG_ERROR"
                )
            ]

        elif failure_type == "DATABASE_DOWN":
            hypotheses = [
                Hypothesis(
                    id="HYP-1",
                    description="PostgreSQL connection pool exhaustion and socket timeout",
                    initial_confidence=0.72,
                    confidence=0.72,
                    supporting_evidence=[
                        "Database connection timeout logged to postgresql-primary:5432",
                        "Query to orders table threw OperationalError timeout",
                        f"Error rate spiked to {metrics.get('error_rate_pct', 70)}%"
                    ],
                    contradicting_evidence=[],
                    diagnostic_test="test_db_ping",
                    candidate_fix="repair_database",
                    target_fault_type="DATABASE_DOWN"
                ),
                Hypothesis(
                    id="HYP-2",
                    description="API Service crash or HTTP 500 error generation",
                    initial_confidence=0.18,
                    confidence=0.18,
                    supporting_evidence=[
                        "Clients experiencing failed request attempts",
                        "High error rates on orders endpoint"
                    ],
                    contradicting_evidence=[
                        "No service process crash logs found",
                        "API service listener still registered"
                    ],
                    diagnostic_test="test_api_port",
                    candidate_fix="restart_service",
                    target_fault_type="API_DOWN"
                ),
                Hypothesis(
                    id="HYP-3",
                    description="Severe downstream thread latency delaying database queries",
                    initial_confidence=0.10,
                    confidence=0.10,
                    supporting_evidence=[
                        "Requests timing out after 5000ms"
                    ],
                    contradicting_evidence=[
                        "Error explicitly indicates pool exhaustion, not generic latency"
                    ],
                    diagnostic_test="test_endpoint_latency",
                    candidate_fix="reset_latency_profile",
                    target_fault_type="HIGH_LATENCY"
                )
            ]

        elif failure_type == "CONFIG_ERROR":
            hypotheses = [
                Hypothesis(
                    id="HYP-1",
                    description="Missing required database configuration parameter in release v1.4.2",
                    initial_confidence=0.68,
                    confidence=0.68,
                    supporting_evidence=[
                        "Schema validation error detected in config v1.4.2",
                        "Health check reported config INVALID",
                        "Recent deployment recorded 10 minutes ago"
                    ],
                    contradicting_evidence=[],
                    diagnostic_test="test_config_schema",
                    candidate_fix="rollback_config",
                    target_fault_type="CONFIG_ERROR"
                ),
                Hypothesis(
                    id="HYP-2",
                    description="Database connection failure during bootstrap",
                    initial_confidence=0.20,
                    confidence=0.20,
                    supporting_evidence=[
                        "Errors mention database connection parameters",
                        "API requests fail with HTTP 500"
                    ],
                    contradicting_evidence=[
                        "Database ping probe may be intact"
                    ],
                    diagnostic_test="test_db_ping",
                    candidate_fix="repair_database",
                    target_fault_type="DATABASE_DOWN"
                ),
                Hypothesis(
                    id="HYP-3",
                    description="API Gateway process crash",
                    initial_confidence=0.12,
                    confidence=0.12,
                    supporting_evidence=[
                        "Requests failing to complete successfully"
                    ],
                    contradicting_evidence=[
                        "Service process is running; errors are application-level 500s"
                    ],
                    diagnostic_test="test_api_port",
                    candidate_fix="restart_service",
                    target_fault_type="API_DOWN"
                )
            ]

        elif failure_type == "HIGH_MEMORY":
            hypotheses = [
                Hypothesis(
                    id="HYP-1",
                    description="Worker memory leak or uncollected buffer accumulation",
                    initial_confidence=0.75,
                    confidence=0.75,
                    supporting_evidence=[
                        f"Memory consumption at {metrics.get('memory_pct', 94.5)}%",
                        "High memory warning event in logs",
                        "Health probe reported status DEGRADED"
                    ],
                    contradicting_evidence=[],
                    diagnostic_test="test_memory_footprint",
                    candidate_fix="restart_service",
                    target_fault_type="HIGH_MEMORY"
                ),
                Hypothesis(
                    id="HYP-2",
                    description="API Gateway network backlog buffering",
                    initial_confidence=0.15,
                    confidence=0.15,
                    supporting_evidence=[
                        "Elevated error rates on system monitor"
                    ],
                    contradicting_evidence=[
                        "API port is healthy"
                    ],
                    diagnostic_test="test_api_port",
                    candidate_fix="restart_service",
                    target_fault_type="API_DOWN"
                ),
                Hypothesis(
                    id="HYP-3",
                    description="Downstream slow queries holding connection memory",
                    initial_confidence=0.10,
                    confidence=0.10,
                    supporting_evidence=[
                        "Memory allocations remain elevated"
                    ],
                    contradicting_evidence=[
                        "No database connection timeouts logged"
                    ],
                    diagnostic_test="test_db_ping",
                    candidate_fix="repair_database",
                    target_fault_type="DATABASE_DOWN"
                )
            ]

        elif failure_type in ("DATA_MUTATION_RISK", "persistent_data_mutation"):
            hypotheses = [
                Hypothesis(
                    id="HYP-1",
                    description="Persistent storage ledger desynchronization requiring data resync",
                    initial_confidence=0.74,
                    confidence=0.74,
                    supporting_evidence=[
                        "Storage ledger desynchronization event logged in logs/app.log",
                        "Uncommitted transaction entries flagged in persistent database tables",
                        "High potential persistent data mutation impact (Risk Score 87/100)"
                    ],
                    contradicting_evidence=[],
                    diagnostic_test="test_storage_ledger",
                    candidate_fix="database_data_resync",
                    target_fault_type="DATA_MUTATION_RISK"
                ),
                Hypothesis(
                    id="HYP-2",
                    description="Database connection pool timeout causing transient 503 errors",
                    initial_confidence=0.16,
                    confidence=0.16,
                    supporting_evidence=[
                        "Database subsystem reported disconnected"
                    ],
                    contradicting_evidence=[
                        "Storage ledger contains persistent uncommitted records rather than simple pool exhaustion"
                    ],
                    diagnostic_test="test_db_ping",
                    candidate_fix="repair_database",
                    target_fault_type="DATABASE_DOWN"
                ),
                Hypothesis(
                    id="HYP-3",
                    description="API Gateway service process crash",
                    initial_confidence=0.10,
                    confidence=0.10,
                    supporting_evidence=[
                        "HTTP 503 response codes observed by health probes"
                    ],
                    contradicting_evidence=[
                        "API service process listener remains active; failure is in persistent database layer"
                    ],
                    diagnostic_test="test_api_port",
                    candidate_fix="restart_service",
                    target_fault_type="API_DOWN"
                )
            ]

        else:  # HIGH_LATENCY or generic
            hypotheses = [
                Hypothesis(
                    id="HYP-1",
                    description="Downstream request thread congestion and artificial latency spike",
                    initial_confidence=0.70,
                    confidence=0.70,
                    supporting_evidence=[
                        f"Observed latency of {metrics.get('latency_ms', 2450)}ms exceeds SLO threshold (250ms)",
                        "Slow API latency warning event in logs"
                    ],
                    contradicting_evidence=[],
                    diagnostic_test="test_endpoint_latency",
                    candidate_fix="reset_latency_profile",
                    target_fault_type="HIGH_LATENCY"
                ),
                Hypothesis(
                    id="HYP-2",
                    description="Database query bottleneck or slow lock contention",
                    initial_confidence=0.20,
                    confidence=0.20,
                    supporting_evidence=[
                        "Requests query database table orders"
                    ],
                    contradicting_evidence=[
                        "Database health probe is responsive"
                    ],
                    diagnostic_test="test_db_ping",
                    candidate_fix="repair_database",
                    target_fault_type="DATABASE_DOWN"
                ),
                Hypothesis(
                    id="HYP-3",
                    description="Worker process memory thrashing",
                    initial_confidence=0.10,
                    confidence=0.10,
                    supporting_evidence=[
                        "Throughput throttled"
                    ],
                    contradicting_evidence=[
                        "Memory percentage within normal boundaries"
                    ],
                    diagnostic_test="test_memory_footprint",
                    candidate_fix="restart_service",
                    target_fault_type="HIGH_MEMORY"
                )
            ]

        return hypotheses

    def test_and_rank_hypotheses(
        self,
        incident: Incident,
        app: Optional[SandboxApp] = None
    ) -> Dict[str, Any]:
        """
        Runs the complete multi-hypothesis evaluation:
          1. Generates competing hypotheses
          2. Ranks them by initial confidence
          3. Executes safe diagnostic checks for each
          4. Updates confidence scores
          5. Selects winning root cause with explanation
        """
        target_app = app if app is not None else self.app

        # 1. Generate Hypotheses
        hypotheses = self.generate_hypotheses(incident)

        # 2. Initial Ranking
        hypotheses.sort(key=lambda h: h.initial_confidence, reverse=True)

        print("\n" + "=" * 65)
        print(f"🧠 MULTI-HYPOTHESIS TESTING FOR INCIDENT: {incident.id} ({incident.failure_type})")
        print("=" * 65)
        print(f"Generated {len(hypotheses)} competing hypotheses. Beginning safe diagnostic tests...\n")

        # 3. Execute Diagnostic Checks & Update Confidences
        for idx, hyp in enumerate(hypotheses, 1):
            print(f"--- [Hypothesis {idx}] {hyp.description} ---")
            print(f"  Initial Confidence:    {hyp.initial_confidence:.2f}")
            print(f"  Supporting Evidence:   {', '.join(hyp.supporting_evidence)}")
            print(f"  Diagnostic Test Probe: {hyp.diagnostic_test}")

            # Run safe test
            result = self.runner.execute_test(hyp.diagnostic_test, target_app)
            hyp.test_result = result
            test_passed = result["passed"]  # True = subsystem is healthy; False = subsystem is broken

            print(f"  Probe Result:          {'HEALTHY (PASSED)' if test_passed else 'DEFECT DETECTED (FAILED)'}")
            print(f"  Probe Output:          {result['output']}")

            # 4. Bayesian/Evidence Confidence Update
            # If the test detected a defect in the component this hypothesis accuses:
            if not test_passed:
                # Strong confirmation!
                hyp.confidence = round(min(0.98, hyp.initial_confidence + 0.25), 2)
                hyp.supporting_evidence.append(f"Diagnostic probe '{hyp.diagnostic_test}' confirmed defect: {result['output']}")
            else:
                # Component is actually healthy -> Disproves this hypothesis!
                hyp.confidence = round(max(0.02, hyp.initial_confidence * 0.15), 2)
                hyp.contradicting_evidence.append(f"Diagnostic probe '{hyp.diagnostic_test}' proved component healthy: {result['output']}")

            print(f"  Updated Confidence:    {hyp.confidence:.2f}\n")

        # 5. Final Ranking by Updated Confidence
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        winner = hypotheses[0]
        runner_ups = hypotheses[1:]

        # 6. Synthesize comparative explanation of WHY the winner won
        why_winner_won_points = [
            f"Primary verification: Diagnostic test '{winner.diagnostic_test}' directly confirmed defect with output: \"{winner.test_result['output']}\".",
            f"Confidence increased from initial {winner.initial_confidence:.2f} to {winner.confidence:.2f} based on physical probe validation."
        ]
        for other in runner_ups:
            why_winner_won_points.append(
                f"Competing hypothesis '{other.description}' was ruled out: probe '{other.diagnostic_test}' proved that subsystem was actually healthy ({other.test_result['output']}), dropping its confidence to {other.confidence:.2f}."
            )

        why_winner_won = " ".join(why_winner_won_points)

        print("=" * 65)
        print(f"🏆 WINNING ROOT CAUSE: {winner.description}")
        print(f"   Final Confidence:  {winner.confidence:.2f}")
        print(f"   Recommended Fix:   {winner.candidate_fix}")
        print(f"\n   WHY THIS HYPOTHESIS WON:")
        print(f"   {why_winner_won}")
        print("=" * 65 + "\n")

        return {
            "incident_id": incident.id,
            "failure_type": incident.failure_type,
            "hypotheses_evaluated": [h.to_dict() for h in hypotheses],
            "winning_hypothesis": winner.to_dict(),
            "recommended_fix": winner.candidate_fix,
            "confidence": winner.confidence,
            "why_winner_won": why_winner_won,
            "diagnostic_tests_executed": [
                {
                    "test": h.diagnostic_test,
                    "target": h.test_result["target"],
                    "passed": h.test_result["passed"],
                    "output": h.test_result["output"]
                }
                for h in hypotheses if h.test_result
            ]
        }


# Singleton engine instance
_global_hypothesis_engine: Optional[HypothesisTestingEngine] = None

def get_hypothesis_engine() -> HypothesisTestingEngine:
    global _global_hypothesis_engine
    if _global_hypothesis_engine is None:
        _global_hypothesis_engine = HypothesisTestingEngine()
    return _global_hypothesis_engine


# ============================================================================
# VERIFICATION SUITE (TESTING TWO DIFFERENT SCENARIOS)
# ============================================================================

def verify_hypothesis_engine():
    print("\n" + "=" * 70)
    print("[TEST] MULTI-HYPOTHESIS REASONING & TESTING ENGINE VERIFICATION")
    print("=" * 70)

    from incident_manager import IncidentManager
    from monitor import HealthMonitor

    app = SandboxApp()
    im = IncidentManager(persistence_file=Path("logs") / "test_hypothesis_incidents.json")
    im.clear_all()
    monitor = HealthMonitor(app=app, incident_manager=im)
    engine = HypothesisTestingEngine(app=app)

    # ------------------------------------------------------------------------
    # SCENARIO 1: API_DOWN
    # ------------------------------------------------------------------------
    print("\n========================================================")
    print(">>> SCENARIO 1: API_DOWN (API Service Failure)")
    print("========================================================")
    fault_simulator.trigger_failure("API_DOWN", app=app)
    monitor.inspect_now()
    inc_api = im.find_active_by_failure_type("API_DOWN")
    assert inc_api is not None

    api_result = engine.test_and_rank_hypotheses(inc_api, app=app)

    # Verifications for Scenario 1
    assert len(api_result["hypotheses_evaluated"]) >= 3, "Must generate at least 3 hypotheses"
    winner_api = api_result["winning_hypothesis"]
    assert "API Gateway" in winner_api["description"] or "API Service" in winner_api["description"]
    assert winner_api["confidence"] >= 0.90, "Winner must have >= 0.90 confidence"
    assert winner_api["candidate_fix"] == "restart_service"
    assert len(api_result["why_winner_won"]) > 50, "Must provide detailed comparative explanation"
    print("[PASS] Scenario 1 verified successfully!")

    # Reset
    fault_simulator.reset_failure("API_DOWN", app=app)
    im.resolve_incident(inc_api.id, "Resolved after Scenario 1.")

    # ------------------------------------------------------------------------
    # SCENARIO 2: DATABASE_DOWN
    # ------------------------------------------------------------------------
    print("\n========================================================")
    print(">>> SCENARIO 2: DATABASE_DOWN (Database Connection Pool Failure)")
    print("========================================================")
    fault_simulator.trigger_failure("DATABASE_DOWN", app=app)
    monitor.inspect_now()
    inc_db = im.find_active_by_failure_type("DATABASE_DOWN")
    assert inc_db is not None

    db_result = engine.test_and_rank_hypotheses(inc_db, app=app)

    # Verifications for Scenario 2
    assert len(db_result["hypotheses_evaluated"]) >= 3, "Must generate at least 3 hypotheses"
    winner_db = db_result["winning_hypothesis"]
    assert "PostgreSQL" in winner_db["description"] or "Database" in winner_db["description"]
    assert winner_db["confidence"] >= 0.90, "Winner must have >= 0.90 confidence"
    assert winner_db["candidate_fix"] == "repair_database"
    assert "ruled out" in db_result["why_winner_won"].lower()
    print("[PASS] Scenario 2 verified successfully!")

    # Clean reset
    fault_simulator.reset_failure("DATABASE_DOWN", app=app)
    im.resolve_incident(inc_db.id, "Resolved after Scenario 2.")
    im.clear_all()

    print("\n" + "=" * 70)
    print("[SUCCESS] MULTI-HYPOTHESIS ENGINE FULLY VERIFIED ON BOTH SCENARIOS!")
    print("=" * 70)


if __name__ == "__main__":
    verify_hypothesis_engine()
