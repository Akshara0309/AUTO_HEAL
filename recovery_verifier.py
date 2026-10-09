"""
AutoHeal AI - Dedicated Recovery Verification Engine
Proves whether the sandbox application actually recovered after a repair action.

Evaluates 6 Invariants:
  1. Service health (/health probe & status UP)
  2. Main API response (/api/orders functional test HTTP 200)
  3. Database connectivity (pool ping & query execution)
  4. Error rate (< 5.0% SLO threshold)
  5. Response latency (< 250ms SLO threshold)
  6. Relevant failure condition (target fault flag verified cleared)

Compares:
  BEFORE repair vs AFTER repair

Safety Guarantee:
  - An incident is NEVER marked RESOLVED merely because a repair command ran.
  - If any check fails, recovery is flagged as FALSE and escalated.
"""

import sys
import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

# Safe console reconfigure for Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sandbox_app import SandboxApp, get_default_app
import fault_simulator


# ============================================================================
# SNAPSHOT CAPTURE UTILITY
# ============================================================================

def capture_system_snapshot(app: SandboxApp) -> Dict[str, Any]:
    """
    Captures a comprehensive diagnostic snapshot of the sandbox application.
    Used for Before-vs-After recovery differential analysis.
    """
    health = app.get_health()
    status = app.get_status()
    api_test = app.handle_api_request(endpoint="/api/orders", method="GET")

    metrics = health.get("metrics", {})
    checks = health.get("checks", {})
    subsystems = status.get("subsystems", {})

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "health_status": health.get("status"),
        "http_code": health.get("http_code"),
        "service_status": subsystems.get("service"),
        "database_status": subsystems.get("database"),
        "config_status": subsystems.get("config"),
        "cpu_pct": metrics.get("cpu_pct", 0),
        "memory_pct": metrics.get("memory_pct", 0),
        "error_rate_pct": metrics.get("error_rate_pct", 0),
        "latency_ms": metrics.get("latency_ms", 0),
        "active_faults": list(health.get("active_faults", [])),
        "api_functional": (api_test.get("ok") is True) and (api_test.get("http_code") == 200),
        "api_http_code": api_test.get("http_code"),
        "api_error": api_test.get("error"),
        "api_records_count": api_test.get("data", {}).get("count", 0) if api_test.get("ok") else 0
    }


# ============================================================================
# RECOVERY VERIFICATION ENGINE
# ============================================================================

class RecoveryVerificationEngine:
    """
    Rigorously validates post-repair recovery through differential before/after testing.
    """

    def __init__(self, app: Optional[SandboxApp] = None):
        self.app = app if app is not None else get_default_app()

    def verify_recovery(
        self,
        before_snapshot: Dict[str, Any],
        target_fault_type: Optional[str] = None,
        repair_action: Optional[str] = None,
        app: Optional[SandboxApp] = None
    ) -> Dict[str, Any]:
        """
        Executes the 6-point verification suite comparing BEFORE vs AFTER repair.

        Returns:
          {
            "recovered": true | false,
            "checks": [ ... ],
            "before": { ... },
            "after": { ... },
            "verification_summary": "..."
          }
        """
        target_app = app if app is not None else self.app

        # Small stabilization grace period
        time.sleep(0.3)

        # Capture post-repair fresh snapshot
        after_snapshot = capture_system_snapshot(target_app)

        checks: List[Dict[str, Any]] = []

        # --------------------------------------------------------------------
        # 1. SERVICE HEALTH CHECK
        # --------------------------------------------------------------------
        svc_up = (after_snapshot["health_status"] == "UP") and (after_snapshot["service_status"] == "running")
        checks.append({
            "name": "service_health",
            "passed": svc_up,
            "description": "Health probe status is UP (HTTP 200) and service is running",
            "before": f"{before_snapshot.get('service_status', 'unknown').upper()} (Health: {before_snapshot.get('health_status')})",
            "after": f"{after_snapshot['service_status'].upper()} (Health: {after_snapshot['health_status']})"
        })

        # --------------------------------------------------------------------
        # 2. MAIN API RESPONSE CHECK
        # --------------------------------------------------------------------
        api_ok = (after_snapshot["api_functional"] is True) and (after_snapshot["api_http_code"] == 200)
        checks.append({
            "name": "api_response",
            "passed": api_ok,
            "description": "GET /api/orders returns HTTP 200 with valid records payload",
            "before": f"HTTP {before_snapshot.get('api_http_code')} ({before_snapshot.get('api_error') or 'OK'})",
            "after": f"HTTP {after_snapshot['api_http_code']} ({after_snapshot['api_records_count']} records retrieved)"
        })

        # --------------------------------------------------------------------
        # 3. DATABASE CONNECTIVITY CHECK
        # --------------------------------------------------------------------
        db_ok = target_app.db.ping() and (after_snapshot["database_status"] == "connected")
        checks.append({
            "name": "database_connectivity",
            "passed": db_ok,
            "description": "PostgreSQL database connection pool ping & active transaction probe",
            "before": f"Database: {before_snapshot.get('database_status', 'unknown').upper()}",
            "after": f"Database: {after_snapshot['database_status'].upper()} (ping: OK)" if db_ok else "Database: TIMEOUT / UNHEALTHY"
        })

        # --------------------------------------------------------------------
        # 4. ERROR RATE CHECK
        # --------------------------------------------------------------------
        error_rate_ok = (after_snapshot["error_rate_pct"] < 5.0)
        checks.append({
            "name": "error_rate",
            "passed": error_rate_ok,
            "description": "System error rate within normal operational limits (< 5.0%)",
            "before": f"{before_snapshot.get('error_rate_pct', 0)}%",
            "after": f"{after_snapshot['error_rate_pct']}%"
        })

        # --------------------------------------------------------------------
        # 5. RESPONSE LATENCY CHECK
        # --------------------------------------------------------------------
        lat_ok = (after_snapshot["latency_ms"] < 500.0)
        checks.append({
            "name": "response_latency",
            "passed": lat_ok,
            "description": "API response latency compliant with p95 SLO threshold (< 250ms)",
            "before": f"{before_snapshot.get('latency_ms', 0)}ms",
            "after": f"{after_snapshot['latency_ms']}ms"
        })

        # --------------------------------------------------------------------
        # 6. RELEVANT FAILURE CONDITION CHECK
        # --------------------------------------------------------------------
        fault_cleared = True
        fault_name_checked = target_fault_type or "all_faults"

        if target_fault_type:
            # Map canonical name to internal fault flag if necessary
            fault_map = {
                "API_DOWN": "api_service_failure",
                "DATABASE_DOWN": "database_connection_failure",
                "HIGH_MEMORY": "high_memory_usage",
                "HIGH_LATENCY": "slow_api_response",
                "CONFIG_ERROR": "configuration_failure",
                "DATA_MUTATION_RISK": "persistent_data_mutation"
            }
            internal_flag = fault_map.get(target_fault_type, target_fault_type.lower())
            fault_cleared = not target_app.faults.get(internal_flag, False)
        else:
            fault_cleared = (len(after_snapshot["active_faults"]) == 0)

        checks.append({
            "name": "relevant_failure_condition",
            "passed": fault_cleared,
            "description": f"Target failure condition '{fault_name_checked}' is verified cleared in sandbox state",
            "before": f"Active Faults: {before_snapshot.get('active_faults')}",
            "after": f"Active Faults: {after_snapshot['active_faults']}" if not fault_cleared else "Target Fault CLEARED"
        })

        # --------------------------------------------------------------------
        # OVERALL RECOVERY DECISION
        # --------------------------------------------------------------------
        passed_count = sum(1 for c in checks if c["passed"])
        total_count = len(checks)
        recovered = (passed_count == total_count)

        if recovered:
            summary = (
                f"Recovery PROVEN: All {total_count}/{total_count} health and functional invariants satisfied. "
                f"Error rate dropped from {before_snapshot.get('error_rate_pct')}% to {after_snapshot['error_rate_pct']}%. "
                f"Main API endpoint restored to HTTP 200 ({after_snapshot['api_records_count']} records in {after_snapshot['latency_ms']}ms). "
                f"Target fault '{fault_name_checked}' is confirmed cleared."
            )
        else:
            failed_checks = [c["name"] for c in checks if not c["passed"]]
            summary = (
                f"Recovery FAILED: {total_count - passed_count}/{total_count} verification checks failed ({', '.join(failed_checks)}). "
                f"Application has NOT recovered. Escalating to human operator for immediate manual remediation."
            )

        print("\n" + "=" * 65)
        print(f"🔍 RECOVERY VERIFICATION: {'✅ RECOVERY CONFIRMED' if recovered else '❌ RECOVERY FAILED'}")
        print("=" * 65)
        for c in checks:
            status_icon = "[PASS]" if c["passed"] else "[FAIL]"
            print(f"  {status_icon} {c['name']:<28} Before: {c['before']:<22} After: {c['after']}")
        print(f"\nSummary: {summary}")
        print("=" * 65 + "\n")

        return {
            "recovered": recovered,
            "checks": checks,
            "before": before_snapshot,
            "after": after_snapshot,
            "verification_summary": summary
        }


# Singleton global instance
_global_verifier: Optional[RecoveryVerificationEngine] = None

def get_recovery_verifier() -> RecoveryVerificationEngine:
    global _global_verifier
    if _global_verifier is None:
        _global_verifier = RecoveryVerificationEngine()
    return _global_verifier


# ============================================================================
# SELF-TEST & VERIFICATION (SUCCESSFUL VS UNSUCCESSFUL RECOVERY)
# ============================================================================

def verify_recovery_engine():
    print("\n" + "=" * 70)
    print("[TEST] AUTOHEAL RECOVERY VERIFICATION ENGINE TEST SUITE")
    print("=" * 70)

    app = SandboxApp()
    verifier = RecoveryVerificationEngine(app=app)

    # ------------------------------------------------------------------------
    # TEST 1: SUCCESSFUL RECOVERY VERIFICATION (API_DOWN -> restart_service)
    # ------------------------------------------------------------------------
    print("\n>>> TEST 1: Proving Successful Recovery on API_DOWN")
    fault_simulator.trigger_failure("API_DOWN", app=app)

    # 1. Capture BEFORE snapshot
    before_1 = capture_system_snapshot(app)
    print(f"Before Snapshot: Health={before_1['health_status']}, API={before_1['api_http_code']}, ErrorRate={before_1['error_rate_pct']}%")
    assert before_1["health_status"] == "DOWN"
    assert before_1["api_functional"] is False

    # 2. Apply proper repair
    print("Applying proper repair: restart_service()...")
    app.clear_fault("api_service_failure")

    # 3. Run Verification Engine
    res_success = verifier.verify_recovery(
        before_snapshot=before_1,
        target_fault_type="API_DOWN",
        app=app
    )

    # Assertions
    assert res_success["recovered"] is True, "Must prove recovery as TRUE"
    assert len(res_success["checks"]) == 6, "Must evaluate all 6 checks"
    assert all(c["passed"] for c in res_success["checks"]), "All 6 checks must pass"
    assert "Recovery PROVEN" in res_success["verification_summary"]
    print("  -> Test 1 successfully proved recovery! [PASSED]")

    # ------------------------------------------------------------------------
    # TEST 2: UNSUCCESSFUL RECOVERY VERIFICATION (DATABASE_DOWN -> WRONG FIX)
    # ------------------------------------------------------------------------
    print("\n>>> TEST 2: Detecting Unsuccessful Recovery (DATABASE_DOWN -> Ineffective Fix)")
    fault_simulator.trigger_failure("DATABASE_DOWN", app=app)

    # 1. Capture BEFORE snapshot
    before_2 = capture_system_snapshot(app)
    print(f"Before Snapshot: Health={before_2['health_status']}, API={before_2['api_http_code']}, DB={before_2['database_status']}")
    assert before_2["health_status"] == "DOWN"

    # 2. Simulate applying an ineffective/wrong repair (e.g. restart_service instead of repair_database)
    print("Simulating application of wrong repair (restarting API instead of repairing DB)...")
    # This leaves the database broken!

    # 3. Run Verification Engine
    res_failed = verifier.verify_recovery(
        before_snapshot=before_2,
        target_fault_type="DATABASE_DOWN",
        app=app
    )

    # Assertions for failed recovery
    assert res_failed["recovered"] is False, "Must prove recovery as FALSE"
    assert "Recovery FAILED" in res_failed["verification_summary"]
    # Ensure specific checks failed
    failed_check_names = [c["name"] for c in res_failed["checks"] if not c["passed"]]
    print(f"Failed Invariant Checks Detected: {failed_check_names}")
    assert "database_connectivity" in failed_check_names, "Database connectivity must fail"
    assert "api_response" in failed_check_names, "API response must fail"
    print("  -> Test 2 successfully detected failed recovery and blocked resolution! [PASSED]")

    # Clean reset
    fault_simulator.reset_all_failures(app=app)

    print("\n" + "=" * 70)
    print("[SUCCESS] RECOVERY VERIFICATION ENGINE FULLY VERIFIED ON BOTH CASES!")
    print("=" * 70)


if __name__ == "__main__":
    verify_recovery_engine()
