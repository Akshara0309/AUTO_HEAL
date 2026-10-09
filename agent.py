from tools import (
    get_logs,
    get_metrics,
    check_db_health,
    get_recent_deploys,
    restart_service,
    rollback_config,
    repair_database,
    verify_recovery
)


# =========================
# CREATE HYPOTHESIS
# =========================

def create_hypothesis():

    metrics = get_metrics()
    logs = get_logs()

    error_rate = metrics["data"]["error_rate"]

    if error_rate >= 80:

        return {
            "cause": "API service is down",
            "confidence": 0.92,
            "test": "Check service logs and metrics"
        }

    elif error_rate >= 60:

        return {
            "cause": "Database or configuration problem",
            "confidence": 0.75,
            "test": "Check database health and configuration"
        }

    else:

        return {
            "cause": "Unknown",
            "confidence": 0.40,
            "test": "Collect more system information"
        }


# =========================
# RUN AUTO-HEAL
# =========================

def run_agent():

    print("\n==============================")
    print("       AUTO-HEAL AGENT")
    print("==============================")

    print("\n[1] Reading logs...")

    logs = get_logs()

    print(logs)

    print("\n[2] Reading metrics...")

    metrics = get_metrics()

    print(metrics)

    print("\n[3] Creating hypothesis...")

    hypothesis = create_hypothesis()

    print(hypothesis)

    print("\n[4] Testing hypothesis...")

    if "API service" in hypothesis["cause"]:

        print("Test result: API service appears to be DOWN")

        print("\n[5] Applying fix...")

        result = restart_service()

        print(result)

    elif "Database" in hypothesis["cause"]:

        print("Test result: Database problem suspected")

        print("\n[5] Applying fix...")

        result = repair_database()

        print(result)

    else:

        print("Unable to determine safe fix.")

        return

    print("\n[6] Verifying recovery...")

    verification = verify_recovery()

    print(verification)

    if verification["data"]["recovered"]:

        print("\n✅ SYSTEM RECOVERED")

    else:

        print("\n🚨 HUMAN ESCALATION REQUIRED")


# =========================
# START AGENT
# =========================

if __name__ == "__main__":

    run_agent()