import os
import json
import logging
from flask import Flask, request, jsonify, abort
from llm_client import parse_constraints
from scheduler import build_and_solve
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    filename="backend.log",
    filemode="a",
    level=logging.INFO
)

# Flask app
app = Flask(__name__)

@app.route("/schedule", methods=["POST"])
def schedule():
    # 1) Parse & validate input JSON
    try:
        data = request.get_json(force=True)
    except Exception as e:
        logging.error(f"Invalid JSON: {e}")
        abort(400, description="Invalid JSON payload")

    required_fields = ["start_date", "end_date", "senior_ids", "junior_ids", "rules_text"]
    missing = [f for f in required_fields if f not in data]
    if missing:
        msg = f"Missing required fields: {', '.join(missing)}"
        logging.error(msg)
        abort(400, description=msg)

    # Convert to scheduler.py format
    input_data = {
        "start_date": data["start_date"],
        "end_date": data["end_date"],
        "nurses": {
            "seniors": data["senior_ids"],
            "juniors": data["junior_ids"]
        },
        "rules_text": data.get("rules_text", ""),
        "min_hours_per_week": data.get("min_hours_per_week", 0),
        "max_hours_per_week": data.get("max_hours_per_week", 168),
        "min_nurses_per_shift": data.get("min_nurses_per_shift", 1),
        "min_seniors_per_shift": data.get("min_seniors_per_shift", 0),
        "min_am_coverage": data.get("min_am_coverage", 1),
        "min_senior_am_coverage": data.get("min_senior_am_coverage", 0)
    }

    start = datetime.strptime(data["start_date"], "%Y-%m-%d")
    end = datetime.strptime(data["end_date"], "%Y-%m-%d")
    num_days = (end - start).days + 1
    days = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(num_days)]
    day_of_week = [(start + timedelta(days=i)).strftime("%A") for i in range(num_days)]

    input_data["days"] = days
    input_data["day_of_week"] = day_of_week

    # 2) Extract & parse rules via LLM
    rules_text = data["rules_text"]
    try:
        constraints = parse_constraints(rules_text, days=days, day_of_week=day_of_week)
        # Log the constraints structure
        logging.info("[Constraints structure]\n%s", json.dumps(constraints, indent=2))
    except Exception as e:
        logging.exception("Failed to parse constraints with LLM")
        abort(500, description=f"Constraint parsing error: {str(e)}")

    # 3) Build & solve schedule with OR‑Tools
    try:
        schedule = build_and_solve(input_data, constraints)
    except Exception as e:
        logging.exception("Scheduling solver error")
        abort(500, description=f"Scheduling error: {str(e)}")

    # 4) Return JSON schedule
    return jsonify(schedule), 200

if __name__ == "__main__":
    # Use PORT env var if set (e.g. in prod)
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_ENV", "production") != "production"
    app.run(host="0.0.0.0", port=port, debug=debug)
