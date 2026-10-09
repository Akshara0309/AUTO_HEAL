"""
AutoHeal AI - Incident Management Layer
Manages the lifecycle, tracking, state machine, and persistence of system incidents.

Statuses:
  DETECTED -> INVESTIGATING -> DIAGNOSED -> REPAIR_PROPOSED ->
  VALIDATING -> HEALING -> VERIFYING -> RESOLVED (or ESCALATED)

Severities:
  LOW, MEDIUM, HIGH, CRITICAL
"""

import sys
import json
import time
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict

# Safe console reconfigure for Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

INCIDENTS_FILE = Path("logs") / "incidents.json"
INCIDENTS_FILE.parent.mkdir(exist_ok=True)


# ============================================================================
# ENUMS
# ============================================================================

class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSED = "DIAGNOSED"
    REPAIR_PROPOSED = "REPAIR_PROPOSED"
    VALIDATING = "VALIDATING"
    HEALING = "HEALING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    ESCALATED = "ESCALATED"


class IncidentSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ============================================================================
# INCIDENT DATA MODEL
# ============================================================================

@dataclass
class Incident:
    id: str
    timestamp: str
    service: str
    failure_type: str
    severity: str
    status: str
    description: str
    logs: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    affected_component: str = ""
    timeline: List[Dict[str, Any]] = field(default_factory=list)
    resolution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Incident":
        return cls(**data)


# ============================================================================
# INCIDENT MANAGER
# ============================================================================

class IncidentManager:
    """Manages creation, state progression, and persistence of incidents."""

    def __init__(self, persistence_file: Path = INCIDENTS_FILE):
        self.persistence_file = persistence_file
        self.incidents: Dict[str, Incident] = {}
        self._counter = 1000
        self._load_from_disk()

    def _generate_id(self) -> str:
        self._counter += 1
        return f"INC-{self._counter}"

    def _persist(self):
        """Saves all incidents to disk."""
        data = {inc_id: inc.to_dict() for inc_id, inc in self.incidents.items()}
        try:
            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[WARN] Failed to persist incidents: {e}")

    def _load_from_disk(self):
        """Loads incidents from disk if available."""
        if not self.persistence_file.exists():
            return
        try:
            with open(self.persistence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for inc_id, inc_dict in data.items():
                self.incidents[inc_id] = Incident.from_dict(inc_dict)
                # Keep counter ahead of highest ID
                try:
                    num = int(inc_id.split("-")[-1])
                    if num >= self._counter:
                        self._counter = num
                except Exception:
                    pass
        except Exception as e:
            print(f"[WARN] Failed to load incidents from disk: {e}")

    def create_incident(
        self,
        service: str,
        failure_type: str,
        severity: str,
        description: str,
        affected_component: str = "Core Subsystem",
        logs: Optional[List[Dict[str, Any]]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        deduplicate: bool = True
    ) -> Incident:
        """
        Creates a new incident with status DETECTED.
        If deduplicate=True and an active incident for this failure_type exists, updates and returns it.
        """
        if deduplicate:
            existing = self.find_active_by_failure_type(failure_type)
            if existing is not None:
                # Update existing active incident with fresh telemetry
                existing.logs = logs or existing.logs
                existing.metrics = metrics or existing.metrics
                existing.timeline.append({
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "status": existing.status,
                    "event": "INCIDENT_REFRESHED",
                    "note": "Telemetric symptoms re-verified while incident active."
                })
                self._persist()
                return existing

        inc_id = self._generate_id()
        now = time.strftime("%Y-%m-%d %H:%M:%S")

        # Validate enums
        valid_status = IncidentStatus.DETECTED.value
        valid_severity = severity if severity in [s.value for s in IncidentSeverity] else IncidentSeverity.HIGH.value

        incident = Incident(
            id=inc_id,
            timestamp=now,
            service=service,
            failure_type=failure_type,
            severity=valid_severity,
            status=valid_status,
            description=description,
            logs=logs or [],
            metrics=metrics or {},
            affected_component=affected_component,
            timeline=[
                {
                    "timestamp": now,
                    "status": valid_status,
                    "event": "INCIDENT_CREATED",
                    "note": f"Incident {inc_id} automatically created by Monitoring engine."
                }
            ]
        )

        self.incidents[inc_id] = incident
        self._persist()

        print(f"\n[INCIDENT DETECTED] {inc_id} [{incident.severity}] {incident.service} - {incident.failure_type}")
        print(f"  Description: {incident.description}")
        print(f"  Affected: {incident.affected_component}")

        return incident

    def update_status(self, incident_id: str, new_status: IncidentStatus, note: Optional[str] = None) -> Optional[Incident]:
        """Transitions an incident to a new lifecycle status."""
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        status_value = new_status.value if isinstance(new_status, IncidentStatus) else str(new_status)
        incident.status = status_value
        incident.timeline.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": status_value,
            "event": "STATUS_CHANGED",
            "note": note or f"Status transitioned to {status_value}."
        })
        self._persist()
        return incident

    def resolve_incident(self, incident_id: str, resolution_summary: str) -> Optional[Incident]:
        """Marks an incident as RESOLVED with resolution details."""
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        incident.status = IncidentStatus.RESOLVED.value
        incident.resolution = resolution_summary
        incident.timeline.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": IncidentStatus.RESOLVED.value,
            "event": "INCIDENT_RESOLVED",
            "note": resolution_summary
        })
        self._persist()
        print(f"\n[INCIDENT RESOLVED] {incident_id} - {resolution_summary}")
        return incident

    def escalate_incident(self, incident_id: str, reason: str) -> Optional[Incident]:
        """Escalates an incident for human operator intervention."""
        incident = self.incidents.get(incident_id)
        if not incident:
            return None

        incident.status = IncidentStatus.ESCALATED.value
        incident.timeline.append({
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": IncidentStatus.ESCALATED.value,
            "event": "HUMAN_ESCALATION",
            "note": reason
        })
        self._persist()
        print(f"\n[INCIDENT ESCALATED] {incident_id} - Paging Human Operator! Reason: {reason}")
        return incident

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        return self.incidents.get(incident_id)

    def get_all_incidents(self) -> List[Incident]:
        return list(self.incidents.values())

    def get_active_incidents(self) -> List[Incident]:
        """Returns incidents that are not yet RESOLVED."""
        return [
            inc for inc in self.incidents.values()
            if inc.status != IncidentStatus.RESOLVED.value
        ]

    def find_active_by_failure_type(self, failure_type: str) -> Optional[Incident]:
        """Returns an active incident matching the given failure type if one exists."""
        for inc in self.get_active_incidents():
            if inc.failure_type == failure_type:
                return inc
        return None

    def clear_all(self):
        """Clears all incidents from memory and disk (for testing)."""
        self.incidents.clear()
        self._counter = 1000
        if self.persistence_file.exists():
            self.persistence_file.unlink()


# Singleton global manager instance
_global_incident_manager: Optional[IncidentManager] = None

def get_incident_manager() -> IncidentManager:
    global _global_incident_manager
    if _global_incident_manager is None:
        _global_incident_manager = IncidentManager()
    return _global_incident_manager
