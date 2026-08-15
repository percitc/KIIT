"""
agent/executor.py — KITT Task Executor
✅ Fixed: google.generativeai → google.genai (new API)
✅ Fixed: MARK XXV → KITT
✅ Added: office_controller + system_monitor tool support
✅ Improved: Context injection, language detection, summary
"""

import json
import re
import sys
import threading
import subprocess
import tempfile
import os
from pathlib import Path
from typing import Callable

from agent.planner       import create_plan, replan
from agent.error_handler import analyze_error, generate_fix, ErrorDecision
from google import genai
from google.genai import types as gentypes


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


def _get_client() -> genai.Client:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        api_key = json.load(f)["gemini_api_key"]
    return genai.Client(api_key=api_key)


# ── Context Injection ─────────────────────────────────────────────────────────

def _inject_context(params: dict, tool: str, step_results: dict, goal: str = "") -> dict:
    """Inject previous step results into file write operations."""
    if not step_results:
        return params

    params = dict(params)

    if tool == "file_controller" and params.get("action") in ("write", "create_file"):
        content = params.get("content", "")
        if not content or len(content) < 50:
            all_results = [
                v for v in step_results.values()
                if v and len(v) > 100 and v not in ("Done.", "Completed.", "")
            ]
            if all_results:
                combined   = "\n\n---\n\n".join(all_results)
                translated = _translate_to_goal_language(combined, goal)
                params["content"] = translated
                print("[Executor] 💉 Injected context into file content")

    return params


# ── Language Detection & Translation ─────────────────────────────────────────

def _detect_language(text: str) -> str:
    try:
        client   = _get_client()
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f"What language is this text written in? "
                f"Reply with ONLY the language name in English (e.g. Spanish, Turkish, English).\n\n"
                f"Text: {text[:200]}"
            ),
            config=gentypes.GenerateContentConfig(
                temperature=0.0, max_output_tokens=10
            )
        )
        return response.text.strip()
    except Exception:
        return "English"


def _translate_to_goal_language(content: str, goal: str) -> str:
    if not goal:
        return content
    try:
        client      = _get_client()
        target_lang = _detect_language(goal)
        print(f"[Executor] 🌐 Translating to: {target_lang}")

        if target_lang.lower() == "english":
            return content

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f"Translate the following text into {target_lang}.\n"
                f"Keep all facts, numbers, structure and formatting intact.\n"
                f"Output ONLY the translated text, nothing else.\n\n"
                f"Text:\n{content[:4000]}"
            ),
            config=gentypes.GenerateContentConfig(
                temperature=0.1, max_output_tokens=4096
            )
        )
        translated = response.text.strip()
        print(f"[Executor] ✅ Translation done ({target_lang})")
        return translated
    except Exception as e:
        print(f"[Executor] ⚠️ Translation failed: {e}")
        return content


# ── Tool Dispatcher ───────────────────────────────────────────────────────────

def _call_tool(tool: str, parameters: dict, speak: Callable | None) -> str:

    if tool == "open_app":
        from actions.open_app import open_app
        return open_app(parameters=parameters, player=None) or "Done."

    elif tool == "web_search":
        from actions.web_search import web_search
        return web_search(parameters=parameters, player=None) or "Done."

    elif tool == "game_updater":
        from actions.game_updater import game_updater
        return game_updater(parameters=parameters, player=None, speak=speak) or "Done."

    elif tool == "browser_control":
        from actions.browser_control import browser_control
        return browser_control(parameters=parameters, player=None) or "Done."

    elif tool == "file_controller":
        from actions.file_controller import file_controller
        return file_controller(parameters=parameters, player=None) or "Done."

    elif tool == "code_helper":
        from actions.code_helper import code_helper
        return code_helper(parameters=parameters, player=None, speak=speak) or "Done."

    elif tool == "dev_agent":
        from actions.dev_agent import dev_agent
        return dev_agent(parameters=parameters, player=None, speak=speak) or "Done."

    elif tool == "screen_process":
        from actions.screen_processor import screen_process
        screen_process(parameters=parameters, player=None)
        return "Screen captured and analyzed."

    elif tool == "send_message":
        from actions.send_message import send_message
        return send_message(parameters=parameters, player=None) or "Done."

    elif tool == "reminder":
        from actions.reminder import reminder
        return reminder(parameters=parameters, player=None) or "Done."

    elif tool == "youtube_video":
        from actions.youtube_video import youtube_video
        return youtube_video(parameters=parameters, player=None) or "Done."

    elif tool == "weather_report":
        from actions.weather_report import weather_action
        return weather_action(parameters=parameters, player=None) or "Done."

    elif tool == "computer_settings":
        from actions.computer_settings import computer_settings
        return computer_settings(parameters=parameters, player=None) or "Done."

    elif tool == "desktop_control":
        from actions.desktop import desktop_control
        return desktop_control(parameters=parameters, player=None) or "Done."

    elif tool == "computer_control":
        from actions.computer_control import computer_control
        return computer_control(parameters=parameters, player=None) or "Done."

    elif tool == "flight_finder":
        from actions.flight_finder import flight_finder
        return flight_finder(parameters=parameters, player=None, speak=speak) or "Done."

    elif tool == "office_controller":
        from actions.office_controller import office_controller
        return office_controller(parameters=parameters, player=None) or "Done."

    elif tool == "system_monitor":
        from actions.system_monitor import system_monitor
        return system_monitor(parameters=parameters, player=None) or "Done."

    else:
        print(f"[Executor] ⚠️ Unknown tool '{tool}' — falling back to web_search")
        desc = parameters.get("description", str(parameters))
        return _call_tool("web_search", {"query": desc[:200]}, speak)


# ── Summary Generator ─────────────────────────────────────────────────────────

def _summarize(goal: str, completed_steps: list, speak: Callable | None) -> str:
    fallback = f"All done, sir. Completed {len(completed_steps)} step(s) for: {goal[:60]}."
    try:
        client    = _get_client()
        steps_str = "\n".join(f"- {s.get('description', '')}" for s in completed_steps)
        response  = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=(
                f'User goal: "{goal}"\n'
                f"Completed steps:\n{steps_str}\n\n"
                "Write ONE natural sentence summarizing what was accomplished. "
                "Address the user as 'sir'. Be direct and positive. Max 20 words."
            ),
            config=gentypes.GenerateContentConfig(
                temperature=0.3, max_output_tokens=64
            )
        )
        summary = response.text.strip()
        if speak:
            speak(summary)
        return summary
    except Exception:
        if speak:
            speak(fallback)
        return fallback


# ── Main Executor ─────────────────────────────────────────────────────────────

class AgentExecutor:

    MAX_REPLAN_ATTEMPTS = 2

    def execute(
        self,
        goal:        str,
        speak:       Callable | None        = None,
        cancel_flag: threading.Event | None = None,
    ) -> str:
        print(f"\n[Executor] 🎯 Goal: {goal}")

        replan_attempts = 0
        completed_steps = []
        step_results    = {}
        plan            = create_plan(goal)

        while True:
            steps = plan.get("steps", [])

            if not steps:
                msg = "I couldn't create a valid plan for this task, sir."
                if speak:
                    speak(msg)
                return msg

            success      = True
            failed_step  = None
            failed_error = ""

            for step in steps:
                if cancel_flag and cancel_flag.is_set():
                    if speak:
                        speak("Task cancelled, sir.")
                    return "Task cancelled."

                step_num = step.get("step", "?")
                tool     = step.get("tool", "web_search")
                desc     = step.get("description", "")
                params   = dict(step.get("parameters", {}))

                params = _inject_context(params, tool, step_results, goal=goal)

                print(f"\n[Executor] ▶️ Step {step_num}: [{tool}] {desc}")

                attempt = 1
                step_ok = False

                while attempt <= 3:
                    if cancel_flag and cancel_flag.is_set():
                        break
                    try:
                        result = _call_tool(tool, params, speak)
                        step_results[step_num] = result
                        completed_steps.append(step)
                        print(f"[Executor] ✅ Step {step_num}: {str(result)[:100]}")
                        step_ok = True
                        break

                    except Exception as e:
                        error_msg = str(e)
                        print(f"[Executor] ❌ Step {step_num} attempt {attempt}: {error_msg}")

                        recovery = analyze_error(step, error_msg, attempt=attempt)
                        decision = recovery["decision"]
                        user_msg = recovery.get("user_message", "")

                        if speak and user_msg:
                            speak(user_msg)

                        if decision == ErrorDecision.RETRY:
                            attempt += 1
                            import time; time.sleep(2)
                            continue

                        elif decision == ErrorDecision.SKIP:
                            print(f"[Executor] ⏭️ Skipping step {step_num}")
                            completed_steps.append(step)
                            step_ok = True
                            break

                        elif decision == ErrorDecision.ABORT:
                            msg = f"Task aborted, sir. {recovery.get('reason', '')}"
                            if speak:
                                speak(msg)
                            return msg

                        else:  # REPLAN
                            fix_suggestion = recovery.get("fix_suggestion", "")
                            if fix_suggestion:
                                try:
                                    fixed = generate_fix(step, error_msg, fix_suggestion)
                                    if speak:
                                        speak("Trying an alternative approach, sir.")
                                    res = _call_tool(fixed["tool"], fixed["parameters"], speak)
                                    step_results[step_num] = res
                                    completed_steps.append(step)
                                    step_ok = True
                                    break
                                except Exception as fix_err:
                                    print(f"[Executor] ⚠️ Fix failed: {fix_err}")

                            failed_step  = step
                            failed_error = error_msg
                            success      = False
                            break

                if not step_ok and not failed_step:
                    failed_step  = step
                    failed_error = "Max retries exceeded"
                    success      = False

                if not success:
                    break

            if success:
                return _summarize(goal, completed_steps, speak)

            if replan_attempts >= self.MAX_REPLAN_ATTEMPTS:
                msg = f"Task failed after {replan_attempts} replan attempts, sir."
                if speak:
                    speak(msg)
                return msg

            if speak:
                speak("Adjusting my approach, sir.")

            replan_attempts += 1
            plan = replan(goal, completed_steps, failed_step, failed_error)