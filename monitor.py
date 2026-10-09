"""
AutoHeal AI - Monitoring & Health Detection Layer
Provides deterministic health inspection and automated incident generation.

Detects:
  - Unhealthy service
  - Failed health check
  - Database failure
  - Abnormal latency
  - Simulated memory problem
  - Configuration failure

Generates standardized Incident objects in the IncidentManager.
Supports both on-demand inspection and continuous background monitoring.
"""

import sys
import json
import time
import threading
from typing import Dict, Any, List, Optional
from pathlib import Path

# Safe console reconfigure for Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from sandbox_app import SandboxApp, get_default_app, LOG_FILE
from incident_manager import Incident, IncidentManager, IncidentSeverity, IncidentStatus, get_incident_manager
import fault_simulator


# ============================================================================
# DETERMINISTIC HEALTH MONITOR
# ============================================================================

class HealthMonitor:
    """Deterministic monitoring engine inspecting sandbox health and triggering incidents."""

    def __init__(
        self,
        app: Optional[SandboxApp] = None,
        incident_manager: Optional[IncidentManager] = None
    ):
        self.app = app if app is not None else get_default_app()
        self.incident_manager = incident_manager if incident_manager is not None else get_incident_manager()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._poll_interval = 1.0

    def _get_recent_logs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Reads recent structured log entries from logs/app.log."""
        if not LOG_FILE.exists():
            return []
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = [line.strip() for line in f if line.strip()]
            entries = []
            for line in lines[-limit:]:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    entries.append({"raw": line})
            return entries
        except Exception:
            return []

    def inspect_now(self) -> Dict[str, Any]:
        """
        Runs on-demand deterministic inspection of the sandbox application.
        Evaluates health probes, service states, and metrics against SLO invariants.
        Automatically generates or refreshes Incident objects when problems are detected.
        """
        health = self.app.get_health()
        status = self.app.get_status()
        recent_logs = self._get_recent_logs(limit=12)

        checks = health.get("checks", {})
        metrics = health.get("metrics", {})
        subsystems = status.get("subsystems", {})

        detected_issues: List[Dict[str, Any]] = []
        created_or_updated_incidents: List[Incident] = []

        # --------------------------------------------------------------------
        # DETERMINISTIC DETECTION RULES
        # --------------------------------------------------------------------

        # Rule 1: Unhealthy Service / Failed Service Health Check
        if checks.get("service") == "DOWN" or subsystems.get("service") == "down" or self.app.faults.get("api_service_failure"):
            detected_issues.append({
                "service": "api-service",
                "failure_type": "API_DOWN",
                "severity": IncidentSeverity.CRITICAL.value,
                "description": "API service process is DOWN: port 8080 connection refused, health probe failed, error rate spike.",
                "affected_component": "API Service Gateway"
            })

        # Rule 2A: Persistent Data Mutation Risk
        if self.app.faults.get("persistent_data_mutation"):
            detected_issues.append({
                "service": "database",
                "failure_type": "DATA_MUTATION_RISK",
                "severity": IncidentSeverity.CRITICAL.value,
                "description": "Storage ledger desynchronization: uncommitted records detected in persistent database. Potential persistent data impact.",
                "affected_component": "PostgreSQL Storage Engine / Orders Ledger"
            })

        # Rule 2: Database Connection Failure
        elif checks.get("database") == "DOWN" or not self.app.db.connected or self.app.faults.get("database_connection_failure"):
            detected_issues.append({
                "service": "database",
                "failure_type": "DATABASE_DOWN",
                "severity": IncidentSeverity.CRITICAL.value,
                "description": "Database connection failure: Connection timed out to postgresql-primary:5432, connection pool exhausted.",
                "affected_component": "PostgreSQL Primary Database Pool"
            })

        # Rule 3: Configuration Failure
        if checks.get("config") == "INVALID" or subsystems.get("config") == "invalid" or self.app.faults.get("configuration_failure"):
            detected_issues.append({
                "service": "config-service",
                "failure_type": "CONFIG_ERROR",
                "severity": IncidentSeverity.HIGH.value,
                "description": f"Configuration validation failure: missing database parameters in release {subsystems.get('config_version', 'v1.4.2')}.",
                "affected_component": "Configuration Provider Engine"
            })

        # Rule 4: Simulated Memory Problem
        if checks.get("memory") == "HIGH" or metrics.get("memory_pct", 0) > 85.0 or self.app.faults.get("high_memory_usage"):
            mem_pct = metrics.get("memory_pct", 94.5)
            mem_mb = metrics.get("memory_mb", 1920.0)
            detected_issues.append({
                "service": "system-monitor",
                "failure_type": "HIGH_MEMORY",
                "severity": IncidentSeverity.HIGH.value,
                "description": f"High memory pressure detected: {mem_pct}% utilized ({mem_mb}MB / 2048MB). OOM crash hazard.",
                "affected_component": "System Memory Management"
            })

        # Rule 5: Abnormal Latency
        if checks.get("latency") == "SLOW" or metrics.get("latency_ms", 0) > 1000.0 or self.app.faults.get("slow_api_response"):
            latency_ms = metrics.get("latency_ms", 2450.0)
            detected_issues.append({
                "service": "api-service",
                "failure_type": "HIGH_LATENCY",
                "severity": IncidentSeverity.MEDIUM.value,
                "description": f"Abnormal response latency: {latency_ms}ms exceeds maximum SLO threshold (250ms).",
                "affected_component": "Request Routing Pipeline"
            })

        # --------------------------------------------------------------------
        # INCIDENT GENERATION
        # --------------------------------------------------------------------
        for issue in detected_issues:
            # Filter relevant logs for this service/failure
            svc = issue["service"]
            rel_logs = [l for l in recent_logs if l.get("service") == svc or l.get("severity") in ("ERROR", "WARNING", "CRITICAL")]

            incident = self.incident_manager.create_incident(
                service=issue["service"],
                failure_type=issue["failure_type"],
                severity=issue["severity"],
                description=issue["description"],
                affected_component=issue["affected_component"],
                logs=rel_logs if rel_logs else recent_logs[-5:],
                metrics=metrics,
                deduplicate=True
            )
            created_or_updated_incidents.append(incident)

        is_healthy = (len(detected_issues) == 0 and health.get("status") == "UP")

        return {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "healthy": is_healthy,
            "overall_status": health.get("status"),
            "detected_issues_count": len(detected_issues),
            "detected_issues": detected_issues,
            "active_incidents": [inc.to_dict() for inc in created_or_updated_incidents],
            "metrics": metrics,
            "checks": checks
        }

    # ------------------------------------------------------------------------
    # CONTINUOUS BACKGROUND MONITORING
    # ------------------------------------------------------------------------

    def start_background_monitor(self, interval_seconds: float = 1.0):
        """Starts a background daemon thread that polls sandbox health continuously."""
        if self._running:
            return
        self._running = True
        self._poll_interval = interval_seconds

        def _monitor_loop():
            print(f"\n[MONITOR] Continuous Health Monitoring started (interval: {interval_seconds}s)")
            while self._running:
                try:
                    self.inspect_now()
                except Exception as e:
                    print(f"[MONITOR ERROR] Error during health scan: {e}")
                time.sleep(self._poll_interval)

        self._thread = threading.Thread(target=_monitor_loop, daemon=True)
        self._thread.start()

    def stop_background_monitor(self):
        """Stops the background monitoring thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        print("[MONITOR] Continuous Health Monitoring stopped.")


# Singleton global monitor
_global_monitor: Optional[HealthMonitor] = None

def get_monitor(
    app: Optional[SandboxApp] = None,
    incident_manager: Optional[IncidentManager] = None
) -> HealthMonitor:
    global _global_monitor
    if _global_monitor is None or app is not None or incident_manager is not None:
        _global_monitor = HealthMonitor(app=app, incident_manager=incident_manager)
    return _global_monitor


# ============================================================================
# SELF-TEST & VERIFICATION (TESTING API_DOWN INCIDENT CREATION)
# ============================================================================

def verify_monitoring_layer():
    print("\n" + "=" * 70)
    print("[TEST] AUTOHEAL MONITORING & INCIDENT MANAGEMENT VERIFICATION")
    print("=" * 70)

    app = SandboxApp()
    im = IncidentManager(persistence_file=Path("logs") / "test_incidents.json")
    im.clear_all()
    monitor = HealthMonitor(app=app, incident_manager=im)

    # 1. Inspect clean baseline
    print("\n--- [1] Inspecting Clean Baseline System ---")
    initial_res = monitor.inspect_now()
    print(f"Health: {initial_res['overall_status']}, Detected Issues: {initial_res['detected_issues_count']}")
    assert initial_res["healthy"] is True
    assert initial_res["detected_issues_count"] == 0
    assert len(im.get_active_incidents()) == 0
    print("  -> Baseline is pristine. Zero incidents detected. [PASSED]")

    # 2. Trigger API_DOWN and verify automatic Incident creation
    print("\n--- [2] Triggering API_DOWN and Running Monitor Inspection ---")
    fault_simulator.trigger_failure("API_DOWN", app=app)

    # Monitor inspects and detects the problem
    scan_result = monitor.inspect_now()
    print(f"Monitor Scan Health: {scan_result['overall_status']}")
    print(f"Detected Issues Count: {scan_result['detected_issues_count']}")

    assert scan_result["healthy"] is False
    assert scan_result["detected_issues_count"] >= 1

    active_incidents = im.get_active_incidents()
    print(f"Active Incidents Count: {len(active_incidents)}")
    assert len(active_incidents) == 1

    incident = active_incidents[0]
    print(f"\nCreated Incident Summary:")
    print(f"  ID:                 {incident.id}")
    print(f"  Timestamp:          {incident.timestamp}")
    print(f"  Service:            {incident.service}")
    print(f"  Failure Type:       {incident.failure_type}")
    print(f"  Severity:           {incident.severity}")
    print(f"  Status:             {incident.status}")
    print(f"  Description:        {incident.description}")
    print(f"  Affected Component: {incident.affected_component}")
    print(f"  Metrics Captured:   CPU={incident.metrics.get('cpu_pct')}%, ErrorRate={incident.metrics.get('error_rate_pct')}%")
    print(f"  Logs Captured:      {len(incident.logs)} log entries")

    # Assert all required fields
    assert incident.id.startswith("INC-"), "Incident ID must start with INC-"
    assert incident.service == "api-service", "Service must be api-service"
    assert incident.failure_type == "API_DOWN", "Failure type must be API_DOWN"
    assert incident.severity == IncidentSeverity.CRITICAL.value, "Severity must be CRITICAL"
    assert incident.status == IncidentStatus.DETECTED.value, "Initial status must be DETECTED"
    assert "API service" in incident.description
    assert incident.affected_component == "API Service Gateway"
    assert len(incident.logs) > 0, "Incident must contain captured logs"
    assert incident.metrics.get("cpu_pct") == 95.0, "CPU metric must be captured"

    # 3. Test lifecycle progression (INVESTIGATING -> RESOLVED)
    print("\n--- [3] Testing Incident Lifecycle State Machine ---")
    im.update_status(incident.id, IncidentStatus.INVESTIGATING, "Agent started diagnosing logs.")
    assert im.get_incident(incident.id).status == "INVESTIGATING"

    im.update_status(incident.id, IncidentStatus.DIAGNOSED, "Root cause identified: Port 8080 down.")
    assert im.get_incident(incident.id).status == "DIAGNOSED"

    im.update_status(incident.id, IncidentStatus.REPAIR_PROPOSED, "Candidate fix: restart_service().")
    assert im.get_incident(incident.id).status == "REPAIR_PROPOSED"

    # Reset failure and verify resolution
    fault_simulator.reset_failure("API_DOWN", app=app)
    post_fix_scan = monitor.inspect_now()
    assert post_fix_scan["healthy"] is True

    im.resolve_incident(incident.id, "Service restarted, health check passed, zero errors.")
    assert im.get_incident(incident.id).status == "RESOLVED"
    assert len(im.get_active_incidents()) == 0
    print("  -> Incident successfully transitioned and resolved. [PASSED]")

    # Clean up test persistence file
    im.clear_all()

    print("\n" + "=" * 70)
    print("[SUCCESS] MONITORING AND INCIDENT MANAGEMENT FULLY VERIFIED!")
    print("=" * 70)


if __name__ == "__main__":
    verify_monitoring_layer()
