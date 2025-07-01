import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from llm_client import parse_constraints
from scheduler import build_and_solve
import logging
import json

st.set_page_config(page_title="Hybrid Nurse Scheduler", layout="wide")
st.title("🩺 Hybrid Nurse Roster Scheduler")

# --- Sidebar Inputs ---
with st.sidebar:
    st.header("Scheduler Inputs")
    start_date = st.date_input("Start date", date.today())
    end_date   = st.date_input("End date", date.today())
    st.markdown("---")
    st.subheader("Nurse Counts")
    num_seniors = st.number_input("Number of Senior Nurses", 1, 100, 15, 1)
    num_juniors = st.number_input("Number of Junior Nurses", 1, 100, 10, 1)
    st.markdown("---")
    st.subheader("Shift Coverage Constraints")
    min_nurses_per_shift = st.number_input("Minimum nurses per shift", 1, num_seniors + num_juniors, 2, 1)
    min_seniors_per_shift = st.number_input("Minimum senior nurses per shift", 0, num_seniors, 1, 1)
    min_am_coverage = st.slider("Minimum percentage of nurses for AM shift", 1, 100, 60, 1)
    min_senior_am_coverage = st.slider("Minimum percentage of senior nurses for AM shift", 0, 100, 60, 1)
    st.markdown("---")
    st.subheader("Working Hours Constraints")
    min_hours = st.number_input("Minimum working hours per week", 0, 168, 0, 1)
    max_hours = st.number_input("Maximum working hours per week", 1, 168, 42, 1)
    st.markdown("---")
    st.subheader("Custom Rules")

    if "custom_rules" not in st.session_state:
        st.session_state.custom_rules = []

    st.markdown("### 🛠️ Custom Rules")
    new_rule = st.text_area("Add a custom rule", height=100, placeholder="Type your rule here...", key="new_rule")

    if st.button("➕ Add Rule"):
        if new_rule.strip():
            st.session_state.custom_rules.append(new_rule.strip())
            st.success("Rule added!")
            st.rerun()
        else:
            st.warning("No rule entered.")

    st.markdown("---")
    st.markdown("### 📋 Your Rules")

    if st.session_state.custom_rules:
        for i, rule in enumerate(st.session_state.custom_rules):
            rule_col, del_col = st.columns([5, 1])
            rule_col.markdown(f"- {rule}")
            if del_col.button("❌", key=f"del_{i}"):
                st.session_state.custom_rules.pop(i)
                st.rerun()
    else:
        st.info("No custom rules added yet.")

    st.markdown("---")
    st.subheader("Medical Certificate (MC) Preferences")

    if "mc_preferences" not in st.session_state:
        st.session_state.mc_preferences = {}

    date_list = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d")
                 for i in range((end_date - start_date).days + 1)]
    date_options = ["Select date"] + date_list
    nurse_options = ["Select nurse"] + [f"S{str(i).zfill(2)}" for i in range(num_seniors)] + \
                    [f"J{str(i).zfill(2)}" for i in range(num_juniors)]
    mc_nurse = st.selectbox("Select nurse for MC", nurse_options)
    mc_date = st.selectbox("Select MC date", date_options)

    if st.button("Add MC Day"):
        if mc_nurse == "Select nurse":
            st.warning("Please select a nurse.")
        elif mc_date == "Select date":
            st.warning("Please select a date.")
        else:
            nurse_prefs = st.session_state.mc_preferences.get(mc_nurse, [])
            if mc_date not in nurse_prefs:
                nurse_prefs.append(mc_date)
                st.session_state.mc_preferences[mc_nurse] = nurse_prefs
                st.success(f"Added MC for {mc_nurse} on {mc_date}")
            else:
                st.info("MC declaration already added!")

    if st.session_state.mc_preferences:
        st.markdown("#### Current MC Preferences:")
        for nurse, dates in st.session_state.mc_preferences.items():
            for d in sorted(dates):
                col1, col2 = st.columns([5, 1])  # Match the column ratio used for custom rules
                col1.write(f"{nurse} - {d}")
                if col2.button("❌", key=f"remove_{nurse}_{d}"):
                    st.session_state.mc_preferences[nurse].remove(d)
                    if not st.session_state.mc_preferences[nurse]:
                        del st.session_state.mc_preferences[nurse]
                    st.rerun()

    else:
        st.info("No MC preferences set.")

    generate = st.button("Generate Schedule")

# --- Main Area ---
if generate:
    seniors = [f"S{str(i).zfill(2)}" for i in range(num_seniors)]
    juniors = [f"J{str(i).zfill(2)}" for i in range(num_juniors)]
    nurse_ids = seniors + juniors

    num_days = (end_date - start_date).days + 1
    days = [(start_date + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(num_days)]
    day_of_week = [(start_date + timedelta(days=i)).strftime("%A") for i in range(num_days)]

    rules_text = "\n".join(st.session_state.custom_rules)

    input_data = {
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "days": days,
        "day_of_week": day_of_week,
        "nurses": {
            "seniors": seniors,
            "juniors": juniors
        },
        "rules_text": rules_text.strip(),
        "min_hours_per_week": min_hours,
        "max_hours_per_week": max_hours,
        "min_nurses_per_shift": min_nurses_per_shift,
        "min_seniors_per_shift": min_seniors_per_shift,
        "min_am_coverage": min_am_coverage,
        "min_senior_am_coverage": min_senior_am_coverage,
        "mc_preferences": st.session_state.mc_preferences,
    }

    with st.spinner("🧠 Parsing rules..."):
        try:
            if rules_text.strip():
                constraints = parse_constraints(rules_text.strip(), days=days, day_of_week=day_of_week)
            else:
                constraints = {
                    "hard_constraints": [],
                    "soft_constraints": [],
                    "variables": [],
                    "objective": ""
                }
            logging.info("[Constraints structure]\n%s", json.dumps(constraints, indent=2))
        except Exception as e:
            st.error(f"Failed to parse rules: {e}")
            st.stop()

    with st.spinner("⚙️ Building and solving schedule..."):
        try:
            schedule = build_and_solve(input_data, constraints)
        except Exception as e:
            st.error(f"Scheduling error: {e}")
            st.stop()

    if schedule.get("s"):
        df = pd.DataFrame(schedule["s"], columns=["Nurse", "Date", "Shift"])
        df["Date"] = pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d")
        pivot = df.pivot(index="Nurse", columns="Date", values="Shift")
        nurse_order = seniors + juniors
        pivot = pivot.reindex(nurse_order)
        st.success("✅ Schedule generated successfully!")
        st.dataframe(pivot)
    else:
        st.warning("⚠️ No feasible schedule found.")

    st.markdown("---")
