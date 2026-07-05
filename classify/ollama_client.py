import json
import time
import requests
from config import MAX_CTX_CHARS, OLLAMA_BASE, RETRY_DELAY, RETRY_LIMIT, TIMEOUT
from utils import format_table_for_llm
 
def check_ollama(model: str) -> bool:
    """Verify Ollama is reachable and the model is available."""
    try:
        resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=5)
        models = [m["name"] for m in resp.json().get("models", [])]
        available = any(m.startswith(model.split(":")[0]) for m in models)
        if not available:
            print(f"⚠️  Model '{model}' not found in Ollama. Available: {models}")
            print(f"   Run: ollama pull {model}")
            return False
        return True
    except requests.exceptions.ConnectionError:
        print("❌  Cannot reach Ollama at http://localhost:11434")
        print("   Start it with: ollama serve")
        return False


def call_ollama(prompt: str, model: str) -> str:
    """Call local Ollama model and return raw response text."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": 0.05,     # near-deterministic
            "num_predict": 120,      # short: we only need a JSON snippet
            "top_p": 0.9,
        },
    }
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            resp = requests.post(
                f"{OLLAMA_BASE}/api/chat",
                json=payload,
                timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except requests.exceptions.Timeout:
            if attempt < RETRY_LIMIT:
                time.sleep(RETRY_DELAY)
            else:
                return ""
        except Exception as exc:
            if attempt < RETRY_LIMIT:
                time.sleep(RETRY_DELAY)
            else:
                return ""
    return ""


def parse_llm_json(raw: str) -> dict:
    """Extract the first JSON object from LLM output (handles extra text/markdown)."""
    start = raw.find("{")
    end   = raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end])
        except json.JSONDecodeError:
            pass
    return {}

def classify_via_llm(
    page_text: str,
    table: dict,
    candidates: list[str],
    model: str,
) -> dict:
    """
    Ask Qwen2.5:3b to classify a single table.

    Returns:
        {"category": "bankwise|categorywise|disposal|officewise|other",
         "title":    "short title",
         "confidence": "high|medium|low"}
    """
    cats_list = ", ".join(candidates + ["other"])
    context   = page_text[:MAX_CTX_CHARS].strip().replace("\n", " ")
    tbl_str   = format_table_for_llm(table.get("data", []))

    prompt = f"""You are classifying tables from RBI Ombudsman Annual Reports.

Page context: {context}

Table data:
{tbl_str}

Category definitions:
- bankwise     = rows represent different bank types (public/private/foreign/RRB/cooperative)
- categorywise = rows represent complaint types/categories (ATM, credit card, loans, mobile banking…)
- disposal     = rows describe how complaints were resolved (settled, rejected, award, withdrawn, pending…)
- officewise   = rows represent different Ombudsman offices or geographic zones/regions

Choose the BEST category from: {cats_list}

Respond with ONLY a JSON object — no explanation, no markdown:
{{"category": "<pick one>", "title": "<10 word descriptive title>", "confidence": "<high|medium|low>"}}"""

    raw = call_ollama(prompt, model)
    result = parse_llm_json(raw)

    # Validate / fallback
    valid_cats = set(candidates + ["other"])
    if result.get("category") not in valid_cats:
        # If LLM output is garbled, fall back to the first keyword candidate
        result["category"] = candidates[0] if candidates else "other"
        result.setdefault("confidence", "low")

    result.setdefault("title", "")
    result.setdefault("confidence", "medium")
    return result

