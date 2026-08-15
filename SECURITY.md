# Seguridad de KITT

KITT es un asistente que puede controlar tu computadora por voz, así que tiene un
modelo de amenazas distinto al de una app común. Este documento explica qué
protecciones existen y qué límites tiene el proyecto a propósito.

## Principios de diseño

1. **No hay ejecución de código arbitrario generado por el modelo.** Ninguna
   acción de KITT sobre tu sistema operativo (abrir programas, mover archivos,
   controlar el escritorio, editar documentos, etc.) se implementa pidiéndole
   al modelo que "escriba código y lo ejecutamos". Cada acción es una función
   de Python predefinida y con parámetros validados; el modelo solo elige
   **cuál** función llamar y con qué argumentos, nunca **qué código correr**.

2. **Acceso a archivos restringido a la carpeta del usuario.** `actions/file_controller.py`
   valida que cualquier ruta de archivo esté dentro de `Path.home()` antes de
   leer, mover o borrar algo, para evitar manipulación de rutas (path traversal).

3. **Tu API key nunca sale de tu máquina** salvo hacia la API oficial de Google
   (`generativelanguage.googleapis.com`). Se guarda en texto plano en
   `config/api_keys.json`, que está excluido de git vía `.gitignore`.

## Limitaciones conocidas (léelas antes de usar KITT en un equipo compartido)

- KITT puede **abrir aplicaciones y ejecutar acciones del sistema operativo**
  a partir de lo que interpreta de tu voz. Si alguien más tiene acceso físico
  o remoto a tu micrófono mientras KITT está escuchando, podría, en teoría,
  darle instrucciones. No lo uses en espacios donde no confíes en quién puede
  hablarle al micrófono.
- El agente de desarrollo (`actions/dev_agent.py`) y el ayudante de código
  (`actions/code_helper.py`) sí pueden **crear y escribir archivos de código**
  en carpetas de proyecto que tú indiques — revisa lo que generan antes de
  ejecutarlo, como harías con cualquier código de un tercero.
- La API key se almacena en texto plano localmente (no en el llavero del
  sistema operativo). Si compartes tu computadora, cualquier otra cuenta de
  usuario con acceso a esa carpeta podría leerla.

## Reportar una vulnerabilidad

Si encuentras un problema de seguridad, por favor abre un issue privado o
contacta directamente al autor del repositorio en vez de publicar detalles
de explotación públicamente, para dar tiempo a corregirlo.
