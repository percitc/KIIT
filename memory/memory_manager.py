"""
memory/memory_manager.py — KITT Memory System
✅ Added: Session conversation logging to disk
✅ Improved: Smarter format_memory_for_prompt
✅ Improved: Thread-safe session log writes
"""

import os
import json
from datetime import datetime
from threading import Lock
from pathlib import Path
import sys


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR          = get_base_dir()
MEMORY_PATH       = BASE_DIR / "memory" / "long_term.json"
SESSIONS_DIR      = BASE_DIR / "memory" / "sessions"
_lock             = Lock()
_session_lock     = Lock()
MAX_VALUE_LENGTH  = 380
MEMORY_MAX_CHARS  = 6000   # Ampliado para no perder memorias importantes


# ── Empty state ───────────────────────────────────────────────────────────────

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
    }


# ── Load / Save ───────────────────────────────────────────────────────────────

def _load_memory_unlocked() -> dict:
    """Lectura sin adquirir _lock — solo para uso interno cuando el
    llamador ya sostiene el lock (evita condiciones de carrera en
    update_memory, ver más abajo)."""
    if not MEMORY_PATH.exists():
        return _empty_memory()
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            base = _empty_memory()
            for key in base:
                if key not in data:
                    data[key] = {}
            return data
        return _empty_memory()
    except Exception as e:
        print(f"[Memory] ⚠️ Load error: {e}")
        return _empty_memory()


def load_memory() -> dict:
    with _lock:
        return _load_memory_unlocked()


def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    return memory


def _save_memory_unlocked(memory: dict) -> None:
    """Escritura atómica sin adquirir _lock — solo para uso interno."""
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica: se escribe a un archivo temporal en el mismo
    # directorio y luego se reemplaza con os.replace (atómico en el mismo
    # filesystem). Así, si el proceso muere a mitad de la escritura,
    # long_term.json nunca queda corrupto/truncado.
    tmp_path = MEMORY_PATH.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(memory, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    os.replace(tmp_path, MEMORY_PATH)


def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    with _lock:
        _save_memory_unlocked(memory)


# ── Update ────────────────────────────────────────────────────────────────────

def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    # Todo el ciclo leer → modificar → escribir ocurre bajo UN mismo lock,
    # para que dos guardados concurrentes (ej. voz + comando de texto casi
    # simultáneos) no se pisen entre sí.
    with _lock:
        memory = _load_memory_unlocked()
        if _recursive_update(memory, memory_update):
            _save_memory_unlocked(memory)
            print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
    return memory


# ── Format for Prompt ─────────────────────────────────────────────────────────

def format_memory_for_prompt(memory: dict | None) -> str:
    if not memory:
        return ""

    lines = []

    identity  = memory.get("identity", {})
    id_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("")
        lines.append("Preferences:")
        for key, entry in list(prefs.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    projects = memory.get("projects", {})
    if projects:
        lines.append("")
        lines.append("Active Projects / Goals:")
        for key, entry in list(projects.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    rels = memory.get("relationships", {})
    if rels:
        lines.append("")
        lines.append("People in their life:")
        for key, entry in list(rels.items())[:10]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    wishes = memory.get("wishes", {})
    if wishes:
        lines.append("")
        lines.append("Wishes / Plans / Wants:")
        for key, entry in list(wishes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    notes = memory.get("notes", {})
    if notes:
        lines.append("")
        lines.append("Other notes:")
        for key, entry in list(notes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key}: {val}")

    if not lines:
        return ""

    header = "[LO QUE SABES SOBRE ESTA PERSONA — úsalo naturalmente, no lo recites como lista]\n"
    result = header + "\n".join(lines)
    if len(result) > 5500:
        result = result[:5497] + "…"

    return result + "\n"


# ── Session Logging ───────────────────────────────────────────────────────────

_current_session_path: Path | None = None


def _get_session_path() -> Path:
    global _current_session_path
    if _current_session_path is None:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        _current_session_path = SESSIONS_DIR / f"session_{stamp}.jsonl"
    return _current_session_path


def log_turn(role: str, text: str) -> None:
    """
    Append a conversation turn to the current session log.
    role: 'user' | 'mark'
    """
    if not text or not text.strip():
        return
    entry = {
        "ts":   datetime.now().isoformat(),
        "role": role,
        "text": text.strip()
    }
    try:
        with _session_lock:
            path = _get_session_path()
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[Memory] ⚠️ Session log error: {e}")


def load_recent_sessions(n_sessions: int = 3, max_turns: int = 20) -> str:
    """Load the last N sessions for context injection (future use)."""
    try:
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted(SESSIONS_DIR.glob("session_*.jsonl"), reverse=True)[:n_sessions]
        turns = []
        for f in files:
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    turns.append(json.loads(line))
                except Exception:
                    pass
        turns = turns[-max_turns:]
        if not turns:
            return ""
        lines = [f"{t['role'].upper()}: {t['text']}" for t in turns]
        return "[RECENT CONVERSATION HISTORY]\n" + "\n".join(lines) + "\n"
    except Exception:
        return ""


# ── Public helpers ────────────────────────────────────────────────────────────

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    with _lock:
        memory = _load_memory_unlocked()
        cat    = memory.get(category, {})
        if key in cat:
            del cat[key]
            memory[category] = cat
            _save_memory_unlocked(memory)
            return f"Forgotten: {category}/{key}"
        return f"Not found: {category}/{key}"


forget_memory = forget