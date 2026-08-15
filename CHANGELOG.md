# Changelog

## [Auditoría de seguridad y estabilidad] — 2026-08

Revisión completa del código previa a la publicación pública en GitHub.

### 🔴 Corregido — Crítico

- **Eliminada la ejecución de código arbitrario (`exec()`) en `actions/desktop.py`.**
  Antes, cuando pedías una tarea de escritorio en lenguaje libre, KITT le
  pedía al modelo que generara código Python y lo ejecutaba en un "sandbox"
  que en realidad era fácil de romper (exponía `getattr`/`hasattr`, y en
  Windows acceso directo a `ctypes`). Ahora Gemini solo **clasifica** la
  instrucción hacia una de las acciones seguras predefinidas
  (wallpaper / organize / clean / list / stats); si no encaja en ninguna,
  se lo informa al usuario en vez de generar código.
- **Unificado el SDK de Gemini.** `requirements.txt` solo instalaba
  `google-genai` (SDK nuevo), pero seis archivos (`flight_finder.py`,
  `code_helper.py`, `dev_agent.py`, `computer_settings.py`, `desktop.py`,
  `youtube_video.py`) importaban `google.generativeai` (SDK viejo,
  descontinuado y no instalado) — esas funciones fallaban siempre con
  `ModuleNotFoundError`. Se creó `core/gemini_compat.py` como capa de
  compatibilidad sobre el SDK nuevo, y se migraron los seis archivos.

### 🟠 Corregido — Alto

- **`shell=True` eliminado** en `actions/open_app.py` (lanzaba apps con
  `subprocess.Popen(app_name, shell=True)`, vulnerable a inyección si el
  nombre de la app contenía caracteres de shell) y en
  `actions/dev_agent.py` (apertura de VS Code).
- **Reconexión de sesión de Gemini Live realmente funcional.** Se activaba
  `session_resumption` pero nunca se capturaba ni reenviaba el
  `resumption_handle` devuelto por el servidor, así que cada reconexión
  empezaba una sesión totalmente nueva y perdía el contexto de la
  conversación. Ahora `main.py` captura `session_resumption_update.new_handle`
  y lo reutiliza en la siguiente conexión.
- **Condición de carrera y escritura no atómica en `memory/memory_manager.py`.**
  El ciclo leer → modificar → guardar ahora ocurre bajo un único lock, y el
  guardado en disco usa archivo temporal + `os.replace` (atómico), evitando
  que `long_term.json` quede corrupto si el proceso se cierra a mitad de
  una escritura.

### 🟡 Otros

- `requirements.txt` reescrito: se agregaron dependencias que el código
  usaba pero no estaban listadas (`PyPDF2`, `pdfplumber`, `pandas`,
  `openpyxl`, `python-docx`, `pydub`, `ddgs`), organizadas por categoría y
  con el bloque "Solo Windows" claramente separado.
- Documentación nueva para la publicación pública: `README.md` ampliado
  (requisitos, solución de problemas, seguridad, estructura del proyecto),
  `SECURITY.md` (modelo de amenazas) y `LICENSE` (MIT).

### Deuda técnica conocida (no bloqueante, queda para siguientes iteraciones)

- Existen ~66 bloques `except Exception: pass` silenciosos en el código
  (concentrados en `game_updater.py`, `browser_control.py`, `ui.py`,
  `system_monitor.py`, `open_app.py`). La mayoría son intentos de
  estrategias alternativas legítimas ("prueba A, si falla prueba B"), pero
  dificultan depurar fallos reales. Se recomienda ir agregando logging en
  vez de `pass` puro conforme se toque cada archivo.
- La API key se guarda en texto plano local; para un hardening mayor se
  podría migrar a `keyring` (llavero del sistema operativo).
