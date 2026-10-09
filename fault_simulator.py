"""
AutoHeal AI - Safe Fault Simulator
Provides controlled, non-destructive simulation of infrastructure and application faults.

Supported Scenarios:
  1. API_DOWN       - API Service Process Outage & Port Refusal
  2. DATABASE_DOWN  - Database Connection Pool Exhaustion & Timeout
  3. HIGH_MEMORY    - Memory Pressure & Footprint Leak (94.5% / 1920MB)
  4. HIGH_LATENCY   - Severe Request Latency Degradation (>2200ms)
  5. CONFIG_ERROR   - Corrupted Configuration & Schema Validation Failure

Safety Guarantee:
  - All operations are strictly in-memory simulations against the sandbox application.
  - Zero destructive changes to host operating system or external systems.
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

from sandbox_app import SandboxApp, get_default_app, LOG_FILE


# ============================================================================
# SCENARIO CATALOG & SPECIFICATIONS
# ============================================================================

SCENARIOS: Dict[str, Dict[str, Any]] = {
    "API_DOWN": {
        "id": "API_DOWN",
        "name": "API Service Failure",
        "description": "Simulates complete crash of the API service process, connection refused on port 8080, and CPU spike to 95%.",
        "fault_key": "api_service_failure",
        "risk_level": "LOW",
        "blast_radius": "API Service only (stateless microservice)",
        "recovery_method": "restart_service()",
        "expected_symptoms": {
            "health_status": "DOWN",
            "http_code": 503,
            "api_endpoint_error": "Service Unavailable: API service is not responding",
            "service_subsystem": "down",
            "cpu_pct": 95.0,
            "error_rate_pct": 85.0
        },
        "expected_logs": [
            {
                "severity": "ERROR",
                "service": "api-service",
                "event": "SERVICE_CRASHED",
                "message": "API service process crashed: Connection refused on port 8080"
            },
            {
                "severity": "ERROR",
                "service": "api-service",
                "event": "HEALTH_CHECK_FAIL",
                "message": "Health probe failed! Overall status: DOWN"
            },
            {
                "severity": "ERROR",
                "service": "api-service",
                "event": "API_REQUEST_FAILED",
                "message": "Connection refused on port 8080"
            }
        ]
    },
    "DATABASE_DOWN": {
        "id": "DATABASE_DOWN",
        "name": "Database Connection Pool Failure",
        "description": "Simulates database connection timeout, pool exhaustion, and failed health probes to postgresql-primary:5432.",
        "fault_key": "database_connection_failure",
        "risk_level": "HIGH",
        "blast_radius": "Stateful persistence layer (data transactions and queries)",
        "recovery_method": "repair_database()",
        "expected_symptoms": {
            "health_status": "DOWN",
            "http_code": 503,
            "api_endpoint_error": "Gateway Timeout: Database connection timeout",
            "database_subsystem": "disconnected",
            "error_rate_pct": 70.0
        },
        "expected_logs": [
            {
                "severity": "ERROR",
                "service": "database",
                "event": "DB_CONNECTION_TIMEOUT",
                "message": "Database health check probe failed: Connection timed out to postgresql-primary:5432"
            },
            {
                "severity": "ERROR",
                "service": "api-service",
                "event": "HEALTH_CHECK_FAIL",
                "message": "Health probe failed! Overall status: DOWN"
            },
            {
                "severity": "ERROR",
                "service": "database",
                "event": "DB_QUERY_FAILED",
                "message": "OperationalError: Connection timeout after 5000ms"
            }
        ]
    },
    "HIGH_MEMORY": {
        "id": "HIGH_MEMORY",
        "name": "High Memory Pressure",
        "description": "Simulates memory leak/pressure reaching 94.5% (1920MB / 2048MB) with elevated system error rates.",
        "fault_key": "high_memory_usage",
        "risk_level": "LOW",
        "blast_radius": "Worker process memory allocation",
        "recovery_method": "restart_service() or flush_cache()",
        "expected_symptoms": {
            "health_status": "DEGRADED",
            "http_code": 200,
            "memory_pct": 94.5,
            "memory_mb": 1920.0,
            "memory_check": "HIGH",
            "error_rate_pct": 15.0
        },
        "expected_logs": [
            {
                "severity": "WARNING",
                "service": "system-monitor",
                "event": "HIGH_MEMORY_USAGE",
                "message": "System memory exceeded threshold: 94.5% utilized (1920MB / 2048MB)"
            },
            {
                "severity": "WARNING",
                "service": "system-monitor",
                "event": "HIGH_MEMORY_PRESSURE",
                "message": "Memory footprint at 94.5% during request execution"
            }
        ]
    },
    "HIGH_LATENCY": {
        "id": "HIGH_LATENCY",
        "name": "Degraded API Response Latency",
        "description": "Simulates downstream bottleneck and thread delays causing response latency spikes over 2200ms (threshold: 250ms).",
        "fault_key": "slow_api_response",
        "risk_level": "LOW",
        "blast_radius": "API request throughput and client timeouts",
        "recovery_method": "reset_latency_profile() or restart_service()",
        "expected_symptoms": {
            "health_status": "DEGRADED",
            "http_code": 200,
            "latency_ms": "> 2000ms",
            "latency_check": "SLOW",
            "error_rate_pct": 12.0
        },
        "expected_logs": [
            {
                "severity": "WARNING",
                "service": "api-service",
                "event": "HIGH_LATENCY_DETECTED",
                "message": "API response latency degraded: p95 latency spike 2450ms"
            },
            {
                "severity": "WARNING",
                "service": "api-service",
                "event": "SLOW_API_LATENCY",
                "message": "GET /api/orders processed with degraded latency"
            }
        ]
    },
    "CONFIG_ERROR": {
        "id": "CONFIG_ERROR",
        "name": "Application Configuration Failure",
        "description": "Simulates schema corruption in release configuration v1.4.2 (missing db pool settings) causing startup/runtime validation failures.",
        "fault_key": "configuration_failure",
        "risk_level": "MEDIUM",
        "blast_radius": "Application configuration state and bootstrap",
        "recovery_method": "rollback_config()",
        "expected_symptoms": {
            "health_status": "DOWN",
            "http_code": 503,
            "api_endpoint_error": "Internal Server Error: Application configuration validation failure",
            "config_subsystem": "invalid",
            "error_rate_pct": 60.0
        },
        "expected_logs": [
            {
                "severity": "ERROR",
                "service": "config-service",
                "event": "INVALID_CONFIGURATION",
                "message": "Schema validation error in config v1.4.2: missing db.pool.min_idle"
            },
            {
                "severity": "ERROR",
                "service": "api-service",
                "event": "HEALTH_CHECK_FAIL",
                "message": "Health probe failed! Overall status: DOWN"
            },
            {
                "severity": "ERROR",
                "service": "config-service",
                "event": "API_CONFIG_ERROR",
                "message": "Missing database pool configuration parameter"
            }
        ]
    },
    "DATA_MUTATION_RISK": {
        "id": "DATA_MUTATION_RISK",
        "name": "Persistent Data Ledger Desynchronization",
        "description": "Simulates storage ledger desynchronization flagged for high-risk table and index resynchronization (Score 87/100).",
        "fault_key": "persistent_data_mutation",
        "risk_level": "CRITICAL",
        "blast_radius": "Persistent PostgreSQL storage tables, transaction journals, and customer order records",
        "recovery_method": "database_data_resync()",
        "expected_symptoms": {
            "health_status": "DOWN",
            "http_code": 503,
            "api_endpoint_error": "Critical: Persistent storage desynchronization detected",
            "database_subsystem": "disconnected",
            "error_rate_pct": 75.0
        },
        "expected_logs": [
            {
                "severity": "CRITICAL",
                "service": "database",
                "event": "PERSISTENT_DATA_MUTATION_RISK",
                "message": "Storage ledger desynchronization: uncommitted records detected in persistent database. Potential persistent data impact."
            },
            {
                "severity": "ERROR",
                "service": "api-service",
                "event": "HEALTH_CHECK_FAIL",
                "message": "Health probe failed! Overall status: DOWN"
            }
        ]
    }
}

# Alias resolution mapping for developer flexibility
ALIAS_MAP = {
    "api_down": "API_DOWN",
    "api_service_failure": "API_DOWN",
    "service_failure": "API_DOWN",
    "database_down": "DATABASE_DOWN",
    "db_down": "DATABASE_DOWN",
    "database_connection_failure": "DATABASE_DOWN",
    "db_failure": "DATABASE_DOWN",
    "high_memory": "HIGH_MEMORY",
    "high_memory_usage": "HIGH_MEMORY",
    "memory_pressure": "HIGH_MEMORY",
    "high_latency": "HIGH_LATENCY",
    "slow_api_response": "HIGH_LATENCY",
    "latency_spike": "HIGH_LATENCY",
    "config_error": "CONFIG_ERROR",
    "configuration_failure": "CONFIG_ERROR",
    "bad_config": "CONFIG_ERROR",
    "data_mutation_risk": "DATA_MUTATION_RISK",
    "persistent_data_mutation": "DATA_MUTATION_RISK",
    "persistent_data_risk": "DATA_MUTATION_RISK",
    "high_risk_data": "DATA_MUTATION_RISK"
}


def _resolve_scenario_id(type_name: str) -> str:
    """Normalizes any alias or case variation to canonical scenario ID."""
    if not type_name:
        raise ValueError("Failure type cannot be empty.")
    normalized = type_name.strip()
    if normalized.upper() in SCENARIOS:
        return normalized.upper()
    canonical = ALIAS_MAP.get(normalized.lower())
    if canonical and canonical in SCENARIOS:
        return canonical
    valid_list = list(SCENARIOS.keys())
    raise ValueError(f"Unknown failure type: '{type_name}'. Available scenarios: {valid_list}")


# ============================================================================
# SIMULATOR CONTROLLER FUNCTIONS
# ============================================================================

def trigger_failure(failure_type: str, app: Optional[SandboxApp] = None) -> Dict[str, Any]:
    """
    Triggers a safe simulated failure scenario.
    Returns the scenario metadata, current state, symptoms, and expected logs.
    """
    scenario_id = _resolve_scenario_id(failure_type)
    scenario = SCENARIOS[scenario_id]
    target_app = app if app is not None else get_default_app()

    # Safely inject the fault into sandbox
    inject_result = target_app.inject_fault(scenario["fault_key"])

    # Measure current immediate symptoms
    health = target_app.get_health()
    status = target_app.get_status()

    return {
        "ok": True,
        "action": "TRIGGER_FAILURE",
        "scenario_id": scenario_id,
        "name": scenario["name"],
        "description": scenario["description"],
        "risk_level": scenario["risk_level"],
        "blast_radius": scenario["blast_radius"],
        "recovery_method": scenario["recovery_method"],
        "current_state": {
            "health_status": health["status"],
            "http_code": health["http_code"],
            "checks": health["checks"],
            "metrics": health["metrics"],
            "active_faults": health["active_faults"]
        },
        "expected_symptoms": scenario["expected_symptoms"],
        "expected_logs": scenario["expected_logs"]
    }


def reset_failure(failure_type: str, app: Optional[SandboxApp] = None) -> Dict[str, Any]:
    """
    Clears an individual failure scenario and returns updated system health.
    """
    scenario_id = _resolve_scenario_id(failure_type)
    scenario = SCENARIOS[scenario_id]
    target_app = app if app is not None else get_default_app()

    clear_result = target_app.clear_fault(scenario["fault_key"])
    health = target_app.get_health()

    return {
        "ok": True,
        "action": "RESET_FAILURE",
        "scenario_id": scenario_id,
        "name": scenario["name"],
        "current_state": {
            "health_status": health["status"],
            "http_code": health["http_code"],
            "checks": health["checks"],
            "metrics": health["metrics"],
            "active_faults": health["active_faults"]
        }
    }


def reset_all_failures(app: Optional[SandboxApp] = None) -> Dict[str, Any]:
    """
    Clears all active failure scenarios and returns system to healthy baseline.
    """
    target_app = app if app is not None else get_default_app()
    reset_result = target_app.clear_all_faults()
    health = target_app.get_health()

    return {
        "ok": True,
        "action": "RESET_ALL_FAILURES",
        "status": "HEALTHY",
        "current_state": {
            "health_status": health["status"],
            "http_code": health["http_code"],
            "checks": health["checks"],
            "metrics": health["metrics"],
            "active_faults": []
        }
    }


def get_failure_state(app: Optional[SandboxApp] = None) -> Dict[str, Any]:
    """
    Inspects current simulator state, active faults, and health metrics.
    """
    target_app = app if app is not None else get_default_app()
    health = target_app.get_health()
    status = target_app.get_status()

    # Map active internal faults to canonical scenario IDs
    active_scenarios = []
    for sc_id, sc in SCENARIOS.items():
        if target_app.faults.get(sc["fault_key"]):
            active_scenarios.append({
                "id": sc_id,
                "name": sc["name"],
                "risk_level": sc["risk_level"],
                "recovery_method": sc["recovery_method"]
            })

    return {
        "ok": True,
        "has_active_failures": len(active_scenarios) > 0,
        "active_failures_count": len(active_scenarios),
        "active_scenarios": active_scenarios,
        "health": health,
        "status": status
    }


def get_available_scenarios() -> List[Dict[str, Any]]:
    """Returns the full catalog of available fault scenarios."""
    return list(SCENARIOS.values())


# ============================================================================
# COMPREHENSIVE TEST SUITE
# ============================================================================

def test_simulator_scenarios():
    """
    Executes and verifies every simulated failure scenario:
      1. API_DOWN
      2. DATABASE_DOWN
      3. HIGH_MEMORY
      4. HIGH_LATENCY
      5. CONFIG_ERROR
    """
    print("\n" + "=" * 70)
    print("[TEST] AUTOHEAL FAULT SIMULATOR - SCENARIO VERIFICATION SUITE")
    print("=" * 70)

    test_app = SandboxApp()

    for idx, (sc_id, scenario) in enumerate(SCENARIOS.items(), 1):
        print(f"\n[{idx}/5] Testing Scenario: {sc_id} ({scenario['name']})")
        print("-" * 70)

        # 1. Trigger Failure
        print(f"  Action: trigger_failure('{sc_id}')")
        trigger_res = trigger_failure(sc_id, app=test_app)
        assert trigger_res["ok"] is True
        print(f"  Result: Risk Level = {trigger_res['risk_level']} | Recovery = {trigger_res['recovery_method']}")

        # 2. Verify Symptoms & State
        current_state = trigger_res["current_state"]
        print(f"  Health Check: status={current_state['health_status']}, http_code={current_state['http_code']}")
        print(f"  Metrics: CPU={current_state['metrics']['cpu_pct']}%, Mem={current_state['metrics']['memory_pct']}%, ErrorRate={current_state['metrics']['error_rate_pct']}%")

        if sc_id == "API_DOWN":
            assert current_state["health_status"] == "DOWN"
            assert current_state["checks"]["service"] == "DOWN"
            api_res = test_app.handle_api_request()
            assert api_res["http_code"] == 503

        elif sc_id == "DATABASE_DOWN":
            assert current_state["health_status"] == "DOWN"
            assert current_state["checks"]["database"] == "DOWN"
            api_res = test_app.handle_api_request()
            assert api_res["http_code"] == 504

        elif sc_id == "HIGH_MEMORY":
            assert current_state["health_status"] == "DEGRADED"
            assert current_state["checks"]["memory"] == "HIGH"
            assert current_state["metrics"]["memory_pct"] > 90.0

        elif sc_id == "HIGH_LATENCY":
            assert current_state["health_status"] == "DEGRADED"
            assert current_state["checks"]["latency"] == "SLOW"
            api_res = test_app.handle_api_request()
            assert api_res["latency_ms"] > 2000.0

        elif sc_id == "CONFIG_ERROR":
            assert current_state["health_status"] == "DOWN"
            assert current_state["checks"]["config"] == "INVALID"
            api_res = test_app.handle_api_request()
            assert api_res["http_code"] == 500

        # 3. Verify Log Generation
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            lines = [json.loads(line.strip()) for line in f if line.strip()]
        recent_events = [entry.get("event") for entry in lines[-5:]]
        print(f"  Recent Log Events: {recent_events}")
        expected_first_event = scenario["expected_logs"][0]["event"]
        assert expected_first_event in recent_events, f"Expected event '{expected_first_event}' not found in logs"

        # 4. Verify Failure State Query
        state = get_failure_state(app=test_app)
        assert state["has_active_failures"] is True
        active_ids = [s["id"] for s in state["active_scenarios"]]
        assert sc_id in active_ids

        # 5. Reset Failure
        print(f"  Action: reset_failure('{sc_id}')")
        reset_res = reset_failure(sc_id, app=test_app)
        assert reset_res["ok"] is True

        # 6. Verify System Recovered
        post_reset_health = test_app.get_health()
        assert post_reset_health["status"] == "UP", f"System did not return to UP after reset of {sc_id}"
        print(f"  Recovery Check: Status = {post_reset_health['status']} (HTTP {post_reset_health['http_code']}) -> [PASSED]")

    # Final overall clean reset
    reset_all_failures(app=test_app)
    final_state = get_failure_state(app=test_app)
    assert final_state["has_active_failures"] is False

    print("\n" + "=" * 70)
    print("[SUCCESS] ALL 5 FAULT SIMULATOR SCENARIOS VERIFIED SUCCESSFULLY!")
    print("=" * 70)


if __name__ == "__main__":
    test_simulator_scenarios()
