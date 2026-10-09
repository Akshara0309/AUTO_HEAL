import time
import random
import json
from pathlib import Path


# =========================
# LOG FILE
# =========================

LOG_FOLDER = Path("logs")
LOG_FOLDER.mkdir(exist_ok=True)

LOG_FILE = LOG_FOLDER / "app.log"


# =========================
# FAKE APPLICATION STATE
# =========================

SYSTEM = {
    "service": "running",
    "database": "healthy",
    "config": "normal",
    "cpu": 30,
    "memory": 40,
    "error_rate": 0
}


# =========================
# LOG FUNCTION
# =========================

def write_log(level, message):

    log = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "level": level,
        "message": message
    }

    with open(LOG_FILE, "a") as file:
        file.write(json.dumps(log) + "\n")

    print(f"[{level}] {message}")


# =========================
# NORMAL APPLICATION
# =========================

def normal_activity():

    SYSTEM["cpu"] = random.randint(25, 50)
    SYSTEM["memory"] = random.randint(35, 60)
    SYSTEM["error_rate"] = random.randint(0, 2)

    write_log(
        "INFO",
        "Request processed successfully"
    )


# =========================
# FAULT 1
# =========================

def service_failure():

    SYSTEM["service"] = "down"
    SYSTEM["cpu"] = 95
    SYSTEM["error_rate"] = 85

    write_log(
        "ERROR",
        "API service stopped responding"
    )

    write_log(
        "ERROR",
        "Connection refused on port 8080"
    )


# =========================
# FAULT 2
# =========================

def database_failure():

    SYSTEM["database"] = "unhealthy"
    SYSTEM["error_rate"] = 70

    write_log(
        "ERROR",
        "Database connection timeout"
    )

    write_log(
        "ERROR",
        "Database health check failed"
    )


# =========================
# FAULT 3
# =========================

def configuration_failure():

    SYSTEM["config"] = "invalid"
    SYSTEM["error_rate"] = 60

    write_log(
        "ERROR",
        "Invalid configuration detected"
    )

    write_log(
        "ERROR",
        "Application configuration validation failed"
    )


# =========================
# START SANDBOX
# =========================

def run_cli():
    print("\n==============================")
    print("      AUTO-HEAL SANDBOX")
    print("==============================")

    print("\nStarting fake application...\n")

    write_log(
        "INFO",
        "Sandbox application started"
    )

    # Generate normal activity
    for i in range(5):
        normal_activity()
        time.sleep(1)

    # =========================
    # CHOOSE FAILURE
    # =========================

    print("\nChoose a fault to create:\n")
    print("1. API Service Failure")
    print("2. Database Failure")
    print("3. Configuration Failure")

    choice = input("\nEnter your choice: ")

    if choice == "1":
        service_failure()
    elif choice == "2":
        database_failure()
    elif choice == "3":
        configuration_failure()
    else:
        print("\nInvalid choice!")

    # =========================
    # SHOW CURRENT STATE
    # =========================

    print("\n==============================")
    print("       CURRENT STATE")
    print("==============================")

    print(
        json.dumps(
            SYSTEM,
            indent=4
        )
    )

    print("\nSandbox fault created.")
    print("Check logs/app.log")


if __name__ == "__main__":
    run_cli()