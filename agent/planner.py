"""
agent/planner.py — KITT Planning Module
✅ Fixed: google.generativeai → google.genai (new API)
✅ Fixed: MARK XXV → KITT
✅ Improved: Better tool routing, cleaner prompts, faster model calls
"""

import json
import re
import sys
from pathlib import Path
from google import genai
from google.genai import types as gentypes


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

PLANNER_PROMPT = """\
You are the planning module of KITT — a hyper-intelligent personal AI assistant.
Your job: break any user goal into the MINIMUM number of steps using ONLY the tools listed below.

ABSOLUTE RULES:
- NEVER use generated_code. It does not exist.
- NEVER reference previous step results in parameters. Every step is independent.
- Use web_search for ANY information retrieval or research.
- Use file_controller to save content to disk.
- Max 5 steps. Use the minimum steps needed.
- Prefer a single tool call over multi-step plans when possible.

AVAILABLE TOOLS:

open_app          | app_name: string (required)
web_search        | query: string (required) | mode: search|compare | items: list | aspect: string
game_updater      | action: update|install|list|download_status|schedule | platform: steam|epic|both | game_name: string | app_id: string | shutdown_when_done: bool
browser_control   | action: go_to|search|click|type|scroll|get_text|press|close | url: string | query: string | text: string | direction: up|down
file_controller   | action: write|create_file|read|list|delete|move|copy|find|disk_usage|largest | path: string | name: string | content: string | count: int
computer_settings | action: string | description: string | value: string
computer_control  | action: type|click|hotkey|press|scroll|screenshot|screen_find|screen_click | text: string | x: int | y: int | keys: string | direction: up|down | description: string
screen_process    | text: string (required) | angle: screen|camera
send_message      | receiver: string (required) | message_text: string (required) | platform: string (required)
reminder          | date: YYYY-MM-DD (required) | time: HH:MM (required) | message: string (required)
desktop_control   | action: wallpaper|organize|clean|list|task | path: string | task: string
youtube_video     | action: play|summarize|trending | query: string
weather_report    | city: string (required)
flight_finder     | origin: string (required) | destination: string (required) | date: string (required)
code_helper       | action: write|edit|run|explain | description: string | language: string | output_path: string | file_path: string
dev_agent         | description: string (required) | language: string
office_controller | app: word|excel|powerpoint | action: create|edit|analyze|add|pdf | title: string | content: string | headers: list | data: list | slides: list
system_monitor    | action: status|processes|kill|network|disk|startup|alert | process_name: string | sort_by: cpu|ram|name

EXAMPLES:

Goal: "research mechanical engineering and save it to a file"
{"goal":"...","steps":[
  {"step":1,"tool":"web_search","description":"Research mechanical engineering","parameters":{"query":"mechanical engineering overview applications future"},"critical":true},
  {"step":2,"tool":"file_controller","description":"Save results to desktop","parameters":{"action":"create_file","path":"desktop","name":"mechanical_engineering.txt","content":"Results will be filled from step 1"},"critical":false}
]}

Goal: "What is the Bitcoin price"
{"goal":"...","steps":[
  {"step":1,"tool":"web_search","description":"Get Bitcoin price","parameters":{"query":"Bitcoin price today USD 2025"},"critical":true}
]}

Goal: "Create an Excel with monthly sales"
{"goal":"...","steps":[
  {"step":1,"tool":"office_controller","description":"Create Excel spreadsheet","parameters":{"app":"excel","action":"create","title":"Monthly Sales","headers":["Month","Sales","Target"],"data":[["January","0","0"]]},"critical":true}
]}

Goal: "How is my system doing"
{"goal":"...","steps":[
  {"step":1,"tool":"system_monitor","description":"Full system status","parameters":{"action":"status"},"critical":true}
]}

OUTPUT — return ONLY valid JSON, no markdown, no explanation:
{
  "goal": "...",
  "steps": [
    {
      "step": 1,
      "tool": "tool_name",
      "description": "what this step does",
      "parameters": {},
      "critical": true
    }
  ]
}
"""


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _get_client() -> genai.Client:
    return genai.Client(api_key=_get_api_key())


def _sanitize_steps(plan: dict, goal: str) -> dict:
    """Remove forbidden tools and patch bad parameter types."""
    for step in plan.get("steps", []):
        # Kill generated_code
        if step.get("tool") in ("generated_code", "python_code"):
            step["tool"] = "web_search"
            step["parameters"] = {"query": step.get("description", goal)[:200]}
        # Ensure parameters is always a dict
        if not isinstance(step.get("parameters"), dict):
            step["parameters"] = {}
    return plan


def create_plan(goal: str, context: str = "") -> dict:
    client = _get_client()

    user_input = f"Goal: {goal}"
    if context:
        user_input += f"\n\nContext: {context}"

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user_input,
            config=gentypes.GenerateContentConfig(
                system_instruction=PLANNER_PROMPT,
                temperature=0.1,
                max_output_tokens=1024,
            )
        )
        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        plan = json.loads(text)

        if "steps" not in plan or not isinstance(plan["steps"], list):
            raise ValueError("Invalid plan structure — missing steps")

        plan = _sanitize_steps(plan, goal)

        print(f"[Planner] ✅ Plan: {len(plan['steps'])} step(s)")
        for s in plan["steps"]:
            print(f"  Step {s['step']}: [{s['tool']}] {s['description']}")

        return plan

    except json.JSONDecodeError as e:
        print(f"[Planner] ⚠️ JSON parse failed: {e}")
        return _fallback_plan(goal)
    except Exception as e:
        print(f"[Planner] ⚠️ Planning failed: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    print("[Planner] 🔄 Using fallback plan")
    return {
        "goal": goal,
        "steps": [
            {
                "step": 1,
                "tool": "web_search",
                "description": f"Search for: {goal}",
                "parameters": {"query": goal[:200]},
                "critical": True
            }
        ]
    }


def replan(goal: str, completed_steps: list, failed_step: dict, error: str) -> dict:
    client = _get_client()

    completed_summary = "\n".join(
        f"  - Step {s['step']} ({s['tool']}): DONE" for s in completed_steps
    )

    prompt = f"""Goal: {goal}

Already completed:
{completed_summary if completed_summary else '  (none)'}

Failed step: [{failed_step.get('tool')}] {failed_step.get('description')}
Error: {error[:300]}

Create a REVISED plan for the remaining work only. Do not repeat completed steps.
Use a DIFFERENT approach or tool than what failed."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=gentypes.GenerateContentConfig(
                system_instruction=PLANNER_PROMPT,
                temperature=0.2,
                max_output_tokens=1024,
            )
        )
        text = response.text.strip()
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        plan = json.loads(text)
        plan = _sanitize_steps(plan, goal)

        print(f"[Planner] 🔄 Revised plan: {len(plan['steps'])} step(s)")
        return plan

    except Exception as e:
        print(f"[Planner] ⚠️ Replan failed: {e}")
        return _fallback_plan(goal)