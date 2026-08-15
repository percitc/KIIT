# 🤖 K.I.T.T — Asistente de IA de Voz en Tiempo Real
### Por **Perci Olid Teran Cabanillas**

Asistente de voz en tiempo real con interfaz futurista rojo neón. Escucha, ve, entiende y controla tu computadora usando la API de Gemini Live. Compatible con Windows, macOS y Linux. Ejecución local. Cero suscripciones — solo pagas (o usas gratis) tu propia API key de Gemini.

---

## ✨ Descripción

KITT es un asistente de IA personal. Conecta el sistema operativo con la intención humana a través del diálogo natural: analiza tu pantalla, procesa documentos, detecta sonidos del entorno y ejecuta flujos de trabajo de varios pasos.

---

## 🚀 Capacidades

| Función | Descripción |
|---|---|
| 🎙️ Voz en tiempo real | Conversación de baja latencia en cualquier idioma (Gemini Live API) |
| 🖥️ Control del sistema | Abre apps, gestiona archivos, ajustes de volumen/brillo |
| 🧩 Tareas autónomas | Planificación de múltiples pasos con cola de tareas |
| 👁️ Visión | Captura y análisis de pantalla en tiempo real y webcam |
| 🧠 Memoria persistente | Recuerda proyectos, preferencias y contexto entre sesiones |
| 🔊 Detección de sonidos | Identifica aplausos, tos, silbidos y más |
| 📊 Oficina completa | Crea/edita Word, Excel, PowerPoint por voz |
| 💻 Agente de código | Escribe, edita y ayuda a depurar proyectos |
| 🌐 Búsqueda web | Búsquedas, resúmenes de YouTube, vuelos |

---

## ⚙️ Requisitos

- **Python 3.10 o superior** (el código usa sintaxis moderna de tipado, `str | None`)
- Una **API key de Gemini** gratuita (ver abajo)
- Micrófono y altavoces/audífonos
- **Windows, macOS o Linux** — algunas funciones (control de volumen del sistema, Office vía COM, notificaciones nativas) son exclusivas de Windows y se degradan de forma segura en otros sistemas operativos.

---

## ⚡ Instalación

```bash
git clone https://github.com/TU_USUARIO/KITT-IA.git
cd KITT-IA

# Recomendado: usar un entorno virtual
python3 -m venv venv
source venv/bin/activate        # En Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install              # necesario para búsqueda web / scraping

# Si usas Windows, además:
#   1. Descomenta el bloque "Solo Windows" en requirements.txt
#   2. pip install -r requirements.txt   (de nuevo, para instalar esas líneas)

python main.py
```

> La primera vez que abras KITT aparecerá una pantalla de configuración para ingresar tu API key de Gemini y tu sistema operativo. Se guarda localmente en `config/api_keys.json` (ese archivo está en `.gitignore` — nunca se sube a GitHub).

---

## 🔑 Consigue tu API Key de Gemini

1. Ve a [aistudio.google.com](https://aistudio.google.com) — es gratis.
2. Haz clic en **Get API Key** → **Create API Key**.
3. Pégala en la pantalla de configuración de KITT al iniciar por primera vez.

Una sola key funciona para todo: voz, visión, búsqueda, generación de documentos, etc. Ten en cuenta que la API de Gemini tiene límites de uso gratuito (rate limits) — si usas KITT intensivamente, revisa la [documentación de precios de Gemini](https://ai.google.dev/pricing).

---

## 🧯 Solución de problemas comunes

| Problema | Causa probable | Solución |
|---|---|---|
| `ModuleNotFoundError` al iniciar | Falta una dependencia | Vuelve a correr `pip install -r requirements.txt` dentro del entorno virtual activado |
| No abre apps / control del sistema no funciona en Windows | Faltan las dependencias de Windows | Descomenta el bloque "Solo Windows" en `requirements.txt` e instala de nuevo |
| Se corta la conversación de voz a los pocos minutos | Es un comportamiento conocido de la API Live de Gemini (desconexiones de WebSocket) | KITT reconecta automáticamente e intenta retomar el contexto; si el corte persiste, revisa tu conexión a internet |
| Error de API key | Key inválida, vencida o sin cuota | Genera una nueva key en aistudio.google.com y vuelve a completar la configuración inicial de KITT |
| La búsqueda web falla | Falta `playwright install` | Corre `playwright install` una vez, después de instalar `requirements.txt` |

---

## 🔒 Seguridad y privacidad

- Tu API key se guarda **solo localmente** en `config/api_keys.json` (excluido de git vía `.gitignore`). Nunca se envía a nadie más que a la API de Google.
- KITT **no ejecuta código arbitrario generado por el modelo**: todas las acciones sobre tu sistema (abrir apps, mover archivos, controlar el escritorio, etc.) pasan por funciones predefinidas y auditadas, no por generación libre de código.
- Las rutas de archivos que KITT puede tocar están restringidas a tu carpeta de usuario.
- Revisa `SECURITY.md` para más detalle sobre el modelo de amenazas y cómo reportar una vulnerabilidad.

---

## 🗂️ Estructura del proyecto

```
KITT/
├── main.py              # Punto de entrada, loop de audio/voz con Gemini Live
├── ui.py                # Interfaz gráfica (PyQt6)
├── agent/                # Planificador, ejecutor y cola de tareas autónomas
├── actions/              # Cada "herramienta" que KITT puede usar (abrir apps, archivos, oficina, etc.)
├── memory/                # Memoria persistente (JSON local)
├── core/                  # Utilidades compartidas (cliente Gemini, prompts)
└── config/                 # api_keys.json (generado en el primer arranque, no se sube a git)
```

---

## 🤝 Contribuir

Los pull requests son bienvenidos. Antes de enviar uno grande, abre un issue describiendo el cambio propuesto. Revisa `CHANGELOG.md` para ver el historial de correcciones recientes.

---

## 📄 Licencia

Este proyecto se distribuye bajo la licencia MIT — ver `LICENSE`.

---

## 👤 Autor

Desarrollado por **Perci Olid Teran Cabanillas**
Ingeniero en Sistemas y Software · Especialista en Ciberseguridad y Hacking Ético

⭐ Dale una estrella al repositorio para apoyar el proyecto.
