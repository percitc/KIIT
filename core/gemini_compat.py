"""
core/gemini_compat.py — Capa de compatibilidad para Gemini
────────────────────────────────────────────────────────────
KITT usaba una mezcla de dos SDKs distintos de Google:
  - google-generativeai   (SDK viejo, en proceso de descontinuación)
  - google-genai          (SDK nuevo, el único soportado a futuro)

requirements.txt solo instala google-genai, así que cualquier módulo
que importara "google.generativeai" fallaba con ModuleNotFoundError.

Este módulo expone una única función `get_model()` que usa EXCLUSIVAMENTE
el SDK nuevo, pero mantiene la interfaz `.generate_content(prompt)` con
`.text` en la respuesta, igual que el SDK viejo. Así no hay que reescribir
cada llamada en cada archivo de acciones.

Autor de la corrección: Claude (auditoría solicitada por Perci)
"""

from __future__ import annotations

from google import genai
from google.genai import types


class CompatModel:
    """Envuelve google-genai para imitar la interfaz vieja de GenerativeModel."""

    def __init__(self, client: "genai.Client", model_name: str, system_instruction: str | None = None):
        self._client = client
        # Acepta tanto "gemini-2.5-flash" como "models/gemini-2.5-flash"
        self._model_name = model_name if model_name.startswith("models/") else model_name
        self._system_instruction = system_instruction

    def generate_content(self, prompt: str, **kwargs):
        config = None
        if self._system_instruction:
            config = types.GenerateContentConfig(system_instruction=self._system_instruction)
        try:
            return self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
                config=config,
            )
        except Exception as e:
            # Normalizamos el error para que el código llamador (que espera
            # .text en la respuesta) reciba algo legible en vez de reventar
            # con una traza confusa del SDK.
            raise RuntimeError(f"Gemini request failed ({self._model_name}): {e}") from e


def get_model(api_key: str, model_name: str, system_instruction: str | None = None) -> CompatModel:
    """
    Reemplazo directo de:
        genai.configure(api_key=...)
        model = genai.GenerativeModel(model_name, system_instruction=...)

    Uso:
        model = get_model(api_key, "gemini-2.5-flash-lite")
        response = model.generate_content("hola")
        print(response.text)
    """
    if not api_key or not api_key.strip():
        raise ValueError(
            "No hay API key de Gemini configurada. "
            "Abre KITT y completa la configuración inicial, o edita config/api_keys.json"
        )
    client = genai.Client(api_key=api_key)
    return CompatModel(client, model_name, system_instruction)
