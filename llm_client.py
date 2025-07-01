# llm_client.py

import os
import json
import re
import logging
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()
logging.basicConfig(
    filename="backend.log",
    filemode="a",
    level=logging.INFO
)

# Pick provider from ENV
PROVIDER           = os.getenv("PROVIDER", "openai").lower()
OPENAI_API_KEY     = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL       = os.getenv("OPENAI_MODEL", "gpt-4-turbo")
ANTHROPIC_API_KEY  = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL    = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL   = os.getenv("OPENROUTER_MODEL", "mistralai/mistral-7b-instruct")
DEEPSEEK_API_KEY   = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL     = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# Lazy‐import SDKs
try:
    import openai
    openai.api_key = OPENAI_API_KEY
except ImportError:
    openai = None

try:
    import anthropic
    anthropic_client = anthropic.Client(api_key=ANTHROPIC_API_KEY)
    from anthropic import HUMAN_PROMPT, AI_PROMPT
except ImportError:
    anthropic = None


def _call_openai(prompt: str) -> str:
    import openai
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    # Log token usage
    usage = getattr(response, "usage", None)
    if usage:
        logging.info(f"[OpenAI tokens] prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")


def _call_anthropic(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=1000,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}]
    )
    usage = getattr(response, "usage", None)
    if usage:
        logging.info(f"[Anthropic tokens] input: {usage.input_tokens}, output: {usage.output_tokens}")
    return response.content[0].text


def _call_openrouter(prompt: str) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def _call_deepseek(prompt: str) -> str:
    import openai
    client = openai.OpenAI(
        api_key=DEEPSEEK_API_KEY,
        base_url="https://api.deepseek.com/v1"
    )
    response = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0
    )
    # Log token usage
    usage = getattr(response, "usage", None)
    if usage:
        logging.info(f"[Deepseek tokens] prompt: {usage.prompt_tokens}, completion: {usage.completion_tokens}, total: {usage.total_tokens}")
    return response.choices[0].message.content


def call_llm(prompt: str) -> str:
    if PROVIDER == "openai":
        if openai is None:
            raise RuntimeError("OpenAI SDK not installed")
        return _call_openai(prompt)

    if PROVIDER == "anthropic":
        if anthropic is None:
            raise RuntimeError("Anthropic SDK not installed")
        return _call_anthropic(prompt)

    if PROVIDER == "openrouter":
        return _call_openrouter(prompt)

    if PROVIDER == "deepseek":
        return _call_deepseek(prompt)

    raise RuntimeError(f"Unsupported PROVIDER: {PROVIDER}")


def parse_constraints(rules_text: str, days=None, day_of_week=None) -> dict:
    """
    Parse free-form rules_text via the selected LLM into structured JSON.
    Optionally pass days and day_of_week lists to inform date-related constraints.
    """
    # Prepare context block (if date info is available)
    date_info = ""
    if days and day_of_week:
        date_lines = "\n".join([f"{i}: {d} ({dow})" for i, (d, dow) in enumerate(zip(days, day_of_week))])
        date_info = f"\nThe schedule has these indexed days:\n{date_lines}\n"

    prompt = f"""
You are a constraint parser for OR‑Tools CP‑SAT. Read these rules and output JSON ONLY.
{date_info}
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

    raw = call_llm(prompt)
    logging.info(f"[LLM raw output]\n{raw}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass

    raise RuntimeError(f"Failed to parse JSON from LLM response:\n{raw}")