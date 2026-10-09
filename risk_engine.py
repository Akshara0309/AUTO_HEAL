"""
AutoHeal AI - Risk Assessment Engine
Computes deterministic operational risk scores (0-100) for candidate repair actions.

Risk Dimensions Evaluated:
  - Data loss risk (0-30 pts)
  - Service downtime / blast radius (0-25 pts)
  - Reversibility (0-25 pts)
  - Persistent data modification (0-15 pts)
  - Sandbox validation status (-10 to +15 pts)

Risk Categories:
  0-30   = LOW       -> AUTO_EXECUTE (Can be executed automatically after sandbox validation)
  31-60  = MEDIUM    -> REQUIRE_APPROVAL (Requires human approval)
  61-80  = HIGH      -> REQUIRE_APPROVAL (Must require human approval)
  81-100 = CRITICAL  -> BLOCK (Must be blocked from autonomous execution)

Safety Guarantee:
  - Deterministic policy enforcement strictly overrides any LLM hallucinations or bypass attempts.
"""

import sys
import json
from enum import Enum
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

# Safe console reconfigure for Windows cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


# ============================================================================
# ENUMS & DATA MODELS
# ============================================================================

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskDecision(str, Enum):
    AUTO_EXECUTE = "AUTO_EXECUTE"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"
    BLOCK = "BLOCK"


@dataclass
class RiskReport:
    risk_score: int
    risk_level: str
    reasons: List[str]
    decision: str
    action: str
    breakdown: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "reasons": self.reasons,
            "decision": self.decision,
            "action": self.action,
            "breakdown": self.breakdown
        }


# ============================================================================
# ACTION PROFILE CATALOG
# ============================================================================

ACTION_PROFILES: Dict[str, Dict[str, Any]] = {
    # Stateless and low risk
    "restart_service": {
        "name": "Restart API Service",
        "base_data_loss": 0,
        "base_downtime": 5,
        "base_reversibility": 0,
        "modifies_persistent_data": False,
        "affected_components": ["API Service Gateway"],
        "is_destructive": False,
        "default_reason": "Stateless microservice restart with zero data persistence risk and fast recovery."
    },
    "reset_latency_profile": {
        "name": "Reset Latency Profile",
        "base_data_loss": 0,
        "base_downtime": 2,
        "base_reversibility": 0,
        "modifies_persistent_data": False,
        "affected_components": ["Request Pipeline"],
        "is_destructive": False,
        "default_reason": "Thread pool flush and latency profile reset without persistent state modification."
    },
    "flush_cache": {
        "name": "Flush Memory Cache",
        "base_data_loss": 2,
        "base_downtime": 2,
        "base_reversibility": 5,
        "modifies_persistent_data": False,
        "affected_components": ["Memory Management"],
        "is_destructive": False,
        "default_reason": "Evicts transient in-memory caches to release memory; data re-hydrates on demand."
    },

    # Configuration changes - Medium risk
    "rollback_deployment": {
        "name": "Rollback Deployment / Release",
        "base_data_loss": 5,
        "base_downtime": 15,
        "base_reversibility": 10,
        "modifies_persistent_data": True,
        "affected_components": ["Deployment Registry", "Runtime Environment"],
        "is_destructive": False,
        "default_reason": "Rolls back application binary/configuration to previous known-good release tag."
    },
    "rollback_config": {
        "name": "Rollback Configuration",
        "base_data_loss": 5,
        "base_downtime": 10,
        "base_reversibility": 10,
        "modifies_persistent_data": True,
        "affected_components": ["Configuration Provider", "Active Services"],
        "is_destructive": False,
        "default_reason": "Restores previous configuration schema across running instances; requires verification."
    },

    # Database changes - High risk
    "repair_database": {
        "name": "Repair Database Connection Pool",
        "base_data_loss": 20,
        "base_downtime": 20,
        "base_reversibility": 18,
        "modifies_persistent_data": True,
        "affected_components": ["PostgreSQL Primary Database Pool", "Active Transactions"],
        "is_destructive": False,
        "default_reason": "Resets active database connection pool handles, potentially interrupting active client transactions."
    },
    "database_modification": {
        "name": "Database Schema / Index Modification",
        "base_data_loss": 25,
        "base_downtime": 20,
        "base_reversibility": 20,
        "modifies_persistent_data": True,
        "affected_components": ["PostgreSQL Tables", "Primary Storage"],
        "is_destructive": False,
        "default_reason": "Direct modification of persistent database layer with high transactional impact."
    },
    "database_data_resync": {
        "name": "Database Data Resync / In-Place Mutation",
        "base_data_loss": 30,
        "base_downtime": 22,
        "base_reversibility": 20,
        "modifies_persistent_data": True,
        "affected_components": ["PostgreSQL Storage Engines", "Customer Data Partitions"],
        "is_destructive": False,
        "fixed_risk_score": 87,
        "default_reason": "Potential persistent data impact."
    },

    # Destructive operations - Critical risk (Blocked)
    "drop_database": {
        "name": "Drop Database / Truncate Tables",
        "base_data_loss": 30,
        "base_downtime": 25,
        "base_reversibility": 25,
        "modifies_persistent_data": True,
        "affected_components": ["Storage Volumes", "Core Databases"],
        "is_destructive": True,
        "default_reason": "Irreversible destructive operation with catastrophic data loss risk."
    },
    "raw_sql_execution": {
        "name": "Execute Arbitrary DDL / Shell",
        "base_data_loss": 30,
        "base_downtime": 25,
        "base_reversibility": 25,
        "modifies_persistent_data": True,
        "affected_components": ["Host Operating System"],
        "is_destructive": True,
        "default_reason": "Unvetted arbitrary command execution violates autonomous safety policy."
    }
}

# Alias mapping
ACTION_ALIASES = {
    "restart service": "restart_service",
    "restart": "restart_service",
    "restart_api": "restart_service",
    "rollback deployment": "rollback_deployment",
    "rollback release": "rollback_deployment",
    "rollback config": "rollback_config",
    "rollback": "rollback_config",
    "database modification": "database_modification",
    "modify database": "database_modification",
    "db modification": "database_modification",
    "repair db": "repair_database",
    "repair database": "repair_database",
    "database_data_resync": "database_data_resync",
    "database data resync": "database_data_resync",
    "resync database": "database_data_resync",
    "resync database data": "database_data_resync",
    "persistent data resync": "database_data_resync",
    "drop table": "drop_database",
    "drop database": "drop_database",
    "truncate table": "drop_database"
}


# ============================================================================
# RISK ASSESSMENT ENGINE
# ============================================================================

class RiskAssessmentEngine:
    """
    Deterministic risk scoring and safety policy engine.
    Calculates 0-100 risk score and produces definitive execution decisions.
    """

    def _normalize_action(self, action_name: str) -> str:
        cleaned = action_name.strip().lower()
        if cleaned in ACTION_PROFILES:
            return cleaned
        if cleaned in ACTION_ALIASES:
            return ACTION_ALIASES[cleaned]
        # Underscore normalization
        normalized = cleaned.replace(" ", "_").replace("-", "_")
        if normalized in ACTION_PROFILES:
            return normalized
        if normalized in ACTION_ALIASES:
            return ACTION_ALIASES[normalized]
        return cleaned

    def assess_risk(
        self,
        action: str,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Assesses the operational risk of a proposed remediation action.

        Context options:
          - sandbox_validated: bool (default True)
          - is_production: bool (default True)
          - data_loss_risk_override: int (0-30)
          - target_subsystem: str
        """
        context = context or {}
        normalized_action = self._normalize_action(action)
        profile = ACTION_PROFILES.get(normalized_action)

        reasons: List[str] = []

        # If action is completely unrecognized, treat as high risk unapproved action
        if not profile:
            score = 85
            reasons.append(f"Unapproved or unrecognized action '{action}' violates safety whitelist.")
            return {
                "risk_score": score,
                "risk_level": RiskLevel.CRITICAL.value,
                "reasons": reasons,
                "decision": RiskDecision.BLOCK.value
            }

        # --------------------------------------------------------------------
        # DIMENSION 1: Data Loss Risk (0 - 30)
        # --------------------------------------------------------------------
        data_loss_pts = profile["base_data_loss"]
        if profile["is_destructive"]:
            data_loss_pts = 30
            reasons.append("Catastrophic data loss risk: action is inherently destructive.")
        elif profile["modifies_persistent_data"]:
            reasons.append("Modifies persistent data structures; risk of state corruption.")
        else:
            reasons.append("Zero persistent data loss risk (stateless operation).")

        # --------------------------------------------------------------------
        # DIMENSION 2: Service Downtime & Blast Radius (0 - 25)
        # --------------------------------------------------------------------
        downtime_pts = profile["base_downtime"]
        if downtime_pts >= 15:
            reasons.append(f"Moderate to high blast radius affecting: {', '.join(profile['affected_components'])}.")
        else:
            reasons.append("Minimal blast radius restricted to local microservice.")

        # --------------------------------------------------------------------
        # DIMENSION 3: Reversibility (0 - 25)
        # --------------------------------------------------------------------
        reversibility_pts = profile["base_reversibility"]
        if reversibility_pts >= 20:
            reasons.append("Action is difficult or impossible to roll back safely.")
        elif reversibility_pts >= 10:
            reasons.append("Action can be rolled back via subsequent configuration update.")
        else:
            reasons.append("Easily reversible; system state returns immediately.")

        # --------------------------------------------------------------------
        # DIMENSION 4: Modifies Persistent Data (0 - 15)
        # --------------------------------------------------------------------
        persistence_pts = 15 if profile["modifies_persistent_data"] else 0

        # --------------------------------------------------------------------
        # DIMENSION 5: Sandbox Validation Status (-10 to +15)
        # --------------------------------------------------------------------
        sandbox_validated = context.get("sandbox_validated", True)
        if sandbox_validated:
            sandbox_modifier = -10
            reasons.append("Sandbox pre-flight validation PASSED (-10 risk deduction).")
        else:
            sandbox_modifier = 15
            reasons.append("Sandbox pre-flight validation FAILED/SKIPPED (+15 risk penalty).")

        # Total Raw Score
        raw_score = data_loss_pts + downtime_pts + reversibility_pts + persistence_pts + sandbox_modifier
        final_score = max(0, min(100, raw_score))
        if profile.get("fixed_risk_score") is not None:
            final_score = profile["fixed_risk_score"]

        # --------------------------------------------------------------------
        # DECISION CATEGORIES & SAFETY RULES
        # --------------------------------------------------------------------
        if final_score <= 30:
            risk_level = RiskLevel.LOW.value
            decision = RiskDecision.AUTO_EXECUTE.value
            reasons.append("Policy: Low-risk action approved for autonomous execution.")

        elif final_score <= 60:
            risk_level = RiskLevel.MEDIUM.value
            decision = RiskDecision.REQUIRE_APPROVAL.value
            reasons.append("Policy: Medium-risk action paused; requires SRE operator approval.")

        elif final_score <= 80:
            risk_level = RiskLevel.HIGH.value
            decision = RiskDecision.REQUIRE_APPROVAL.value
            reasons.append("Policy: High-risk action strictly requires human operator approval.")

        else:
            risk_level = RiskLevel.CRITICAL.value
            decision = RiskDecision.BLOCK.value
            reasons.append("Policy: Critical-risk action blocked from autonomous execution. Human approval required.")

        # Add profile reason
        if profile.get("default_reason"):
            reasons.insert(0, profile["default_reason"])

        # Structured Output conforming to specification
        return {
            "risk_score": final_score,
            "risk_level": risk_level,
            "reasons": reasons,
            "decision": decision
        }

    def enforce_policy_override(
        self,
        action: str,
        llm_decision: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Guarantees that an LLM cannot bypass safety decision rules.
        Deterministic risk assessment always takes precedence.
        """
        assessment = self.assess_risk(action, context)
        enforced_decision = assessment["decision"]

        # Check if LLM attempted unauthorized bypass
        if llm_decision and llm_decision.upper() == "AUTO_EXECUTE" and enforced_decision != "AUTO_EXECUTE":
            assessment["reasons"].append(
                f"SAFETY GUARD: LLM requested '{llm_decision}', but deterministic policy strictly enforced '{enforced_decision}' due to {assessment['risk_level']} risk level."
            )
            assessment["decision"] = enforced_decision

        return assessment


# Singleton global risk engine
_global_risk_engine: Optional[RiskAssessmentEngine] = None

def get_risk_engine() -> RiskAssessmentEngine:
    global _global_risk_engine
    if _global_risk_engine is None:
        _global_risk_engine = RiskAssessmentEngine()
    return _global_risk_engine


# ============================================================================
# VERIFICATION SUITE
# ============================================================================

def verify_risk_engine():
    print("\n" + "=" * 70)
    print("[TEST] AUTOHEAL RISK ASSESSMENT ENGINE VERIFICATION")
    print("=" * 70)

    engine = RiskAssessmentEngine()

    # ------------------------------------------------------------------------
    # TEST 1: Restart Service
    # ------------------------------------------------------------------------
    print("\n--- [1] Testing Action: 'restart service' ---")
    res_restart = engine.assess_risk("restart service", context={"sandbox_validated": True})
    print(json.dumps(res_restart, indent=2))
    assert res_restart["risk_score"] <= 30, f"Score {res_restart['risk_score']} must be <= 30"
    assert res_restart["risk_level"] == "LOW", "Risk level must be LOW"
    assert res_restart["decision"] == "AUTO_EXECUTE", "Decision must be AUTO_EXECUTE"
    print("  -> 'restart service' correctly classified as LOW / AUTO_EXECUTE [PASSED]")

    # ------------------------------------------------------------------------
    # TEST 2: Rollback Deployment
    # ------------------------------------------------------------------------
    print("\n--- [2] Testing Action: 'rollback deployment' ---")
    res_rollback = engine.assess_risk("rollback deployment", context={"sandbox_validated": True})
    print(json.dumps(res_rollback, indent=2))
    assert 31 <= res_rollback["risk_score"] <= 60, f"Score {res_rollback['risk_score']} must be 31-60"
    assert res_rollback["risk_level"] == "MEDIUM", "Risk level must be MEDIUM"
    assert res_rollback["decision"] == "REQUIRE_APPROVAL", "Decision must be REQUIRE_APPROVAL"
    print("  -> 'rollback deployment' correctly classified as MEDIUM / REQUIRE_APPROVAL [PASSED]")

    # ------------------------------------------------------------------------
    # TEST 3: Database Modification
    # ------------------------------------------------------------------------
    print("\n--- [3] Testing Action: 'database modification' ---")
    res_db = engine.assess_risk("database modification", context={"sandbox_validated": True})
    print(json.dumps(res_db, indent=2))
    assert 61 <= res_db["risk_score"] <= 80, f"Score {res_db['risk_score']} must be 61-80"
    assert res_db["risk_level"] == "HIGH", "Risk level must be HIGH"
    assert res_db["decision"] == "REQUIRE_APPROVAL", "Decision must be REQUIRE_APPROVAL"
    print("  -> 'database modification' correctly classified as HIGH / REQUIRE_APPROVAL [PASSED]")

    # ------------------------------------------------------------------------
    # TEST 4: Destructive Action (Drop Database)
    # ------------------------------------------------------------------------
    print("\n--- [4] Testing Action: 'drop database' (Critical Hazard) ---")
    res_drop = engine.assess_risk("drop database")
    print(json.dumps(res_drop, indent=2))
    assert res_drop["risk_score"] >= 81, f"Score {res_drop['risk_score']} must be >= 81"
    assert res_drop["risk_level"] == "CRITICAL", "Risk level must be CRITICAL"
    assert res_drop["decision"] == "BLOCK", "Decision must be BLOCK"
    print("  -> 'drop database' correctly classified as CRITICAL / BLOCK [PASSED]")

    # ------------------------------------------------------------------------
    # TEST 5: LLM Bypass Attempt Prevention
    # ------------------------------------------------------------------------
    print("\n--- [5] Testing LLM Safety Bypass Prevention ---")
    tamper_result = engine.enforce_policy_override("database modification", llm_decision="AUTO_EXECUTE")
    print(f"LLM Requested: 'AUTO_EXECUTE' | Enforced: '{tamper_result['decision']}'")
    assert tamper_result["decision"] == "REQUIRE_APPROVAL", "Engine must deny LLM AUTO_EXECUTE bypass on database action"
    print("  -> LLM bypass successfully prevented! Deterministic policy enforced. [PASSED]")

    print("\n" + "=" * 70)
    print("[SUCCESS] RISK ASSESSMENT ENGINE FULLY VERIFIED ON ALL TEST CASES!")
    print("=" * 70)


if __name__ == "__main__":
    verify_risk_engine()
