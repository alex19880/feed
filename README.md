# 📡 Feed RSS combinado — Mangas y Novelas

Genera **un solo feed RSS** (`docs/feed.xml`) con los capítulos más recientes de
todas tus series, leyendo fuentes que **no ofrecen RSS** y se actualizan de forma
esporádica. Se ejecuta solo con **GitHub Actions** y se publica en **GitHub Pages**.

Te suscribes UNA vez en tu lector (Feedly, Inoreader, etc.) y recibes cada
capítulo nuevo de cualquier serie, sin revisar decenas de páginas a mano.

## Cobertura actual (92 series)

| Fuente | Series | Método | Fiabilidad |
|---|---|---|---|
| **MangaDex** | 41 | API oficial JSON | Alta — fecha real de publicación |
| **Novelcool** | 26 | Scraping HTML | Alta — server-rendered |
| **ManhwaWeb** | 25 | API interna (backend del sitio) | Alta — fecha real de publicación |

Las tres usan datos en JSON o HTML estable, fiables desde GitHub Actions y con
fecha de publicación real (salvo algún capítulo de Novelcool sin fecha, que se
data por *first-seen*).

### Pendiente (fase opcional)

Quedan ~42 series en sitios SPA/Cloudflare (manhwa-latino, mangasnosekai,
mangaplus, mangafire, etc.). manhwaweb se resolvió encontrando su API interna;
para el resto haría falta repetir ese trabajo (buscar su API) o usar un navegador
headless. Se puede añadir después.

## Puesta en marcha (5 pasos)

1. Sube esta carpeta a un repositorio de GitHub.
2. En `series.yaml`, cambia `site_url` por `https://TU-USUARIO.github.io/TU-REPO`.
3. **Settings → Pages →** *Deploy from a branch* → Branch `main`, carpeta `/docs` → *Save*.
4. **Settings → Actions → General → Workflow permissions →** *Read and write* → *Save*.
5. **Actions → Build RSS feed → Run workflow** (primera ejecución). Luego corre solo
   cada 12 h.

Tu feed quedará en `https://TU-USUARIO.github.io/TU-REPO/feed.xml`
y un panel de estado en `https://TU-USUARIO.github.io/TU-REPO/`.

## Añadir o quitar series

Solo editas `series.yaml`:

```yaml
# MangaDex: copia el UUID de la URL del título
#   https://mangadex.org/title/<UUID>/loquesea
mangadex:
  - id: "a9cfa101-8924-4dab-8e38-9516d921f3b8"

# ManhwaWeb: el slug tras /manhwa/ o /manga/ en la URL
#   https://manhwaweb.com/manhwa/<slug>
manhwaweb:
  - slug: "sousou-no-frieren_1696233652704"

# Novelcool: pega la URL completa de la novela
novelcool:
  - url: "https://es.novelcool.com/novel/Tonikaku-Kawaii.html"
    name: "Tonikaku-Kawaii"
```

Ajustes en `settings`: `mangadex_languages` (orden de idiomas preferidos),
`per_series_fetch` (capítulos consultados por serie), `max_items` (tamaño del feed).

## Probar en local (opcional)

```bash
pip install -r requirements.txt
python generate_feed.py --config series.yaml --output-dir docs --state state.json
# Abre docs/index.html
```

## Notas

- **Fechas:** MangaDex y ManhwaWeb aportan la fecha real de publicación; Novelcool
  se parsea del listado. Si una fecha no se puede leer, se usa la fecha en que el
  script vio el capítulo por primera vez (estable, vía `state.json`).
- **Primera ejecución:** el feed se llena con los capítulos actuales de cada serie
  (una "foto" inicial). A partir de ahí solo aparecen los realmente nuevos.
- **Frecuencia:** cada 12 h por defecto. Cámbiala en el `cron` del workflow.
- **Si una serie falla**, el resto del feed se genera igual y el fallo aparece en
  el panel `index.html`.
- **Coste:** gratis en repos públicos de GitHub.
- **Uso responsable:** respeta los términos y el `robots.txt` de cada sitio.
