from sandbox import SYSTEM, LOG_FILE


# =========================
# READ LOGS
# =========================

def get_logs(n=10):

    try:
        with open(LOG_FILE, "r") as file:
            lines = file.readlines()

        return {
            "ok": True,
            "data": lines[-n:]
        }

    except Exception as e:

        return {
            "ok": False,
            "data": {
                "error": str(e)
            }
        }


# =========================
# GET METRICS
# =========================

def get_metrics():

    return {
        "ok": True,
        "data": {
            "cpu": SYSTEM["cpu"],
            "memory": SYSTEM["memory"],
            "error_rate": SYSTEM["error_rate"]
        }
    }


# =========================
# CHECK DATABASE
# =========================

def check_db_health():

    return {
        "ok": True,
        "data": {
            "database": SYSTEM["database"]
        }
    }


# =========================
# GET RECENT DEPLOYS
# =========================

def get_recent_deploys():

    return {
        "ok": True,
        "data": {
            "last_deploy": "10 minutes ago",
            "version": "v1.2.4"
        }
    }


# =========================
# RESTART SERVICE
# =========================

def restart_service():

    if SYSTEM["service"] == "down":

        SYSTEM["service"] = "running"
        SYSTEM["cpu"] = 35
        SYSTEM["error_rate"] = 0

        return {
            "ok": True,
            "data": {
                "message": "Service restarted successfully"
            }
        }

    return {
        "ok": False,
        "data": {
            "message": "Service is already running"
        }
    }


# =========================
# ROLLBACK CONFIG
# =========================

def rollback_config():

    SYSTEM["config"] = "normal"
    SYSTEM["error_rate"] = 0

    return {
        "ok": True,
        "data": {
            "message": "Configuration rolled back successfully"
        }
    }


# =========================
# REPAIR DATABASE
# =========================

def repair_database():

    SYSTEM["database"] = "healthy"
    SYSTEM["error_rate"] = 0

    return {
        "ok": True,
        "data": {
            "message": "Database repaired successfully"
        }
    }


# =========================
# VERIFY RECOVERY
# =========================

def verify_recovery():

    service_ok = SYSTEM["service"] == "running"
    database_ok = SYSTEM["database"] == "healthy"
    config_ok = SYSTEM["config"] == "normal"
    errors_ok = SYSTEM["error_rate"] < 5

    recovered = (
        service_ok
        and database_ok
        and config_ok
        and errors_ok
    )

    return {
        "ok": recovered,
        "data": {
            "service": SYSTEM["service"],
            "database": SYSTEM["database"],
            "config": SYSTEM["config"],
            "error_rate": SYSTEM["error_rate"],
            "recovered": recovered
        }
    }


# =========================
# TEST THE TOOLS
# =========================

if __name__ == "__main__":

    print("\n--- LOGS ---")
    print(get_logs())

    print("\n--- METRICS ---")
    print(get_metrics())

    print("\n--- DATABASE ---")
    print(check_db_health())

    print("\n--- DEPLOYMENT ---")
    print(get_recent_deploys())

    print("\n--- VERIFICATION ---")
    print(verify_recovery())

    print("\n--- RESTARTING SERVICE ---")
    print(restart_service())

    print("\n--- VERIFYING AGAIN ---")
    print(verify_recovery())