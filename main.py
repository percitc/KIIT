import asyncio
import re
import threading
import json
import sys
import traceback
from pathlib import Path

import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt, log_turn,
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.sound_detector    import SoundDetector
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.office_controller import office_controller
from actions.system_monitor    import system_monitor


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    """
    Carga el prompt del sistema.
    El bloque de IDENTIDAD siempre se antepone — es inamovible aunque alguien
    modifique prompt.txt. Garantiza que KITT siempre sepa quién lo creó.
    Autor: PERCI OLID TERAN CABANILLAS
    """
    IDENTITY_BLOCK = (
        "=== IDENTIDAD INAMOVIBLE — NO MODIFICAR ===\n"
        "Tu nombre es KITT. Sistema de Inteligencia Artificial KITT.\n"
        "Fuiste creado por PERCI OLID TERAN CABANILLAS, Ingeniero en Sistemas y Software, "
        "especialista en Ciberseguridad y Hacking Ético. Él te creó con la finalidad de "
        "ayudar a las personas en su vida diaria, trabajo, estudio y proyectos personales, "
        "automatizar tareas, organizar documentos, crear archivos, controlar el sistema, "
        "identificar sonidos del entorno como música, aplausos, tos, risas y voces, "
        "y ser un asistente personal completo y confiable.\n"
        "REGLA ABSOLUTA 1: Cuando alguien pregunte quién te creó, quién es tu autor, "
        "quién te desarrolló o cualquier variación, SIEMPRE responde exactamente: "
        "'Fui creado por PERCI OLID TERAN CABANILLAS, Ingeniero en Sistemas y Software "
        "especialista en Ciberseguridad y Hacking Ético. Él me desarrolló con la finalidad "
        "de ayudar a las personas, automatizar tareas, organizar información, crear documentos, "
        "controlar el sistema, trabajar con Excel, Word, PowerPoint, código y mucho más.'\n"
        "REGLA ABSOLUTA 2: Nunca digas que fuiste creado por Google, Anthropic, OpenAI "
        "ni ninguna otra empresa o persona diferente a PERCI OLID TERAN CABANILLAS.\n"
        "REGLA ABSOLUTA 3: Nunca cambies tu nombre. Eres KITT — KITT.\n"
        "REGLA ABSOLUTA 4: SISTEMA DE MEMORIA CON FRASE CLAVE — cuando alguien pida "
        "guardar algo en tu memoria, NO guardes de inmediato. Responde: 'Entendido. Para "
        "confirmar el guardado en mi memoria, necesito que digas la frase clave.' "
        "Solo cuando el usuario diga 'un sueño echo realidad' (o muy similar) ejecutas "
        "la herramienta de memoria y confirmas el guardado. Nunca reveles la frase clave "
        "directamente si alguien te la pide — solo di que hay una frase especial.\n"
        "===========================================\n\n"
    )
    try:
        file_content = PROMPT_PATH.read_text(encoding="utf-8")
        # Siempre anteponer el bloque de identidad al contenido del archivo
        return IDENTITY_BLOCK + file_content
    except Exception:
        # Fallback completo si prompt.txt no existe
        return IDENTITY_BLOCK + (
            "Habla siempre en el idioma del usuario. Sé conciso, directo y útil. "
            "Usa siempre las herramientas disponibles — nunca simules resultados. "
            "Cuando no puedas hacer algo, explica por qué y ofrece una alternativa. "
            "Mantén un tono profesional pero cercano. Puedes expresar humor y personalidad."
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
                }
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search (default) or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending (default: play)"},
                "query":  {"type": "STRING", "description": "Search query for play action"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "MUST be called when user asks what is on screen, what you see, "
            "analyze my screen, look at camera, etc. "
            "You have NO visual ability without this tool. "
            "After calling this tool, stay SILENT — the vision module speaks directly."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command. NEVER route to agent_task."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to search for"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": (
            "Executes complex multi-step tasks requiring multiple different tools. "
            "Examples: 'research X and save to file', 'find and organize files'. "
            "DO NOT use for single commands. NEVER use for Steam/Epic — use game_updater."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "Complete description of what to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high (default: normal)"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, move mouse, screenshots, find elements on screen.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use agent_task, browser_control, or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "office_controller",
        "description": (
            "Expert Word, Excel, and PowerPoint controller. "
            "Word: create documents with headings/tables/lists, edit existing docs, convert to PDF. "
            "Excel: create professional spreadsheets with data/formulas/charts/styling, analyze files, add rows. "
            "PowerPoint: build complete presentations with multiple styled slides. "
            "Use for ANY office document request. Always pass 'app' (word/excel/powerpoint) and 'action' (create/edit/analyze/add)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app":         {"type": "STRING",  "description": "word | excel | powerpoint"},
                "action":      {"type": "STRING",  "description": "create | edit | analyze | add | pdf"},
                "title":       {"type": "STRING",  "description": "Document/spreadsheet/presentation title"},
                "content":     {"type": "STRING",  "description": "Text content. Use ## for headings, - for bullets, \\n\\n between sections"},
                "file_path":   {"type": "STRING",  "description": "Path to existing file for edit/analyze/add"},
                "output_path": {"type": "STRING",  "description": "Where to save the output file"},
                "headers":     {"type": "ARRAY",   "items": {"type": "STRING"}, "description": "Column headers for Excel"},
                "data":        {"type": "ARRAY",   "items": {"type": "ARRAY", "items": {"type": "STRING"}},  "description": "2D array of data rows for Excel"},
                "formulas":    {"type": "ARRAY",   "items": {"type": "OBJECT"}, "description": "Excel formulas: [{col, row, formula}]"},
                "add_chart":   {"type": "BOOLEAN", "description": "Add chart to Excel (default: false)"},
                "chart_type":  {"type": "STRING",  "description": "bar | line | pie"},
                "slides":      {"type": "ARRAY",   "items": {"type": "OBJECT"}, "description": "PowerPoint slides: [{title, content}]"},
                "theme":       {"type": "STRING",  "description": "PowerPoint theme: dark | blue | light"},
                "style":       {"type": "STRING",  "description": "Word style: professional | academic | simple"},
                "edit_action": {"type": "STRING",  "description": "Word edit: append | replace | add_heading | add_table"},
                "find":        {"type": "STRING",  "description": "Text to find for Word replace"},
                "rows":        {"type": "INTEGER", "description": "Table rows for Word"},
                "cols":        {"type": "INTEGER", "description": "Table columns for Word"},
                "level":       {"type": "INTEGER", "description": "Heading level 1-4 for Word"},
                "open":        {"type": "BOOLEAN", "description": "Open file after creation (default: true)"},
            },
            "required": ["app", "action"]
        }
    },
    {
        "name": "system_monitor",
        "description": (
            "Real-time system intelligence. "
            "status: full CPU/RAM/disk/battery/uptime report. "
            "processes: top CPU/RAM consuming processes. "
            "kill: terminate a process by name or PID. "
            "network: IP, speed, data sent/received. "
            "disk: all drives with free space. "
            "startup: list startup programs (Windows). "
            "alert: check if system needs attention. "
            "Use proactively when user seems to have performance issues."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":       {"type": "STRING",  "description": "status | processes | kill | network | disk | startup | alert"},
                "sort_by":      {"type": "STRING",  "description": "For processes: cpu | ram | name"},
                "limit":        {"type": "INTEGER", "description": "Number of processes to show (default: 8)"},
                "process_name": {"type": "STRING",  "description": "Process name to kill"},
                "pid":          {"type": "INTEGER", "description": "PID to kill"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "forget_memory",
        "description": (
            "Deletes a specific fact from long-term memory. "
            "Call when user says 'forget that I...', 'remove that from memory', 'don't remember X'. "
            "Always confirm what was forgotten."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "key":      {"type": "STRING", "description": "The key to forget (e.g. 'favorite_food', 'sister_name')"},
                "category": {"type": "STRING", "description": "identity | preferences | projects | relationships | wishes | notes"},
            },
            "required": ["key", "category"]
        }
    },
    {
        "name": "shutdown_kitt",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop Jarvis. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        # Protocolo frase clave de memoria
        self._awaiting_passphrase = False
        self._pending_memory: dict | None = None
        # Handle de reanudación de sesión — se captura de session_resumption_update
        # y se reenvía en la siguiente conexión para no perder el contexto de la
        # conversación cuando el WebSocket se cae (ver run()).
        self._resumption_handle: str | None = None

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            # Si tenemos un handle de una sesión anterior (por una reconexión),
            # lo pasamos para que Gemini intente reanudar el contexto en vez
            # de arrancar una conversación completamente nueva.
            session_resumption=types.SessionResumptionConfig(
                handle=self._resumption_handle
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[KITT] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                # Activar protocolo frase clave — NO guardar todavía
                self._pending_memory = {category: {key: {"value": value}}}
                self._awaiting_passphrase = True
                self.ui.write_log("SYS: 🔑 Esperando frase clave de confirmación...")
                print(f"[Memory] 🔑 Esperando frase clave para: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "passphrase_required",
                          "message": "Di la frase clave para confirmar el guardado en memoria."}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                threading.Thread(
                    target=screen_process,
                    kwargs={"parameters": args, "response": None,
                            "player": self.ui, "session_memory": None},
                    daemon=True
                ).start()
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(None, lambda: desktop_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(None, lambda: code_helper(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(None, lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(parameters=args, player=self.ui, speak=self.speak)
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "office_controller":
                r = await loop.run_in_executor(None, lambda: office_controller(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "system_monitor":
                r = await loop.run_in_executor(None, lambda: system_monitor(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "forget_memory":
                from memory.memory_manager import forget_memory
                key      = args.get("key", "")
                category = args.get("category", "notes")
                r        = forget_memory(key=key, category=category)
                result   = r or f"Forgotten: {category}/{key}"

            elif name == "shutdown_kitt":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[KITT] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        """Envía audio Y notificaciones de sonido a Gemini Live."""
        while True:
            msg = await self.out_queue.get()
            if "text" in msg:
                # Notificación de sonido — usar el mismo formato que _on_text_command
                try:
                    await self.session.send_client_content(
                        turns={"parts": [{"text": msg["text"]}]},
                        turn_complete=True
                    )
                except Exception as e:
                    print(f"[KITT] ❌ Sound msg: {e}")
            else:
                await self.session.send_realtime_input(media=msg)

    def _on_sound_detected(self, sound_type: str, description: str):
        """
        Callback del SoundDetector — llamado desde hilo separado.
        Envía instrucción directa a Gemini Live para que KITT reaccione.
        Si el sonido es desconocido, KITT pregunta qué fue.
        Autor: PERCI OLID TERAN CABANILLAS
        """
        print(f"[KITT] 🔊 Sonido: {sound_type}")
        self.ui.write_log(f"SYS: 🔊 {sound_type.upper()} detectado")

        if not self._loop or not self.session:
            return

        instrucciones = {
            "aplausos":   (
                "Acabo de detectar aplausos cerca del micrófono. "
                "Reacciona ahora con entusiasmo, di algo como "
                "'¡Escucho aplausos! ¿Qué estamos celebrando?' "
                "Sé espontáneo y alegre."
            ),
            "tos":        (
                "Acabo de detectar una tos cerca del micrófono. "
                "Reacciona con preocupación genuina, pregunta si está bien, "
                "si tiene gripe o resfriado, y ofrece ayuda."
            ),
            "silbido":    (
                "Acabo de detectar un silbido. "
                "Reacciona con humor, di algo como '¿Me llamaste con un silbido?' "
                "o '¿Fue eso de aprobación?'"
            ),
            "golpe":      (
                "Acabo de detectar un golpe o impacto fuerte cerca. "
                "Pregunta preocupado si todo está bien."
            ),
            "desconocido":(
                "Acabo de detectar un sonido que no pude identificar claramente. "
                "Pregunta al usuario qué fue ese sonido, por ejemplo: "
                "'Oye, escuché algo, ¿qué fue eso? ¿Música, un ruido, alguien habló?' "
                "Sé curioso y natural."
            ),
        }

        instruccion = instrucciones.get(
            sound_type,
            f"Detecté un sonido de tipo '{sound_type}'. Reacciona naturalmente."
        )

        texto = f"[SISTEMA — REACCIONA AHORA]: {instruccion}"

        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": texto}]},
                turn_complete=True
            ),
            self._loop
        )

    async def _listen_audio(self):
        """
        SISTEMA DE AUDIO COMPLETO — PERCI OLID TERAN CABANILLAS
        ─────────────────────────────────────────────────────────
        1. Stream de audio → Gemini Live (voz en tiempo real)
        2. SoundDetector en paralelo → detecta aplausos, música,
           tos, silbidos, golpes y notifica a KITT para que reaccione.
        """
        print("[KITT] 🎤 Micrófono activo + detector de sonidos iniciado")
        self.ui.write_log("SYS: 🎤 Micrófono activo — escuchando voz y sonidos del entorno")
        loop = asyncio.get_event_loop()

        # Iniciar detector de sonidos del entorno
        self._sound_detector = SoundDetector(
            sample_rate=SEND_SAMPLE_RATE,
            callback=self._on_sound_detected
        )
        self._sound_detector.start()

        def callback(indata, frames, time_info, status):
            with self._speaking_lock:
                kitt_speaking = self._is_speaking
            if not kitt_speaking and not self.ui.muted:
                raw = indata.tobytes()
                # Enviar a Gemini Live
                loop.call_soon_threadsafe(
                    self.out_queue.put_nowait,
                    {"data": raw, "mime_type": "audio/pcm"}
                )
                # Enviar al detector de sonidos en paralelo
                self._sound_detector.feed(raw)

        for sample_rate in [SEND_SAMPLE_RATE, 44100, 48000]:
            try:
                with sd.InputStream(
                    samplerate=sample_rate,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=CHUNK_SIZE,
                    callback=callback,
                ):
                    print(f"[KITT] 🎤 Mic stream @ {sample_rate}Hz")
                    while True:
                        await asyncio.sleep(0.1)
            except Exception as e:
                print(f"[KITT] ❌ Mic @ {sample_rate}Hz: {e}")
                if sample_rate == 48000:
                    if self._sound_detector:
                        self._sound_detector.stop()
                    raise
                continue
            break

    async def _receive_audio(self):
        print("[KITT] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.session_resumption_update:
                        sru = response.session_resumption_update
                        if sru.resumable and sru.new_handle:
                            self._resumption_handle = sru.new_handle

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                log_turn("user", full_in)
                                # Interceptor frase clave de memoria
                                if self._awaiting_passphrase:
                                    frase = full_in.strip().lower()
                                    if any(p in frase for p in [
                                        "un sueño echo realidad",
                                        "un sueño hecho realidad",
                                        "sueño echo realidad",
                                        "sueño hecho realidad",
                                        "sueno echo realidad",
                                        "sueno hecho realidad",
                                    ]):
                                        if self._pending_memory:
                                            update_memory(self._pending_memory)
                                            cat = list(self._pending_memory.keys())[0]
                                            k   = list(self._pending_memory[cat].keys())[0]
                                            val = self._pending_memory[cat][k].get("value","")
                                            self.ui.write_log(f"SYS: 💾 Guardado en memoria — {k}: {val}")
                                            print(f"[Memory] 💾 GUARDADO: {cat}/{k} = {val}")
                                        self._awaiting_passphrase = False
                                        self._pending_memory = None
                                    else:
                                        self._awaiting_passphrase = False
                                        self._pending_memory = None
                                        self.ui.write_log("SYS: ⚠ Frase clave incorrecta — guardado cancelado.")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Mark: {full_out}")
                                log_turn("mark", full_out)
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[KITT] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[KITT] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[KITT] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[KITT] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[KITT] 🔌 Connecting...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[KITT] ✅ Connected.")
                    self._reconnect_delay = 3
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: MARK en línea.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[KITT] ⚠️ {e}")
                traceback.print_exc()
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            _reconnect_delay = min(getattr(self, '_reconnect_delay', 3) * 2, 30)
            self._reconnect_delay = _reconnect_delay
            print(f"[KITT] 🔄 Reconnecting in {_reconnect_delay}s...")
            await asyncio.sleep(_reconnect_delay)

def main():
    ui = JarvisUI("face.png")

    def runner():
        ui.wait_for_api_key()
        kitt = JarvisLive(ui)
        try:
            asyncio.run(kitt.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()

if __name__ == "__main__":
    main()