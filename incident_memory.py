"""
AutoHeal AI - Incident Memory & Retrieval Engine
Stores historical incident post-mortems and retrieves historical context
for few-shot diagnostic reasoning and repair success rate calculation.

Stored Fields:
  - incident_id
  - failure_type
  - root_cause
  - evidence
  - selected_repair
  - risk_score
  - sandbox_result
  - recovery_result
  - recovery_time
  - success (True/False)

Safety & Prioritization Guarantee:
  - Historical data provides supplementary supporting evidence.
  - Current physical diagnostic evidence ALWAYS takes strict priority.
"""

import sys
import json
import time
import sqlite3
from typing import Dict, Any, List, Optional
from pathlib import Path

# Safe console reconfigure for Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DB_PATH = Path("logs") / "incident_memory.db"
JSON_BACKUP = Path("logs") / "incident_memory.json"
DB_PATH.parent.mkdir(exist_ok=True)


# ============================================================================
# INCIDENT MEMORY DATABASE (SQLITE + JSON SYNC)
# ============================================================================

class IncidentMemory:
    """
    Local database managing historical incident records, retrieval,
    and empirical repair success rate calculation.
    """

    def __init__(self, db_path: Path = DB_PATH, json_backup: Path = JSON_BACKUP):
        self.db_path = db_path
        self.json_backup = json_backup
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Initializes SQLite schema."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS incident_memory (
                    incident_id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    failure_type TEXT,
                    root_cause TEXT,
                    evidence TEXT,
                    selected_repair TEXT,
                    risk_score INTEGER,
                    sandbox_result TEXT,
                    recovery_result TEXT,
                    recovery_time REAL,
                    success INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_failure_type ON incident_memory (failure_type)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS approval_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    incident_id TEXT,
                    approver TEXT,
                    timestamp TEXT,
                    decision TEXT,
                    repair TEXT,
                    risk_level TEXT,
                    risk_score INTEGER,
                    result TEXT
                )
            """)
            conn.commit()

    def _sync_to_json(self):
        """Synchronizes SQLite database to human-readable JSON backup."""
        all_records = self.get_all_history()
        try:
            with open(self.json_backup, "w", encoding="utf-8") as f:
                json.dump(all_records, f, indent=2)
        except Exception:
            pass

    def save_incident(
        self,
        incident_id: str,
        failure_type: str,
        root_cause: str,
        evidence: List[str],
        selected_repair: str,
        risk_score: int,
        sandbox_result: str,
        recovery_result: str,
        recovery_time: float,
        success: bool,
        timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """Stores a completed incident record in persistent memory."""
        now = timestamp or time.strftime("%Y-%m-%d %H:%M:%S")
        evidence_json = json.dumps(evidence)
        success_int = 1 if success else 0

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO incident_memory (
                    incident_id, timestamp, failure_type, root_cause,
                    evidence, selected_repair, risk_score, sandbox_result,
                    recovery_result, recovery_time, success
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                incident_id, now, failure_type, root_cause,
                evidence_json, selected_repair, risk_score, sandbox_result,
                recovery_result, recovery_time, success_int
            ))
            conn.commit()

        self._sync_to_json()

        print(f"[MEMORY SAVED] Stored {incident_id} ({failure_type}) - Repair: {selected_repair} - Success: {success}")

        return {
            "incident_id": incident_id,
            "failure_type": failure_type,
            "selected_repair": selected_repair,
            "success": success
        }

    def record_approval(
        self,
        incident_id: str,
        approver: str,
        decision: str,
        repair: str,
        risk_level: str,
        risk_score: int,
        result: str,
        timestamp: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records a human approval or rejection decision into the audit log."""
        now = timestamp or time.strftime("%Y-%m-%d %H:%M:%S")
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO approval_audit_log (
                    incident_id, approver, timestamp, decision, repair,
                    risk_level, risk_score, result
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                incident_id, approver, now, decision, repair,
                risk_level, risk_score, result
            ))
            conn.commit()

        audit_entry = {
            "incident_id": incident_id,
            "approver": approver,
            "timestamp": now,
            "decision": decision,
            "repair": repair,
            "risk_level": risk_level,
            "risk_score": risk_score,
            "result": result
        }

        # Backup to JSON
        try:
            audit_json_path = Path("logs") / "approval_audit.json"
            all_audits = self.get_approval_audit_trail(100)
            with open(audit_json_path, "w", encoding="utf-8") as f:
                json.dump(all_audits, f, indent=2)
        except Exception:
            pass

        print(f"[AUDIT LOG] Decision: {decision} by '{approver}' on {incident_id} (Repair: {repair}) -> {result}")
        return audit_entry

    def get_approval_audit_trail(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Queries the persistent approval audit log."""
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM approval_audit_log
                ORDER BY id DESC
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]

    def search_similar_incidents(
        self,
        failure_type: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Retrieves matching historical incidents, calculates repair success rates,
        and provides supporting evidence for the diagnosis engine.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT * FROM incident_memory
                WHERE failure_type = ?
                ORDER BY timestamp DESC, rowid DESC
                LIMIT ?
            """, (failure_type, limit))
            rows = cursor.fetchall()

        similar_records: List[Dict[str, Any]] = []
        repair_stats: Dict[str, Dict[str, Any]] = {}

        for row in rows:
            rec = dict(row)
            try:
                rec["evidence"] = json.loads(rec["evidence"])
            except Exception:
                rec["evidence"] = [rec["evidence"]]
            rec["success"] = bool(rec["success"])
            similar_records.append(rec)

            repair = rec["selected_repair"]
            if repair not in repair_stats:
                repair_stats[repair] = {"attempts": 0, "successes": 0, "success_rate": 0.0}

            repair_stats[repair]["attempts"] += 1
            if rec["success"]:
                repair_stats[repair]["successes"] += 1

        match_count = len(similar_records)

        # Calculate success rates per repair
        best_repair = None
        best_rate = 0.0
        for repair, stats in repair_stats.items():
            stats["success_rate"] = round((stats["successes"] / stats["attempts"]) * 100, 1)
            if stats["success_rate"] >= best_rate:
                best_rate = stats["success_rate"]
                best_repair = repair

        # Format standardized summary string
        if match_count > 0 and best_repair:
            summary = (
                f"{match_count} similar incidents found for '{failure_type}'. "
                f"Previous repair: '{best_repair}'. Success rate: {best_rate}% ({repair_stats[best_repair]['successes']}/{repair_stats[best_repair]['attempts']})."
            )
        else:
            summary = f"No previous historical incidents found for '{failure_type}'."

        return {
            "failure_type": failure_type,
            "match_count": match_count,
            "count": match_count,
            "has_history": match_count > 0,
            "best_repair": best_repair,
            "best_success_rate": best_rate,
            "repair_stats": repair_stats,
            "formatted_summary": summary,
            "memory_insight": summary,
            "historical_records": similar_records
        }

    def get_all_history(self) -> List[Dict[str, Any]]:
        """Returns all historical incidents."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM incident_memory ORDER BY timestamp DESC, rowid DESC")
            rows = cursor.fetchall()

        records = []
        for row in rows:
            rec = dict(row)
            try:
                rec["evidence"] = json.loads(rec["evidence"])
            except Exception:
                rec["evidence"] = [rec["evidence"]]
            rec["success"] = bool(rec["success"])
            records.append(rec)
        return records

    get_all_incidents = get_all_history

    def seed_initial_history(self):
        """
        Pre-populates realistic SRE incident history for instant demonstration.
        Includes 8 previous API_DOWN incidents with an 87.5% success rate for restart_service.
        """
        # Clear existing to prevent duplicate seeding
        self.clear_history()

        seed_data = [
            # 8 historical API_DOWN incidents (7 successes, 1 failure = 87.5% success rate)
            ("INC-0981", "API_DOWN", "Port 8080 listener crashed", ["Connection refused on port 8080"], "restart_service", 10, "PASSED", "SUCCESS", 1.8, True, "2026-10-01 10:14:02"),
            ("INC-0984", "API_DOWN", "API worker deadlock", ["Health probe failed 503"], "restart_service", 10, "PASSED", "SUCCESS", 2.1, True, "2026-10-02 14:22:15"),
            ("INC-0988", "API_DOWN", "Port connection timeout", ["Error rate 85%"], "restart_service", 10, "PASSED", "SUCCESS", 1.9, True, "2026-10-03 09:05:40"),
            ("INC-0990", "API_DOWN", "Uncaught exception exit", ["Service down log"], "restart_service", 10, "PASSED", "SUCCESS", 2.0, True, "2026-10-04 18:44:11"),
            ("INC-0992", "API_DOWN", "API Gateway segfault", ["Socket closed abruptly"], "restart_service", 10, "PASSED", "SUCCESS", 1.7, True, "2026-10-05 11:30:00"),
            ("INC-0995", "API_DOWN", "Port 8080 binding error", ["API process crashed"], "restart_service", 10, "PASSED", "SUCCESS", 1.9, True, "2026-10-06 08:15:33"),
            ("INC-0997", "API_DOWN", "Memory exhaustion crash", ["OOM worker termination"], "restart_service", 10, "PASSED", "SUCCESS", 2.2, True, "2026-10-07 16:20:45"),
            ("INC-0999", "API_DOWN", "Network driver failure", ["Underlying host socket down"], "restart_service", 10, "FAILED", "FAILED", 4.5, False, "2026-10-07 22:10:12"),

            # 4 historical DATABASE_DOWN incidents (100% success for repair_database)
            ("INC-0970", "DATABASE_DOWN", "Connection pool exhausted", ["DB timeout 5000ms"], "repair_database", 65, "PASSED", "SUCCESS", 3.2, True, "2026-09-28 13:00:00"),
            ("INC-0975", "DATABASE_DOWN", "PostgreSQL pool leak", ["Query failed pool exhausted"], "repair_database", 65, "PASSED", "SUCCESS", 2.9, True, "2026-09-29 17:15:00"),
            ("INC-0979", "DATABASE_DOWN", "Socket timeout to 5432", ["Health probe failed"], "repair_database", 65, "PASSED", "SUCCESS", 3.1, True, "2026-09-30 04:30:00"),
            ("INC-0985", "DATABASE_DOWN", "Transient connection timeout", ["OperationalError timeout"], "repair_database", 65, "PASSED", "SUCCESS", 2.8, True, "2026-10-02 19:40:00"),

            # 3 historical CONFIG_ERROR incidents (100% success for rollback_config)
            ("INC-0960", "CONFIG_ERROR", "Missing config parameter", ["Schema validation failed"], "rollback_config", 35, "PASSED", "SUCCESS", 2.4, True, "2026-09-25 08:00:00"),
            ("INC-0965", "CONFIG_ERROR", "Invalid YAML syntax", ["Config validation error"], "rollback_config", 35, "PASSED", "SUCCESS", 2.1, True, "2026-09-26 12:10:00"),
            ("INC-0972", "CONFIG_ERROR", "Corrupted DB connection string", ["Config INVALID"], "rollback_config", 35, "PASSED", "SUCCESS", 2.3, True, "2026-09-28 15:45:00")
        ]

        with self._get_connection() as conn:
            for item in seed_data:
                conn.execute("""
                    INSERT OR REPLACE INTO incident_memory (
                        incident_id, failure_type, root_cause, evidence,
                        selected_repair, risk_score, sandbox_result,
                        recovery_result, recovery_time, success, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item[0], item[1], item[2], json.dumps(item[3]),
                    item[4], item[5], item[6], item[7], item[8], 1 if item[9] else 0, item[10]
                ))
            conn.commit()

        self._sync_to_json()
        print(f"[MEMORY SEED] Seeded {len(seed_data)} historical incidents into memory.")

    def clear_history(self):
        """Clears all records from database and JSON backup."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM incident_memory")
            conn.commit()
        if self.json_backup.exists():
            self.json_backup.unlink()


# Singleton global instance
_global_incident_memory: Optional[IncidentMemory] = None

def get_incident_memory() -> IncidentMemory:
    global _global_incident_memory
    if _global_incident_memory is None:
        _global_incident_memory = IncidentMemory()
        # Seed initial history if empty
        if len(_global_incident_memory.get_all_history()) == 0:
            _global_incident_memory.seed_initial_history()
    return _global_incident_memory


# ============================================================================
# SELF-TEST & VERIFICATION
# ============================================================================

def verify_incident_memory():
    print("\n" + "=" * 70)
    print("[TEST] AUTOHEAL INCIDENT MEMORY TEST SUITE")
    print("=" * 70)

    memory = IncidentMemory(
        db_path=Path("logs") / "test_memory.db",
        json_backup=Path("logs") / "test_memory.json"
    )

    # 1. Seed historical data
    print("\n--- [1] Seeding Historical Data ---")
    memory.seed_initial_history()
    all_history = memory.get_all_history()
    print(f"Total historical incidents in memory: {len(all_history)}")
    assert len(all_history) == 15, "Must have seeded 15 historical incidents"

    # 2. Search for similar API_DOWN incidents
    print("\n--- [2] Searching Similar Incidents for 'API_DOWN' ---")
    query_res = memory.search_similar_incidents("API_DOWN")
    print(f"Formatted Summary:\n  >> {query_res['formatted_summary']}")

    assert query_res["match_count"] == 8, f"Must find 8 similar incidents, got {query_res['match_count']}"
    assert query_res["best_repair"] == "restart_service"
    assert query_res["best_success_rate"] == 87.5, f"Success rate must be 87.5%, got {query_res['best_success_rate']}"
    assert "8 similar incidents found" in query_res["formatted_summary"]
    assert "Success rate: 87.5%" in query_res["formatted_summary"]
    print("  -> Exact 87.5% success rate for restart_service on 8 incidents verified! [PASSED]")

    # 3. Search for DATABASE_DOWN incidents
    print("\n--- [3] Searching Similar Incidents for 'DATABASE_DOWN' ---")
    db_res = memory.search_similar_incidents("DATABASE_DOWN")
    print(f"Formatted Summary:\n  >> {db_res['formatted_summary']}")
    assert db_res["match_count"] == 4
    assert db_res["best_repair"] == "repair_database"
    assert db_res["best_success_rate"] == 100.0
    print("  -> 100% success rate on 4 database incidents verified! [PASSED]")

    # 4. Save a new incident and verify persistence
    print("\n--- [4] Storing a New Incident Record ---")
    new_inc = memory.save_incident(
        incident_id="INC-1050",
        failure_type="API_DOWN",
        root_cause="Port 8080 listener crash",
        evidence=["Port 8080 refused"],
        selected_repair="restart_service",
        risk_score=0,
        sandbox_result="PASSED",
        recovery_result="SUCCESS",
        recovery_time=1.5,
        success=True
    )
    # Check count updated (8 + 1 = 9)
    query_after = memory.search_similar_incidents("API_DOWN")
    assert query_after["match_count"] == 9
    assert query_after["repair_stats"]["restart_service"]["attempts"] == 9
    print(f"Updated stats after new incident: {query_after['repair_stats']['restart_service']}")
    print("  -> Real-time history update verified! [PASSED]")

    # Clean up test database
    memory.clear_history()

    print("\n" + "=" * 70)
    print("[SUCCESS] INCIDENT MEMORY ENGINE FULLY VERIFIED!")
    print("=" * 70)


if __name__ == "__main__":
    verify_incident_memory()
