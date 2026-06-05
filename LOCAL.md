# 🔒 Uso local y privado

Tu lista de series y tu progreso quedan **solo en tu PC**; nada se publica en internet.

## Una sola vez
1. Instala **Python 3** desde https://python.org (marca *"Add Python to PATH"* al instalar).
2. En esta carpeta, abre una terminal y ejecuta:
   ```
   pip install -r requirements.txt
   ```

## Para usarlo (cada vez que quieras)
- Doble clic en **`actualizar.bat`**: baja los capítulos más recientes de las 92 series y abre el panel en tu navegador.
- En el panel marcas tu avance (se guarda en ese navegador). El botón **Exportar** te respalda el progreso.

## Automático (opcional)
Programador de tareas de Windows → *Crear tarea básica* → diaria → Acción: *Iniciar un programa* → selecciona `actualizar.bat`. Así se actualiza solo.

## Quitar lo que ya está público
Como antes lo subiste a GitHub, esa lista sigue siendo pública. Para borrarla:
- GitHub → tu repo `feed` → **Settings** → abajo del todo → **Delete this repository** (o **Change visibility → Private**, que apaga la página pública).

## Nota
- El **panel** (`docs/dashboard.html`) es la forma principal de uso local: ábrelo con doble clic.
- El `feed.xml` local solo lo leen lectores RSS de escritorio que acepten archivos locales; los lectores de celular necesitan una URL pública (por eso, en modo local, el seguimiento de novedades se hace desde el panel).
