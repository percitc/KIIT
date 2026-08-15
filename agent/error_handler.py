"""
agent/error_handler.py — KITT Error Recovery Module
✅ Fixed: google.generativeai → google.genai (new API)
✅ Fixed: MARK XXV → KITT
✅ Improved: Faster decisions, smarter fallbacks
"""

import json
import re
import sys
from pathlib import Path
from enum import Enum
from google import genai
from google.genai import types as gentypes


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


class ErrorDecision(Enum):
    RETRY  = "retry"
    SKIP   = "skip"
    REPLAN = "replan"
    ABORT  = "abort"


ERROR_ANALYST_PROMPT = """\
You are the error recovery module of KITT AI assistant.
A task step has failed. Analyze the error and decide what to do.

DECISIONS:
- retry   : Transient error (network timeout, temporary file lock, race condition). Same step can succeed if tried again.
- skip    : Step is not critical and task can succeed without it.
- replan  : Wrong approach. A different tool or method should be tried.
- abort   : Task is fundamentally impossible or unsafe to continue.

Return ONLY valid JSON:
{
  "decision": "retry|skip|replan|abort",
  "reason": "why it failed (1 sentence)",
  "fix_suggestion": "what to try instead (for replan only)",
  "max_retries": 1,
  "user_message": "Short message to tell user (max 12 words, address as sir)"
}
"""


def _get_client() -> genai.Client:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        api_key = json.load(f)["gemini_api_key"]
    return genai.Client(api_key=api_key)


# ── Fast heuristic decisions without API call ─────────────────────────────────

_TRANSIENT_PATTERNS = [
    "timeout", "connection", "network", "temporarily", "rate limit",
    "503", "502", "429", "ssl", "connection reset"
]
_ABORT_PATTERNS = [
    "permission denied", "access denied", "not found", "no such file",
    "authentication failed", "invalid api key"
]


def _heuristic_decision(error: str) -> str | None:
    err_lower = error.lower()
    if any(p in err_lower for p in _TRANSIENT_PATTERNS):
        return "retry"
    if any(p in err_lower for p in _ABORT_PATTERNS):
        return "replan"
    return None


def analyze_error(
    step: dict,
    error: str,
    attempt: int = 1,
    max_attempts: int = 2
) -> dict:
    # Force replan after max attempts
    if attempt >= max_attempts:
        print(f"[ErrorHandler] ⚠️ Max attempts on step {step.get('step')} — forcing replan")
        return {
            "decision":       ErrorDecision.REPLAN,
            "reason":         f"Failed {attempt} times: {error[:100]}",
            "fix_suggestion": "Try a completely different tool or approach",
            "max_retries":    0,
            "user_message":   "Trying a different approach, sir."
        }

    # Try fast heuristic first (no API call)
    heuristic = _heuristic_decision(error)
    if heuristic:
        decision_map = {
            "retry":  ErrorDecision.RETRY,
            "replan": ErrorDecision.REPLAN,
            "skip":   ErrorDecision.SKIP,
            "abort":  ErrorDecision.ABORT,
        }
        decision = decision_map[heuristic]
        print(f"[ErrorHandler] ⚡ Heuristic decision: {decision.value}")
        return {
            "decision":       decision,
            "reason":         error[:100],
            "fix_suggestion": "Use alternative tool",
            "max_retries":    1,
            "user_message":   "Adjusting approach, sir." if heuristic == "replan" else "Retrying, sir."
        }

    # Fall back to AI analysis
    try:
        client = _get_client()
        prompt = f"""Failed step:
Tool: {step.get('tool')}
Description: {step.get('description')}
Parameters: {json.dumps(step.get('parameters', {}), indent=2)}
Critical: {step.get('critical', False)}

Error:
{error[:400]}

Attempt number: {attempt}"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=gentypes.GenerateContentConfig(
                system_instruction=ERROR_ANALYST_PROMPT,
                temperature=0.0,
                max_output_tokens=256,
            )
        )
        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        result = json.loads(text)
        decision_str = result.get("decision", "replan").lower()
        decision_map = {
            "retry":  ErrorDecision.RETRY,
            "skip":   ErrorDecision.SKIP,
            "replan": ErrorDecision.REPLAN,
            "abort":  ErrorDecision.ABORT,
        }
        result["decision"] = decision_map.get(decision_str, ErrorDecision.REPLAN)

        # Never skip critical steps
        if step.get("critical") and result["decision"] == ErrorDecision.SKIP:
            result["decision"]    = ErrorDecision.REPLAN
            result["user_message"] = "Critical step failed — finding alternative, sir."

        print(f"[ErrorHandler] 🧠 AI decision: {result['decision'].value} — {result.get('reason', '')}")
        return result

    except Exception as e:
        print(f"[ErrorHandler] ⚠️ Analysis failed: {e} — defaulting to replan")
        return {
            "decision":       ErrorDecision.REPLAN,
            "reason":         str(e),
            "fix_suggestion": "Try alternative approach",
            "max_retries":    1,
            "user_message":   "Encountered an issue, adjusting, sir."
        }


def generate_fix(step: dict, error: str, fix_suggestion: str) -> dict:
    """Generate a replacement step when the original approach fails."""
    try:
        client = _get_client()

        prompt = f"""A task step failed. Generate a replacement approach.

Original step:
Tool: {step.get('tool')}
Description: {step.get('description')}
Parameters: {json.dumps(step.get('parameters', {}), indent=2)}

Error: {error[:300]}
Suggested fix: {fix_suggestion}

Return a JSON step object using one of these tools:
web_search, file_controller, browser_control, computer_settings, computer_control, code_helper

Return ONLY valid JSON:
{{
  "tool": "tool_name",
  "description": "what this replacement does",
  "parameters": {{}}
}}"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=gentypes.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=512,
            )
        )
        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        fix  = json.loads(text)

        return {
            "step":        step.get("step"),
            "tool":        fix.get("tool", "web_search"),
            "description": fix.get("description", f"Fix for: {step.get('description')}"),
            "parameters":  fix.get("parameters", {}),
            "critical":    step.get("critical", False)
        }

    except Exception as e:
        print(f"[ErrorHandler] ⚠️ Fix generation failed: {e}")
        # Safe fallback: web_search
        return {
            "step":        step.get("step"),
            "tool":        "web_search",
            "description": f"Fallback search for: {step.get('description')}",
            "parameters":  {"query": step.get("description", "")[:200]},
            "critical":    step.get("critical", False)
        }