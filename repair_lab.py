"""
AutoHeal AI - Repair Sandbox / Repair Lab
Provides an isolated, non-destructive test environment to validate proposed
repairs before touching the main application.

Workflow:
  1. Receive a proposed repair
  2. Create an isolated test environment (replicated from current failure state)
  3. Apply the repair in isolation
  4. Run health checks
  5. Run relevant functional tests (/api/orders)
  6. Measure recovery & assess side effects
  7. Destroy/reset the test environment
  8. Return validation result

Safety Guarantee:
  - The live main application state is NEVER touched during pre-flight validation.
  - Zero destructive changes to host operating system.
"""

import sys
import json
import time
from typing import Dict, Any, List, Optional
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
# REPAIR LAB ENGINE
# ============================================================================

class RepairLab:
    """
    Isolated test harness that evaluates repair effectiveness and safety
    prior to production/live deployment.
    """

    def __init__(self):
        self._lab_counter = 0

    def _spawn_isolated_environment(
        self,
        fault_type: Optional[str] = None,
        source_app: Optional[SandboxApp] = None
    ) -> SandboxApp:
        """
        Creates an isolated, in-memory replica of the sandbox application.
        Replicates the current failure state into the isolated container.
        """
        self._lab_counter += 1
        isolated_app = SandboxApp()

        # If a live source app is provided, clone its active faults
        if source_app is not None:
            for fault_key, is_active in source_app.faults.items():
                if is_active:
                    isolated_app.inject_fault(fault_key)
        # If an explicit failure type is provided, inject it
        elif fault_type:
            try:
                fault_simulator.trigger_failure(fault_type, app=isolated_app)
            except Exception:
                pass

        return isolated_app

    def _apply_repair_in_isolation(
        self,
        isolated_app: SandboxApp,
        repair_action: str
    ) -> Dict[str, Any]:
        """Executes the candidate repair against the isolated sandbox instance."""
        action = repair_action.strip().lower()

        if action in ("restart_service", "restart service"):
            # Clear API outage & high CPU
            isolated_app.clear_fault("api_service_failure")
            # If high memory or latency was also tied, clear it
            if isolated_app.faults.get("high_memory_usage"):
                isolated_app.clear_fault("high_memory_usage")
            if isolated_app.faults.get("slow_api_response"):
                isolated_app.clear_fault("slow_api_response")
            return {
                "ok": True,
                "action": "restart_service",
                "message": "Service process restarted, PID refreshed, socket rebound."
            }

        elif action in ("repair_database", "repair database"):
            isolated_app.clear_fault("database_connection_failure")
            return {
                "ok": True,
                "action": "repair_database",
                "message": "PostgreSQL connection pool cleared and re-initialized."
            }

        elif action in ("database_data_resync", "database data resync", "resync_database_data"):
            isolated_app.clear_fault("persistent_data_mutation")
            isolated_app.clear_fault("database_connection_failure")
            return {
                "ok": True,
                "action": "database_data_resync",
                "message": "Storage ledger journals resynchronized cleanly in isolated test replica."
            }

        elif action in ("rollback_config", "rollback configuration", "rollback deployment"):
            isolated_app.clear_fault("configuration_failure")
            return {
                "ok": True,
                "action": "rollback_config",
                "message": "Configuration schema restored to previous known-good tag v1.4.1."
            }

        elif action in ("reset_latency_profile", "reset latency profile"):
            isolated_app.clear_fault("slow_api_response")
            return {
                "ok": True,
                "action": "reset_latency_profile",
                "message": "Request thread pool flushed and latency profile reset."
            }

        elif action in ("flush_cache", "flush cache"):
            isolated_app.clear_fault("high_memory_usage")
            return {
                "ok": True,
                "action": "flush_cache",
                "message": "Transient worker heap caches evicted."
            }

        return {
            "ok": False,
            "action": repair_action,
            "message": f"Unknown repair action '{repair_action}'."
        }

    def _run_functional_tests(self, isolated_app: SandboxApp) -> Dict[str, Any]:
        """Runs end-to-end functional smoke tests on the isolated sandbox."""
        # Test 1: Query main API endpoint (/api/orders)
        api_result = isolated_app.handle_api_request(endpoint="/api/orders", method="GET")

        functional_ok = (api_result.get("ok") is True) and (api_result.get("http_code") == 200)

        # Test 2: Verify payload contents
        record_count = 0
        if functional_ok:
            record_count = api_result.get("data", {}).get("count", 0)
            if record_count == 0:
                functional_ok = False

        return {
            "functional_test_passed": functional_ok,
            "http_code": api_result.get("http_code"),
            "latency_ms": api_result.get("latency_ms", 0),
            "record_count": record_count,
            "error": api_result.get("error")
        }

    def _teardown_isolated_environment(self, isolated_app: SandboxApp):
        """Cleanly destroys and resets the isolated test environment."""
        isolated_app.clear_all_faults()
        del isolated_app

    def validate_repair(
        self,
        repair: str,
        fault_type: Optional[str] = None,
        live_app: Optional[SandboxApp] = None
    ) -> Dict[str, Any]:
        """
        Validates a candidate repair in an isolated test sandbox before live deployment.

        Returns:
          {
            "repair": "...",
            "sandbox_status": "PASSED" | "FAILED",
            "health_check": true | false,
            "functional_test": true | false,
            "estimated_success": 0.95,
            "side_effects": [],
            "validation_summary": "..."
          }
        """
        start_time = time.time()
        side_effects: List[str] = []

        # Step 1 & 2: Spawn isolated sandbox replicating fault state
        isolated_app = self._spawn_isolated_environment(fault_type=fault_type, source_app=live_app)

        # Step 3: Apply the candidate repair to isolated environment
        repair_res = self._apply_repair_in_isolation(isolated_app, repair)

        # Step 4: Run health checks in isolated environment
        health = isolated_app.get_health()
        health_check_ok = (health.get("http_code") == 200) and (health.get("status") in ("UP", "DEGRADED"))

        # Step 5: Run relevant functional tests
        func_res = self._run_functional_tests(isolated_app)
        functional_test_ok = func_res.get("functional_test_passed", False)

        # Step 6: Measure recovery and evaluate side effects
        if repair in ("restart_service", "restart service"):
            side_effects.append("Transient worker thread initialization delay (~12ms)")
        elif repair in ("repair_database", "repair database"):
            side_effects.append("Temporary connection reset for active database clients")
        elif repair in ("database_data_resync", "database data resync"):
            side_effects.append("In-place reconciliation of uncommitted transaction journals and table locks")
        elif repair in ("rollback_config", "rollback configuration"):
            side_effects.append("Configuration cache reload across dependent services")

        # Determine overall sandbox status
        both_passed = health_check_ok and functional_test_ok

        if both_passed:
            sandbox_status = "PASSED"
            estimated_success = 0.96
            validation_summary = (
                f"Pre-flight validation PASSED in isolated Repair Lab. "
                f"Health checks reported {health['status']} (HTTP {health['http_code']}), "
                f"and functional API test succeeded with {func_res['record_count']} orders retrieved ({func_res['latency_ms']}ms)."
            )
        else:
            sandbox_status = "FAILED"
            estimated_success = 0.15
            reasons = []
            if not health_check_ok:
                reasons.append(f"health check reported {health['status']} (HTTP {health['http_code']})")
            if not functional_test_ok:
                reasons.append(f"functional API query failed with error: {func_res.get('error', 'unknown error')}")
            validation_summary = (
                f"Pre-flight validation FAILED in isolated Repair Lab. "
                f"Candidate repair '{repair}' was unable to restore service invariants: {'; '.join(reasons)}."
            )

        # Step 7: Teardown and destroy the isolated test environment
        self._teardown_isolated_environment(isolated_app)

        # Step 8: Return structured validation result
        return {
            "repair": repair,
            "sandbox_status": sandbox_status,
            "health_check": health_check_ok,
            "functional_test": functional_test_ok,
            "estimated_success": estimated_success,
            "side_effects": side_effects,
            "validation_summary": validation_summary
        }


# Singleton global lab instance
_global_repair_lab: Optional[RepairLab] = None

def get_repair_lab() -> RepairLab:
    global _global_repair_lab
    if _global_repair_lab is None:
        _global_repair_lab = RepairLab()
    return _global_repair_lab


# ============================================================================
# SELF-TEST & VERIFICATION
# ============================================================================

def verify_repair_lab():
    print("\n" + "=" * 70)
    print("[TEST] AUTOHEAL REPAIR LAB - PRE-FLIGHT VALIDATION TEST")
    print("=" * 70)

    live_app = SandboxApp()
    lab = RepairLab()

    # 1. Simulate API_DOWN on live app
    print("\n--- [1] Setting Live Application into Fault State (API_DOWN) ---")
    fault_simulator.trigger_failure("API_DOWN", app=live_app)
    live_health_before = live_app.get_health()
    print(f"Live App Health Before Repair Lab: Status = {live_health_before['status']} (HTTP {live_health_before['http_code']})")
    assert live_health_before["status"] == "DOWN"

    # 2. Run Repair Lab validation on API restart repair
    print("\n--- [2] Validating 'restart_service' in Isolated Repair Lab ---")
    val_result = lab.validate_repair(
        repair="restart_service",
        live_app=live_app
    )
    print(json.dumps(val_result, indent=2))

    # Assertions on required output schema
    assert val_result["repair"] == "restart_service"
    assert val_result["sandbox_status"] == "PASSED", "Validation must pass for restart_service"
    assert val_result["health_check"] is True, "Health check must be true"
    assert val_result["functional_test"] is True, "Functional test must be true"
    assert val_result["estimated_success"] >= 0.90, "Estimated success must be >= 0.90"
    assert isinstance(val_result["side_effects"], list)
    assert len(val_result["validation_summary"]) > 20

    # 3. Verify Live App was NOT mutated during pre-flight test
    print("\n--- [3] Verifying Live Application Safety ---")
    live_health_after = live_app.get_health()
    print(f"Live App Health After Repair Lab: Status = {live_health_after['status']} (HTTP {live_health_after['http_code']})")
    assert live_health_after["status"] == "DOWN", "Live application must remain safely in fault state until actual remediation!"
    print("  -> Live application safety verified! Zero side effects on main environment. [PASSED]")

    # 4. Test Ineffective Repair Detection (Negative Control)
    print("\n--- [4] Negative Test: Validating Ineffective Repair ('restart_service' on DATABASE_DOWN) ---")
    val_wrong = lab.validate_repair(
        repair="restart_service",
        fault_type="DATABASE_DOWN"
    )
    print(f"Sandbox Status: {val_wrong['sandbox_status']}")
    print(f"Summary: {val_wrong['validation_summary']}")
    assert val_wrong["sandbox_status"] == "FAILED", "Ineffective repair must be rejected by Repair Lab"
    assert val_wrong["functional_test"] is False, "Functional test must fail for wrong repair"
    print("  -> Ineffective repair successfully caught and blocked by Repair Lab! [PASSED]")

    # Reset live app
    fault_simulator.reset_all_failures(app=live_app)

    print("\n" + "=" * 70)
    print("[SUCCESS] REPAIR LAB PRE-FLIGHT VALIDATION FULLY VERIFIED!")
    print("=" * 70)


if __name__ == "__main__":
    verify_repair_lab()
