#!/usr/bin/env python3
"""
generate_feed.py
----------------
Genera UN feed RSS combinado con los capítulos más recientes de todas las
series configuradas en series.yaml, desde tres fuentes:

  - MangaDex  -> API oficial (https://api.mangadex.org)            [fecha real]
  - Novelcool -> scraping HTML por patrón de URL /chapter/<slug>/<id>
  - ManhwaWeb -> API interna (manhwawebbackend ... railway.app)    [fecha real]

Guarda un estado "first-seen" (state.json) para deduplicar y fechar de forma
estable los capítulos sin fecha. Publica docs/feed.xml + docs/index.html.

Pensado para GitHub Actions + GitHub Pages.
Dependencias: requests, beautifulsoup4, feedgen, PyYAML, lxml
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
import yaml
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

UA = "Mozilla/5.0 (compatible; MangaFeedBot/1.0; +https://github.com)"
MANGADEX_API = "https://api.mangadex.org"
MANHWAWEB_API = "https://manhwawebbackend-production.up.railway.app"


# --------------------------- utilidades de fecha --------------------------- #
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(v: str) -> datetime:
    dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def from_ms(ms) -> str | None:
    try:
        return iso(datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc))
    except Exception:  # noqa: BLE001
        return None


# --------------------------- HTTP --------------------------- #
def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "es,en;q=0.8"})
    return s


def http_get(session: requests.Session, url: str, params=None, timeout: int = 25):
    last = None
    for attempt in range(1, 4):
        try:
            r = session.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt < 3:
                time.sleep(2 * attempt)
    raise RuntimeError(f"GET {url}: {last}")


# ===================== Adapter: MangaDex (API) ===================== #
def pick_title(attr_title, alt_titles, langs):
    pool = {}
    if isinstance(attr_title, dict):
        pool.update(attr_title)
    for d in (alt_titles or []):
        if isinstance(d, dict):
            for k, v in d.items():
                pool.setdefault(k, v)
    for lg in list(langs) + ["en"]:
        if lg in pool:
            return pool[lg]
    return next(iter(pool.values()), "MangaDex")


def parse_mangadex_response(data_list, langs):
    out = []
    for ch in data_list:
        a = ch.get("attributes", {}) or {}
        series = "MangaDex"
        for rel in ch.get("relationships", []):
            if rel.get("type") == "manga":
                ra = rel.get("attributes", {}) or {}
                series = pick_title(ra.get("title"), ra.get("altTitles"), langs)
        num = a.get("chapter") or "?"
        ctitle = a.get("title")
        lang = a.get("translatedLanguage", "")
        label = f"Cap. {num}"
        if ctitle:
            label += f" — {ctitle}"
        if lang:
            label += f" [{lang}]"
        url = a.get("externalUrl") or f"https://mangadex.org/chapter/{ch['id']}"
        try:
            date = iso(parse_iso(a["publishAt"]))
        except Exception:  # noqa: BLE001
            date = None
        out.append({"series": series, "label": label, "url": url,
                    "date": date, "guid": ch["id"], "source": "MangaDex"})
    return out


def mangadex_chapters(session, manga_id, langs, limit):
    params = [("limit", limit), ("manga", manga_id), ("order[publishAt]", "desc"),
              ("includes[]", "manga"), ("includes[]", "scanlation_group")]
    for cr in ("safe", "suggestive", "erotica", "pornographic"):
        params.append(("contentRating[]", cr))
    for lg in langs:
        params.append(("translatedLanguage[]", lg))
    r = http_get(session, f"{MANGADEX_API}/chapter", params=params)
    return parse_mangadex_response(r.json().get("data", []), langs)


# ===================== Adapter: ManhwaWeb (API interna) ===================== #
def parse_manhwaweb_response(data, limit):
    """Convierte el JSON de /manhwa/see/<slug> en items (sin red)."""
    series = (data.get("the_real_name") or data.get("name_esp")
              or data.get("name_raw") or data.get("_id") or "ManhwaWeb")
    chs = data.get("chapters") or []
    chs = sorted(chs, key=lambda c: c.get("create", 0) or 0, reverse=True)[:limit]
    out = []
    for c in chs:
        link = c.get("link")
        if not link:
            continue
        num = c.get("chapter")
        label = f"Cap. {num}" if num is not None else "Capítulo"
        out.append({"series": series, "label": label, "url": link,
                    "date": from_ms(c.get("create")), "guid": link, "source": "ManhwaWeb"})
    return out


def manhwaweb_chapters(session, slug, limit):
    r = http_get(session, f"{MANHWAWEB_API}/manhwa/see/{slug}")
    return parse_manhwaweb_response(r.json(), limit)


# ===================== Adapter: Novelcool (HTML) ===================== #
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_CHAP_PATH = re.compile(r"/chapter/.+/\d+")


def parse_novelcool_date(text: str):
    text = (text or "").strip()
    m = re.search(r"([A-Z][a-z]{2})\s+(\d{1,2}),\s*(\d{4})", text)
    if m and m.group(1) in _MONTHS:
        try:
            return iso(datetime(int(m.group(3)), _MONTHS[m.group(1)],
                                int(m.group(2)), tzinfo=timezone.utc))
        except Exception:  # noqa: BLE001
            pass
    rel = re.search(r"(\d+)\s*(hora|hour|min|d[ií]a|day|week|semana|mes|month)", text, re.I)
    if rel or re.search(r"nuevo|new", text, re.I):
        n = int(rel.group(1)) if rel else 1
        unit = (rel.group(2).lower() if rel else "hora")
        if unit.startswith(("d", "day")):
            delta = timedelta(days=n)
        elif unit.startswith(("week", "sem")):
            delta = timedelta(weeks=n)
        elif unit.startswith(("mes", "month")):
            delta = timedelta(days=30 * n)
        elif unit.startswith("min"):
            delta = timedelta(minutes=n)
        else:
            delta = timedelta(hours=n)
        return iso(now_utc() - delta)
    return None


def parse_novelcool_html(html: str, base_url: str, name: str, limit: int):
    soup = BeautifulSoup(html, "lxml")
    series = name
    h1 = soup.select_one("h1")
    if h1 and h1.get_text(strip=True):
        series = h1.get_text(strip=True)
    out, seen = [], set()
    for a in soup.select('a[href*="/chapter/"]'):
        href = a.get("href", "")
        if not _CHAP_PATH.search(href):
            continue
        full = urljoin(base_url, href)
        if full in seen:
            continue
        labelsrc = (a.get("title") or a.get_text(strip=True) or "").strip()
        if not re.search(r"(cap[ií]tulo|chapter|\bch\b|\d)", labelsrc, re.I):
            continue
        seen.add(full)
        parent = a.find_parent()
        ctx = parent.get_text(" ", strip=True) if parent else labelsrc
        date = parse_novelcool_date(ctx)
        label = re.sub(r"\s*(Nuevo|New)\b.*$", "", labelsrc, flags=re.I).strip() or "Capítulo"
        out.append({"series": series, "label": label, "url": full,
                    "date": date, "guid": full, "source": "Novelcool"})
        if len(out) >= limit:
            break
    return out


def novelcool_chapters(session, url, name, limit):
    r = http_get(session, url)
    return parse_novelcool_html(r.text, url, name, limit)


# ===================== Ensamblado del feed ===================== #
def collect(config):
    s = make_session()
    st = config.get("settings", {})
    langs = st.get("mangadex_languages", ["es-la", "es", "en"])
    pern = int(st.get("per_series_fetch", 5))
    chapters, report = [], []

    def run(label_src, key, fn):
        for e in (config.get(key) or []):
            ident = e.get("name") or e.get("id") or e.get("slug") or e.get("url")
            try:
                chs = fn(e)
                chapters.extend(chs)
                series = chs[0]["series"] if chs else ident
                report.append((series, label_src, len(chs), "ok"))
                print(f"✅ {label_src} {series}: {len(chs)}")
                time.sleep(0.3)
            except Exception as ex:  # noqa: BLE001
                report.append((ident, label_src, 0, f"error: {ex}"))
                print(f"❌ {label_src} {ident}: {ex}", file=sys.stderr)

    run("MangaDex", "mangadex", lambda e: mangadex_chapters(s, e["id"], langs, pern))
    run("ManhwaWeb", "manhwaweb", lambda e: manhwaweb_chapters(s, e["slug"], pern))
    run("Novelcool", "novelcool", lambda e: novelcool_chapters(s, e["url"], e.get("name", ""), pern))
    return chapters, report


def assemble(chapters, state, settings):
    now = now_utc()
    for ch in chapters:
        g = ch["guid"]
        st = state.get(g)
        if st is None:
            state[g] = {"first_seen": iso(now), "series": ch["series"], "label": ch["label"],
                        "url": ch["url"], "date": ch["date"], "source": ch["source"]}
        else:
            st["series"], st["label"], st["url"], st["source"] = (
                ch["series"], ch["label"], ch["url"], ch["source"])
            if ch["date"] and not st.get("date"):
                st["date"] = ch["date"]
    items = []
    for g, st in state.items():
        eff = st.get("date") or st.get("first_seen")
        items.append({**st, "guid": g, "eff": parse_iso(eff)})
    items.sort(key=lambda x: x["eff"], reverse=True)
    return items[:int(settings.get("max_items", 100))]


def write_outputs(items, report, settings, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    site = settings.get("site_url", "").rstrip("/")
    feed_url = f"{site}/feed.xml" if site else "urn:manga-feed"

    fg = FeedGenerator()
    fg.id(feed_url)
    fg.title(settings.get("feed_title", "Capítulos nuevos"))
    fg.link(href=feed_url, rel="self")
    fg.link(href=(site or "https://example.com"), rel="alternate")
    fg.description(settings.get("feed_description", "Capítulos nuevos"))
    fg.language("es")
    fg.lastBuildDate(now_utc())
    for it in items:
        fe = fg.add_entry(order="append")
        fe.id(it["url"])
        fe.guid(it["url"], permalink=True)
        fe.title(f"{it['series']} — {it['label']}")
        fe.link(href=it["url"])
        fe.pubDate(it["eff"])
        fe.description(f"[{it.get('source','')}] {it['series']} — {it['label']}")
    (out / "feed.xml").write_bytes(fg.rss_str(pretty=True))

    ok = sum(1 for r in report if r[3] == "ok")
    rows = "\n".join(
        f'<tr><td>{s}</td><td>{src}</td><td style="text-align:center">{n}</td>'
        f'<td>{"✅" if status=="ok" else "⚠️ "+status}</td></tr>'
        for (s, src, n, status) in sorted(report, key=lambda r: (r[1], str(r[0]).lower()))
    )
    updated = now_utc().strftime("%Y-%m-%d %H:%M UTC")
    (out / "index.html").write_text(f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{settings.get('feed_title','Feed de capítulos')}</title>
<style>
 :root{{color-scheme:light dark}}
 body{{font-family:system-ui,Segoe UI,Roboto,sans-serif;max-width:880px;margin:40px auto;padding:0 20px;line-height:1.5}}
 h1{{font-size:1.5rem}} code{{background:#8882;padding:2px 6px;border-radius:4px}}
 table{{border-collapse:collapse;width:100%;font-size:.9rem;margin-top:16px}}
 th,td{{border-bottom:1px solid #8883;padding:6px 8px;text-align:left}}
 .sub{{background:#6c63ff;color:#fff;padding:10px 16px;border-radius:8px;text-decoration:none;display:inline-block}}
 .meta{{color:#888;font-size:.85rem}}
</style></head><body>
<h1>📡 {settings.get('feed_title','Feed de capítulos')}</h1>
<p class="meta">Actualizado: {updated} · {ok}/{len(report)} series OK · {len(items)} capítulos en el feed</p>
<p><a class="sub" href="feed.xml">Suscribirse al feed RSS</a></p>
<p>Copia esta URL en tu lector (Feedly, Inoreader, etc.):<br><code>{feed_url}</code></p>
<table><thead><tr><th>Serie</th><th>Fuente</th><th>Caps</th><th>Estado</th></tr></thead>
<tbody>{rows}</tbody></table>
</body></html>
""", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Feed RSS combinado (MangaDex + ManhwaWeb + Novelcool).")
    ap.add_argument("--config", default="series.yaml")
    ap.add_argument("--output-dir", default="docs")
    ap.add_argument("--state", default="state.json")
    args = ap.parse_args()

    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    settings = config.get("settings", {})
    state_path = Path(args.state)
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    chapters, report = collect(config)
    items = assemble(chapters, state, settings)
    write_outputs(items, report, settings, Path(args.output_dir))
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = sum(1 for r in report if r[3] == "ok")
    print(f"\n📦 {ok}/{len(report)} series OK · {len(items)} capítulos → {args.output_dir}/feed.xml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
