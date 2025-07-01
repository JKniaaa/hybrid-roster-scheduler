# scheduler.py

from ortools.sat.python import cp_model
import datetime
from llm_client import call_llm
from prompts import build_codegen_prompt  # from prompts.py
import logging
import re

def build_and_solve(input_data: dict, constraints: dict = None) -> dict:
    model = cp_model.CpModel()

    # 1) Unpack nurse & date info
    seniors = input_data["nurses"]["seniors"]
    juniors = input_data["nurses"]["juniors"]
    nurses = seniors + juniors

    start = datetime.datetime.strptime(input_data["start_date"], "%Y-%m-%d")
    end   = datetime.datetime.strptime(input_data["end_date"], "%Y-%m-%d")
    days  = [(start + datetime.timedelta(days=i)).strftime("%Y-%m-%d")
             for i in range((end - start).days + 1)]

    shift_names = ["AM", "PM", "Night", "REST", "MC"]

    # 2) Create variables
    work = {}
    for n in nurses:
        for d in range(len(days)):
            for s in shift_names:
                work[n, d, s] = model.NewBoolVar(f"work_{n}_{d}_{s}")

    # 2b) Enforce MC only if declared, and force it if declared
    declared_mc = input_data.get("mc_preferences", {})  # dict: {nurse_id: [YYYY-MM-DD, ...]}
    for n in nurses:
        declared_dates = set(declared_mc.get(n, []))
        for d, day_str in enumerate(days):
            if day_str in declared_dates:
                model.Add(work[n, d, "MC"] == 1)  # Must assign MC
            else:
                model.Add(work[n, d, "MC"] == 0)  # Cannot assign MC

    # 3) CORE RULES (always enforced)

    # 3a) Exactly one assignment per nurse per day
    for n in nurses:
        for d in range(len(days)):
            model.Add(sum(work[n, d, s] for s in shift_names) == 1)

    # 3b) Shift coverage for all working shifts (AM, PM, Night)
    for d in range(len(days)):
        for s in ["AM", "PM", "Night"]:
            model.Add(
                sum(work[n, d, s] for n in nurses) >= input_data["min_nurses_per_shift"]
            )
            model.Add(
                sum(work[n, d, s] for n in seniors) >= input_data["min_seniors_per_shift"]
            )

    # 3c) AM shift coverage by percentage (of all working nurses/seniors that day)
    for d in range(len(days)):
        total_working = sum(
            work[n, d, s] for n in nurses for s in ["AM", "PM", "Night"]
        )
        total_working_seniors = sum(
            work[n, d, s] for n in seniors for s in ["AM", "PM", "Night"]
        )

        min_am_pct = input_data.get("min_am_coverage", 0)
        if min_am_pct > 0:
            model.Add(
                sum(work[n, d, "AM"] for n in nurses) * 100
                >= min_am_pct * total_working
            )

        min_senior_am_pct = input_data.get("min_senior_am_coverage", 0)
        if min_senior_am_pct > 0:
            model.Add(
                sum(work[n, d, "AM"] for n in seniors) * 100
                >= min_senior_am_pct * total_working_seniors
            )

    # 3d) Weekly hours limits
    shift_hours = {"AM": 7, "PM": 7, "Night": 10, "REST": 0, "MC": 0}
    max_h = input_data["max_hours_per_week"]
    min_h = input_data["min_hours_per_week"]
    for n in nurses:
        num_full_weeks = len(days) // 7
        for w in range(num_full_weeks):
            week_days = range(w * 7, (w + 1) * 7)
            total = sum(
                shift_hours[s] * work[n, d, s]
                for d in week_days for s in ["AM", "PM", "Night"]
            )
            model.Add(total <= max_h)
            model.Add(total >= min_h)

    # 3e) Night → no AM next day (optional, currently disabled)
    # for n in nurses:
    #     for d in range(len(days) - 1):
    #         model.AddImplication(
    #             work[n, d, "Night"],
    #             work[n, d + 1, "AM"].Not()
    #         )

    # 4) CUSTOM RULES (only if supplied)
    custom = input_data.get("rules_text", "").strip()
    if custom:
        prompt = build_codegen_prompt(custom)
        snippet = call_llm(prompt).strip()
        # Remove Markdown code block markers if present
        snippet = re.sub(r"^```(?:python)?\s*", "", snippet)
        snippet = re.sub(r"\s*```$", "", snippet)
        if '\\n' in snippet and '\n' not in snippet:
            snippet = snippet.replace('\\n', '\n')
        logging.info(f"[LLM code snippet]\n{repr(snippet)}")
        forbidden = ["shift_names.index", "for d in days", "for d in days[:-1]", "for d in days[1:]"]
        for f in forbidden:
            if f in snippet:
                raise RuntimeError(f"LLM code contains forbidden pattern: {f}\n{snippet}")
        namespace = {
            "model": model,
            "work": work,
            "nurses": nurses,
            "seniors": seniors,
            "juniors": juniors,
            "days": days,
            "shift_names": shift_names,
            "day_of_week": input_data.get("day_of_week", []),  # <-- Add this line
        }
        try:
            exec(snippet, namespace, namespace)
        except Exception as e:
            raise RuntimeError(f"Error executing custom-rule code:\n{snippet}\n\n{e}")

    # 5) Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 60
    solver.parameters.num_search_workers = 8
    solver.parameters.relative_gap_limit = 0.05
    solver.parameters.random_seed = 42
    status = solver.Solve(model)

    # 6) Format output
    output = {"s": []}
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        for n in nurses:
            for d in range(len(days)):
                for s in shift_names:
                    if solver.Value(work[n, d, s]):
                        output["s"].append([n, days[d], s])
    else:
        output["error"] = "No feasible solution found."

    return output
