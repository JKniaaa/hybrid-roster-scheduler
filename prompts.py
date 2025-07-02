# prompts.py

import json

def build_constraints_prompt(rules_text: str) -> str:
    """
    Build a prompt that asks the LLM to parse free‑form rules_text into
    structured JSON (hard_constraints, soft_constraints, variables, objective).
    """
    return f"""
You are a constraint parser for OR‑Tools CP‑SAT. Read these rules and output JSON ONLY.

Rules:
{rules_text}

Return exactly:
{{
  "hard_constraints": [...],
  "soft_constraints": [...],
  "variables": [...],
  "objective": "..."
}}
No explanations or markdown.
""".strip()


def build_codegen_prompt(custom_rules: str) -> str:
    return f"""
You are NurseRosterScheduler, a senior expert in constraint programming using Google OR‑Tools (CP‑SAT).
You convert natural language rules into strictly correct Python code that integrates seamlessly into an existing `cp_model.CpModel()` instance named `model`.

CONTEXT:
The code will be inserted into a working nurse rostering solver. These variables are pre-defined:
  - work[n, d, s]: BoolVar for nurse `n` on day `d` and shift `s`
  - nurses, seniors, juniors: lists of nurse IDs
  - days: list of date strings (e.g., "2024-07-01")
  - day_of_week: weekday names (e.g., "Monday", "Tuesday")
  - shift_names = ["AM", "PM", "Night", "REST", "MC"]
  - d is the integer index for a day (0 to len(days)-1)

RULES FOR CODE:
- Output ONLY pure, syntactically valid Python code for OR‑Tools CP‑SAT.
- Never include comments, explanations, markdown, or prose.
- Always define `n` inside a `for n in nurses:` loop.
- Always define `d` inside a `for d in range(...)` loop.
- Use `model.Add(...)`, `model.AddImplication(...)`, `sum(...)`, `.Not()`, and `model.NewBoolVar(...)` appropriately.
- Never use `.index(...)`, or operate on string dates directly.
- Never apply `.Not()` to a `sum(...)` expression.
- Never place `sum(...) >= ...` directly inside `model.AddImplication(...)`.

✅ Instead:
1. Create a helper BoolVar: `cond = model.NewBoolVar(...)`
2. Use: `model.Add(sum(...) >= threshold).OnlyEnforceIf(cond)`
3. Then: `model.AddImplication(cond, ...)`

❌ BAD PATTERN (invalid):
model.AddImplication(work[n, d, "AM"], sum(work[n, d, s] for s in shift_names) == 0)

✅ GOOD PATTERN (scoped correctly):
for n in nurses:
    for d in range(len(days) - 1):
        cond = model.NewBoolVar(f"{{{{n}}}}_cond_{{{{d}}}}")
        rhs = model.NewBoolVar(f"{{{{n}}}}_rhs_{{{{d}}}}")
        model.Add(sum(work[n, d, s] for s in shift_names if s != "REST") >= 1).OnlyEnforceIf(cond)
        model.Add(sum(work[n, d, s] for s in shift_names if s != "REST") == 0).OnlyEnforceIf(cond.Not())
        model.Add(sum(work[n, d + 1, s] for s in shift_names if s != "REST") == 0).OnlyEnforceIf(rhs)
        model.Add(sum(work[n, d + 1, s] for s in shift_names if s != "REST") >= 1).OnlyEnforceIf(rhs.Not())
        model.AddImplication(cond, rhs)

EXAMPLES:

1. “If a nurse has a Night on day X, they may not have an AM on day X+1.”
for n in nurses:
    for d in range(len(days)-1):
        model.AddImplication(work[n, d, "Night"], work[n, d+1, "AM"].Not())

2. “If a nurse works Night on Sunday, they must rest on Monday.”
for n in nurses:
    for d in range(len(days)-1):
        if day_of_week[d] == "Sunday" and day_of_week[d+1] == "Monday":
            model.AddImplication(work[n, d, "Night"], work[n, d+1, "REST"])

3. "A nurse cannot work more than 5 Night shifts in total."
for n in nurses:
    model.Add(sum(work[n, d, "Night"] for d in range(len(days))) <= 5)

4. "If a nurse works on Saturday, they must rest on Sunday."
for n in nurses:
    for d in range(len(days)-1):
        if day_of_week[d] == "Saturday" and day_of_week[d+1] == "Sunday":
            worked_sat = model.NewBoolVar(f"{{{{n}}}}_worked_sat_{{{{d}}}}")
            model.Add(sum(work[n, d, s] for s in shift_names if s not in ["REST", "MC"]) >= 1).OnlyEnforceIf(worked_sat)
            model.Add(sum(work[n, d, s] for s in shift_names if s not in ["REST", "MC"]) == 0).OnlyEnforceIf(worked_sat.Not())
            model.AddImplication(worked_sat, sum(work[n, d+1, s] for s in shift_names if s not in ["REST", "MC"]) == 0)

NOW GENERATE the code for:
\"\"\"{custom_rules}\"\"\"
Return exactly valid JSON. Do NOT use Python code, variables, or expressions. Only output data, not code. No comments, no prose, no markdown.
""".strip()
