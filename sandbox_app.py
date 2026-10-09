"""
AutoHeal AI - Demo Application Layer (Sandbox Application)
Simulates a realistic, lightweight microservice with:
  1. Health endpoint (/health)
  2. Main API endpoint (/api/orders)
  3. Database interaction
  4. Structured JSON application logging
  5. Detailed service status (/status)
  6. Configurable failure states (API, Database, Memory, Latency, Config)

All failures are safely simulated in-memory without destructive operations.
"""

import time
import json
import random
import threading
import sys
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any, Optional

# Ensure safe console output encoding on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Maintain compatibility with existing sandbox.py
try:
    from sandbox import SYSTEM as LEGACY_SYSTEM, write_log as legacy_write_log
except ImportError:
    LEGACY_SYSTEM = {}
    legacy_write_log = None

LOG_FOLDER = Path("logs")
LOG_FOLDER.mkdir(exist_ok=True)
LOG_FILE = LOG_FOLDER / "app.log"


# ============================================================================
# STRUCTURED APPLICATION LOGGER
# ============================================================================

def log_event(
    service: str,
    severity: str,
    event: str,
    message: str,
    failure_type: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Appends a structured JSON log entry to logs/app.log and prints to console.
    Guarantees required fields:
      - timestamp
      - service
      - severity
      - event
      - message
      - failure_type (if applicable)
    """
    entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "service": service,
        "severity": severity.upper(),
        "event": event,
        "message": message,
        "failure_type": failure_type
    }
    if extra:
        entry.update(extra)

    line = json.dumps(entry)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

    print(f"[{entry['timestamp']}] [{entry['severity']}] [{entry['service']}] {entry['event']}: {entry['message']}")
    return entry


# ============================================================================
# SIMULATED DATABASE
# ============================================================================

class SimulatedDatabase:
    """Simulated in-memory database component with connection pooling & health checks."""

    def __init__(self):
        self.name = "postgresql-primary"
        self.port = 5432
        self.connected = True
        self.pool_size = 10
        self.active_connections = 2
        self.tables = {
            "orders": [
                {"id": "ORD-1001", "customer": "Acme Logistics", "amount": 1450.00, "status": "COMPLETED"},
                {"id": "ORD-1002", "customer": "Globex Retail", "amount": 320.50, "status": "PENDING"},
                {"id": "ORD-1003", "customer": "Soylent Corp", "amount": 890.00, "status": "PROCESSING"},
                {"id": "ORD-1004", "customer": "Initech Systems", "amount": 2100.75, "status": "COMPLETED"}
            ]
        }

    def ping(self) -> bool:
        return self.connected

    def query(self, table: str = "orders") -> Dict[str, Any]:
        if not self.connected:
            raise ConnectionError(
                f"OperationalError: Connection timeout after 5000ms connecting to {self.name}:{self.port}/orders_db (pool exhausted)"
            )
        # Healthy query execution
        return {
            "table": table,
            "rows": self.tables.get(table, []),
            "count": len(self.tables.get(table, [])),
            "execution_ms": round(random.uniform(4.0, 12.0), 2)
        }


# ============================================================================
# SANDBOX APPLICATION
# ============================================================================

class SandboxApp:
    """
    Realistic demo microservice with configurable failure injection and telemetry.
    """

    def __init__(self):
        self.db = SimulatedDatabase()
        self.start_time = time.time()
        self.total_requests = 0
        self.error_count = 0

        # Subsystem States
        self.service_status = "running"   # "running" | "down"
        self.config_status = "valid"      # "valid" | "invalid"
        self.config_version = "v1.4.2"

        # Failure Injection Flags
        self.faults = {
            "api_service_failure": False,
            "database_connection_failure": False,
            "high_memory_usage": False,
            "slow_api_response": False,
            "configuration_failure": False,
            "persistent_data_mutation": False
        }

        # Telemetry Baselines
        self.cpu_pct = 28.0
        self.memory_mb = 145.0
        self.memory_pct = 36.0
        self.error_rate_pct = 0.0
        self.base_latency_ms = 22.0

        self._sync_legacy_system()

    def _sync_legacy_system(self):
        """Keep legacy sandbox.SYSTEM dictionary synchronized for tools.py compatibility."""
        if isinstance(LEGACY_SYSTEM, dict):
            LEGACY_SYSTEM["service"] = "running" if self.service_status == "running" else "down"
            LEGACY_SYSTEM["database"] = "healthy" if self.db.connected else "unhealthy"
            LEGACY_SYSTEM["config"] = "normal" if self.config_status == "valid" else "invalid"
            LEGACY_SYSTEM["cpu"] = int(self.cpu_pct)
            LEGACY_SYSTEM["memory"] = int(self.memory_pct)
            LEGACY_SYSTEM["error_rate"] = int(self.error_rate_pct)

    # ------------------------------------------------------------------------
    # FAULT INJECTION CONTROLS
    # ------------------------------------------------------------------------

    def inject_fault(self, fault_name: str) -> Dict[str, Any]:
        """Safely activates a simulated fault condition."""
        if fault_name not in self.faults:
            raise ValueError(f"Unknown fault: {fault_name}. Valid faults: {list(self.faults.keys())}")

        self.faults[fault_name] = True

        if fault_name == "api_service_failure":
            self.service_status = "down"
            self.cpu_pct = 95.0
            self.error_rate_pct = 85.0
            log_event(
                service="api-service",
                severity="ERROR",
                event="SERVICE_CRASHED",
                message="API service process crashed: Connection refused on port 8080",
                failure_type="api_service_failure",
                extra={"port": 8080, "cpu_pct": self.cpu_pct}
            )

        elif fault_name == "database_connection_failure":
            self.db.connected = False
            self.error_rate_pct = 70.0
            log_event(
                service="database",
                severity="ERROR",
                event="DB_CONNECTION_TIMEOUT",
                message="Database health check probe failed: Connection timed out to postgresql-primary:5432",
                failure_type="database_connection_failure",
                extra={"host": self.db.name, "port": self.db.port}
            )

        elif fault_name == "high_memory_usage":
            self.memory_mb = 1920.0
            self.memory_pct = 94.5
            self.error_rate_pct = 15.0
            log_event(
                service="system-monitor",
                severity="WARNING",
                event="HIGH_MEMORY_USAGE",
                message="System memory exceeded threshold: 94.5% utilized (1920MB / 2048MB)",
                failure_type="high_memory_usage",
                extra={"memory_mb": self.memory_mb, "memory_pct": self.memory_pct}
            )

        elif fault_name == "slow_api_response":
            self.base_latency_ms = 2450.0
            self.error_rate_pct = 12.0
            log_event(
                service="api-service",
                severity="WARNING",
                event="HIGH_LATENCY_DETECTED",
                message="API response latency degraded: p95 latency spike 2450ms (threshold: 250ms)",
                failure_type="slow_api_response",
                extra={"latency_ms": self.base_latency_ms}
            )

        elif fault_name == "configuration_failure":
            self.config_status = "invalid"
            self.error_rate_pct = 60.0
            log_event(
                service="config-service",
                severity="ERROR",
                event="INVALID_CONFIGURATION",
                message="Schema validation error in config v1.4.2: missing db.pool.min_idle",
                failure_type="configuration_failure",
                extra={"config_version": self.config_version}
            )

        elif fault_name == "persistent_data_mutation":
            self.db.connected = False
            self.error_rate_pct = 75.0
            log_event(
                service="database",
                severity="CRITICAL",
                event="PERSISTENT_DATA_MUTATION_RISK",
                message="Storage ledger desynchronization: uncommitted records detected in persistent database. Potential persistent data impact.",
                failure_type="persistent_data_mutation",
                extra={"table": "orders_ledger", "impact": "persistent_data"}
            )

        self._sync_legacy_system()
        return {
            "ok": True,
            "injected": fault_name,
            "active_faults": [k for k, v in self.faults.items() if v]
        }

    def clear_fault(self, fault_name: str) -> Dict[str, Any]:
        """Clears an individual fault and restores its baseline."""
        if fault_name not in self.faults:
            raise ValueError(f"Unknown fault: {fault_name}")

        self.faults[fault_name] = False

        if fault_name == "api_service_failure":
            self.service_status = "running"
            self.cpu_pct = 32.0
        elif fault_name == "database_connection_failure":
            self.db.connected = True
        elif fault_name == "persistent_data_mutation":
            self.db.connected = True
        elif fault_name == "high_memory_usage":
            self.memory_mb = 145.0
            self.memory_pct = 36.0
        elif fault_name == "slow_api_response":
            self.base_latency_ms = 22.0
        elif fault_name == "configuration_failure":
            self.config_status = "valid"

        # If no active faults remain, reset error rate
        if not any(self.faults.values()):
            self.error_rate_pct = 0.0

        log_event(
            service="autoheal-sandbox",
            severity="INFO",
            event="FAULT_CLEARED",
            message=f"Fault condition '{fault_name}' cleared. Restoring baseline parameters."
        )

        self._sync_legacy_system()
        return {
            "ok": True,
            "cleared": fault_name,
            "active_faults": [k for k, v in self.faults.items() if v]
        }

    def clear_all_faults(self) -> Dict[str, Any]:
        """Restores the sandbox application to pristine healthy state."""
        for fault in list(self.faults.keys()):
            self.faults[fault] = False

        self.service_status = "running"
        self.db.connected = True
        self.config_status = "valid"
        self.cpu_pct = 28.0
        self.memory_mb = 145.0
        self.memory_pct = 36.0
        self.error_rate_pct = 0.0
        self.base_latency_ms = 22.0

        log_event(
            service="autoheal-sandbox",
            severity="INFO",
            event="SYSTEM_RESET_HEALTHY",
            message="All faults cleared. Application restored to full healthy baseline."
        )

        self._sync_legacy_system()
        return {"ok": True, "status": "HEALTHY", "active_faults": []}

    # ------------------------------------------------------------------------
    # 1. HEALTH ENDPOINT
    # ------------------------------------------------------------------------

    def get_health(self) -> Dict[str, Any]:
        """
        Health endpoint (/health) logic.
        Evaluates subsystem invariants and computes health status.
        """
        service_up = (self.service_status == "running")
        db_up = self.db.ping()
        config_up = (self.config_status == "valid")
        memory_ok = not self.faults["high_memory_usage"]
        latency_ok = not self.faults["slow_api_response"]

        is_healthy = service_up and db_up and config_up and memory_ok and latency_ok

        # Determine overall status and HTTP code
        if not (service_up and db_up and config_up):
            overall_status = "DOWN"
            http_code = 503
        elif not (memory_ok and latency_ok):
            overall_status = "DEGRADED"
            http_code = 200
        else:
            overall_status = "UP"
            http_code = 200

        result = {
            "status": overall_status,
            "http_code": http_code,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "checks": {
                "service": "UP" if service_up else "DOWN",
                "database": "UP" if db_up else "DOWN",
                "config": "VALID" if config_up else "INVALID",
                "memory": "NORMAL" if memory_ok else "HIGH",
                "latency": "NORMAL" if latency_ok else "SLOW"
            },
            "metrics": {
                "cpu_pct": round(self.cpu_pct, 1),
                "memory_pct": round(self.memory_pct, 1),
                "memory_mb": round(self.memory_mb, 1),
                "error_rate_pct": round(self.error_rate_pct, 1),
                "latency_ms": round(self.base_latency_ms, 1)
            },
            "active_faults": [k for k, v in self.faults.items() if v]
        }

        if is_healthy:
            log_event(
                service="api-service",
                severity="INFO",
                event="HEALTH_CHECK_PASS",
                message=f"Health probe check passed. Status: {overall_status}"
            )
        else:
            log_event(
                service="api-service",
                severity="WARNING" if overall_status == "DEGRADED" else "ERROR",
                event="HEALTH_CHECK_FAIL",
                message=f"Health probe failed! Overall status: {overall_status}",
                failure_type="health_failure",
                extra={"checks": result["checks"]}
            )

        return result

    # ------------------------------------------------------------------------
    # 2. MAIN API ENDPOINT (/api/orders)
    # ------------------------------------------------------------------------

    def handle_api_request(self, endpoint: str = "/api/orders", method: str = "GET") -> Dict[str, Any]:
        """
        Main API endpoint logic.
        Executes business workflow including database interaction and latency simulation.
        """
        self.total_requests += 1

        # Check 1: API Service Outage
        if self.service_status != "running" or self.faults["api_service_failure"]:
            self.error_count += 1
            log_event(
                service="api-service",
                severity="ERROR",
                event="API_REQUEST_FAILED",
                message=f"{method} {endpoint} failed: Connection refused on port 8080 (Service is down)",
                failure_type="api_service_failure",
                extra={"endpoint": endpoint, "http_code": 503}
            )
            return {
                "ok": False,
                "http_code": 503,
                "error": "Service Unavailable: API service is not responding",
                "endpoint": endpoint
            }

        # Check 2: Configuration Failure
        if self.config_status != "valid" or self.faults["configuration_failure"]:
            self.error_count += 1
            log_event(
                service="config-service",
                severity="ERROR",
                event="API_CONFIG_ERROR",
                message=f"{method} {endpoint} failed: Missing database pool configuration parameter",
                failure_type="configuration_failure",
                extra={"endpoint": endpoint, "http_code": 500}
            )
            return {
                "ok": False,
                "http_code": 500,
                "error": "Internal Server Error: Application configuration validation failure",
                "endpoint": endpoint
            }

        # Check 3: Simulated Slow Latency
        effective_latency_ms = self.base_latency_ms
        if self.faults["slow_api_response"]:
            # Inject a controlled 1.2s delay for slow response simulation
            time.sleep(1.2)
            effective_latency_ms = round(random.uniform(2200.0, 2600.0), 2)
            log_event(
                service="api-service",
                severity="WARNING",
                event="SLOW_API_LATENCY",
                message=f"{method} {endpoint} processed with degraded latency: {effective_latency_ms}ms",
                failure_type="slow_api_response",
                extra={"latency_ms": effective_latency_ms}
            )

        # Check 4: Memory Pressure Alert
        if self.faults["high_memory_usage"]:
            log_event(
                service="system-monitor",
                severity="WARNING",
                event="HIGH_MEMORY_PRESSURE",
                message=f"Memory footprint at {self.memory_pct}% during request execution",
                failure_type="high_memory_usage"
            )

        # Check 5: Database Interaction
        try:
            db_result = self.db.query("orders")
        except ConnectionError as e:
            self.error_count += 1
            log_event(
                service="database",
                severity="ERROR",
                event="DB_QUERY_FAILED",
                message=f"{method} {endpoint} failed: {str(e)}",
                failure_type="database_connection_failure",
                extra={"endpoint": endpoint, "http_code": 504}
            )
            return {
                "ok": False,
                "http_code": 504,
                "error": str(e),
                "endpoint": endpoint
            }

        # Success Response
        log_event(
            service="api-service",
            severity="INFO",
            event="API_REQUEST_SUCCESS",
            message=f"{method} {endpoint} executed successfully: {db_result['count']} records retrieved ({effective_latency_ms}ms)",
            extra={"endpoint": endpoint, "http_code": 200, "rows": db_result["count"]}
        )

        return {
            "ok": True,
            "http_code": 200,
            "endpoint": endpoint,
            "latency_ms": effective_latency_ms,
            "data": {
                "orders": db_result["rows"],
                "count": db_result["count"]
            }
        }

    # ------------------------------------------------------------------------
    # 5. DETAILED SERVICE STATUS
    # ------------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive diagnostic status of all subsystems."""
        uptime = round(time.time() - self.start_time, 1)
        return {
            "application": "AutoHeal Sandbox Microservice",
            "uptime_seconds": uptime,
            "subsystems": {
                "service": self.service_status,
                "database": "connected" if self.db.connected else "disconnected",
                "config": self.config_status,
                "config_version": self.config_version
            },
            "metrics": {
                "cpu_pct": round(self.cpu_pct, 1),
                "memory_pct": round(self.memory_pct, 1),
                "memory_mb": round(self.memory_mb, 1),
                "error_rate_pct": round(self.error_rate_pct, 1),
                "latency_ms": round(self.base_latency_ms, 1)
            },
            "counters": {
                "total_requests": self.total_requests,
                "error_count": self.error_count
            },
            "active_faults": [k for k, v in self.faults.items() if v]
        }


# ============================================================================
# SINGLETON INSTANCE HELPER
# ============================================================================

_global_sandbox_app: Optional[SandboxApp] = None

def get_default_app() -> SandboxApp:
    """Returns or initializes the global singleton SandboxApp instance."""
    global _global_sandbox_app
    if _global_sandbox_app is None:
        _global_sandbox_app = SandboxApp()
    return _global_sandbox_app


# ============================================================================
# BUILT-IN LIGHTWEIGHT HTTP SERVER
# ============================================================================

class SandboxHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler routing requests to the global SandboxApp instance."""

    app_instance: Optional[SandboxApp] = None

    def log_message(self, format, *args):
        # Suppress default noisy stdio logging from http.server
        pass

    def _get_app(self) -> SandboxApp:
        if SandboxHTTPHandler.app_instance is not None:
            return SandboxHTTPHandler.app_instance
        return get_default_app()

    def _send_json(self, status_code: int, data: Dict[str, Any]):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        app = self._get_app()

        if self.path == "/health":
            health = app.get_health()
            self._send_json(health["http_code"], health)
        elif self.path in ("/api/orders", "/api/data"):
            resp = app.handle_api_request(endpoint=self.path, method="GET")
            self._send_json(resp["http_code"], resp)
        elif self.path == "/status":
            self._send_json(200, app.get_status())
        elif self.path == "/api/simulator/state":
            active_scenarios = [k for k, v in app.faults.items() if v]
            self._send_json(200, {
                "health": app.get_health(),
                "status": app.get_status(),
                "active_faults": active_scenarios
            })
        elif self.path == "/api/simulator/scenarios":
            try:
                import fault_simulator
                self._send_json(200, {"scenarios": fault_simulator.get_available_scenarios()})
            except Exception:
                self._send_json(200, {"faults": list(app.faults.keys())})
        else:
            self._send_json(404, {"error": f"Endpoint not found: {self.path}"})

    def do_POST(self):
        app = self._get_app()

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if self.path in ("/simulate_fault", "/api/simulator/trigger"):
            fault = payload.get("fault") or payload.get("type")
            try:
                try:
                    import fault_simulator
                    res = fault_simulator.trigger_failure(fault, app=app)
                except Exception:
                    res = app.inject_fault(fault)
                self._send_json(200, res)
            except Exception as e:
                self._send_json(400, {"error": str(e)})

        elif self.path in ("/clear_fault", "/api/simulator/reset"):
            fault = payload.get("fault") or payload.get("type")
            try:
                try:
                    import fault_simulator
                    res = fault_simulator.reset_failure(fault, app=app)
                except Exception:
                    res = app.clear_fault(fault)
                self._send_json(200, res)
            except Exception as e:
                self._send_json(400, {"error": str(e)})

        elif self.path in ("/reset", "/api/simulator/reset_all"):
            res = app.clear_all_faults()
            self._send_json(200, res)

        else:
            self._send_json(404, {"error": f"Endpoint not found: {self.path}"})


def run_server(port: int = 8000, app: Optional[SandboxApp] = None) -> HTTPServer:
    """Starts a local HTTP server exposing the sandbox application."""
    if app is None:
        app = get_default_app()
    SandboxHTTPHandler.app_instance = app
    server = HTTPServer(("127.0.0.1", port), SandboxHTTPHandler)
    print(f"\n[SERVER] Sandbox HTTP Server running on http://127.0.0.1:{port}")
    print("Available endpoints:")
    print("  GET  /health")
    print("  GET  /api/orders")
    print("  GET  /status")
    print("  GET  /api/simulator/state")
    print("  GET  /api/simulator/scenarios")
    print("  POST /api/simulator/trigger  {\"type\": \"API_DOWN\"}")
    print("  POST /api/simulator/reset    {\"type\": \"API_DOWN\"}")
    print("  POST /api/simulator/reset_all")
    return server


# ============================================================================
# SELF-TEST & VERIFICATION ROUTINE
# ============================================================================

def verify_sandbox_demo():
    """Verifies all required functionality: health, API, logging, and simulated faults."""
    print("\n" + "=" * 60)
    print("[TEST] AUTOHEAL DEMO APPLICATION - VERIFICATION TEST")
    print("=" * 60)

    app = SandboxApp()

    # 1. Normal Health Check
    print("\n--- [1] Testing Normal Health Check ---")
    health = app.get_health()
    print(f"Status Code: {health['http_code']}, Health Status: {health['status']}")
    assert health["http_code"] == 200, "Normal health check must return HTTP 200"
    assert health["status"] == "UP", "Normal status must be UP"

    # 2. Normal Main API Request
    print("\n--- [2] Testing Normal API Request (/api/orders) ---")
    api_resp = app.handle_api_request()
    print(f"Status Code: {api_resp['http_code']}, Orders retrieved: {api_resp['data']['count']}")
    assert api_resp["http_code"] == 200, "Normal API request must return HTTP 200"
    assert api_resp["data"]["count"] > 0, "Orders count must be > 0"

    # 3. Service Status
    print("\n--- [3] Testing Service Status Inspection ---")
    status = app.get_status()
    print(f"Service: {status['subsystems']['service']}, Database: {status['subsystems']['database']}")

    # 4. Verify Log File Generation
    print("\n--- [4] Verifying Structured Log Output ---")
    assert LOG_FILE.exists(), "Log file must exist"
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
    print(f"Total log lines in {LOG_FILE}: {len(lines)}")
    latest_entry = json.loads(lines[-1])
    print(f"Latest log entry: {latest_entry}")
    assert "timestamp" in latest_entry, "Log entry must contain timestamp"
    assert "service" in latest_entry, "Log entry must contain service"
    assert "severity" in latest_entry, "Log entry must contain severity"
    assert "event" in latest_entry, "Log entry must contain event"
    assert "message" in latest_entry, "Log entry must contain message"

    # 5. Safe Fault Simulation Tests
    print("\n--- [5] Testing Safe Fault Simulations ---")

    # Fault A: Database Connection Failure
    print("\n  >> Testing Database Failure Simulation:")
    app.inject_fault("database_connection_failure")
    db_health = app.get_health()
    db_api = app.handle_api_request()
    print(f"  Health under DB fault: {db_health['status']} (HTTP {db_health['http_code']})")
    print(f"  API response under DB fault: HTTP {db_api['http_code']} ({db_api['error']})")
    assert db_api["http_code"] == 504, "API under DB fault must return 504"

    # Reset
    app.clear_all_faults()

    # Fault B: API Service Failure
    print("\n  >> Testing API Service Failure Simulation:")
    app.inject_fault("api_service_failure")
    api_health = app.get_health()
    api_fail = app.handle_api_request()
    print(f"  Health under Service fault: {api_health['status']} (HTTP {api_health['http_code']})")
    print(f"  API response under Service fault: HTTP {api_fail['http_code']} ({api_fail['error']})")
    assert api_fail["http_code"] == 503, "API under service fault must return 503"

    # Fault C: High Memory Usage Simulation
    print("\n  >> Testing High Memory Simulation:")
    app.clear_all_faults()
    app.inject_fault("high_memory_usage")
    mem_health = app.get_health()
    print(f"  Health under High Memory fault: {mem_health['status']}, Memory: {mem_health['metrics']['memory_pct']}%")
    assert mem_health["metrics"]["memory_pct"] > 90.0, "Memory must be > 90%"

    # Fault D: Slow API Response Simulation
    print("\n  >> Testing Slow API Response Simulation:")
    app.clear_all_faults()
    app.inject_fault("slow_api_response")
    slow_resp = app.handle_api_request()
    print(f"  Latency under Slow Response fault: {slow_resp['latency_ms']}ms")
    assert slow_resp["latency_ms"] > 2000.0, "Latency must be > 2000ms"

    # Fault E: Configuration Failure Simulation
    print("\n  >> Testing Configuration Failure Simulation:")
    app.clear_all_faults()
    app.inject_fault("configuration_failure")
    cfg_health = app.get_health()
    cfg_api = app.handle_api_request()
    print(f"  Health under Config fault: {cfg_health['status']} (HTTP {cfg_health['http_code']})")
    print(f"  API response under Config fault: HTTP {cfg_api['http_code']} ({cfg_api['error']})")
    assert cfg_api["http_code"] == 500, "API under config fault must return 500"

    # Final Reset
    app.clear_all_faults()
    final_health = app.get_health()
    assert final_health["status"] == "UP", "Final health check must return UP"

    print("\n" + "=" * 60)
    print("[SUCCESS] ALL VERIFICATION TESTS PASSED PERFECTLY!")
    print("=" * 60)


if __name__ == "__main__":
    import sys
    if "--server" in sys.argv:
        server = run_server()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server.")
            server.server_close()
    else:
        verify_sandbox_demo()
