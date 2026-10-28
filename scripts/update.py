#!/usr/bin/env python3
"""Lee los puntos móviles de donación de sangre de la Comunidad de Madrid,
les asigna coordenadas y escribe data/puntos.json.

Uso:
  python scripts/update.py              # descarga la web y actualiza data/puntos.json
  python scripts/update.py --offline F  # usa filas de un JSON (pruebas), sin red
"""
import argparse
import datetime as dt
import difflib
import json
import pathlib
import re
import sys
import time
import unicodedata
from html.parser import HTMLParser

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
URL = "https://donarsangre.sanidadmadrid.org/moviles.aspx"
PREFIX = "ctl00$ContenedorContenidoSeccion$"
UA = "donar-sangre-madrid/1.0 (https://github.com; mapa de puntos de donacion)"
MAX_AGE_DAYS = 7  # descarta filas con fecha anterior a hace una semana


# ---------- lectura de la web ----------
class _Form(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = {}
        self.rows = []
        self._row = None
        self._cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("type") == "hidden" and a.get("name"):
            self.hidden[a["name"]] = a.get("value", "")
        elif tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", "".join(self._cell)).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if len(self._row) == 5:
                self.rows.append(self._row)
            self._row = None


def parse(html):
    p = _Form()
    p.feed(html)
    return p.hidden, p.rows


def fetch_rows():
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = UA
    r = s.get(URL, timeout=60)
    r.raise_for_status()
    fields, _ = parse(r.text)
    fields[PREFIX + "txtFecha"] = ""
    fields[PREFIX + "cbxMunicipio"] = "0"  # 0 = todos los municipios
    fields[PREFIX + "btnBuscar"] = "Buscar"
    r = s.post(URL, data=fields, timeout=60)
    r.raise_for_status()
    _, rows = parse(r.text)
    return rows


# ---------- normalización ----------
def strip_accents(s):
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def norm(s):
    s = strip_accents(s.lower())
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()


def clean_dir(raw):
    return re.sub(r"^(equipo m[oó]vil en|sala en)\s*", "", raw.strip(), flags=re.I).strip()


def tipo_de(raw):
    low = raw.lower()
    if low.startswith("sala") and "furgo" in low:
        return "SF"
    if low.startswith("sala"):
        return "S"
    return "M"


def horas(texto):
    t = [f"{int(h):02d}:{m}" for h, m in re.findall(r"(\d{1,2})[:.;](\d{2})", texto)]
    out = []
    for i in range(0, len(t) - 1, 2):
        par = [t[i], t[i + 1]]
        if par not in out:
            out.append(par)
    return out


def iso(fecha):
    d, m, y = fecha.split("/")
    return f"{y}-{m}-{d}"


def bonito(s):
    return s.title() if s.isupper() else s


# ---------- coordenadas ----------
def load(name, default):
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def match_seed(muni, lugar, direccion, seeds):
    """Busca entre las posiciones ya verificadas la que mejor encaja."""
    nums = set(re.findall(r"\d+", direccion))
    texto = norm(lugar + " " + direccion)
    mejor, mejor_s = None, 0.0
    for sd in seeds:
        if norm(sd["municipio"]) != norm(muni):
            continue
        sn = set(re.findall(r"\d+", sd["direccion"]))
        s = difflib.SequenceMatcher(None, texto, norm(sd["lugar"] + " " + sd["direccion"])).ratio()
        s = max(s, difflib.SequenceMatcher(None, norm(direccion), norm(sd["direccion"])).ratio())
        nd, ns = norm(direccion), norm(sd["direccion"])
        if len(ns) > 8 and (ns in nd or nd in ns):
            s = max(s, 0.9)  # una dirección contiene a la otra
        if nums and sn and not (nums & sn):
            s *= 0.5
        if s > mejor_s:
            mejor, mejor_s = sd, s
    return mejor if mejor_s >= 0.6 else None


def query_dir(direccion):
    d = re.sub(r"\(.*?\)", "", direccion)
    d = re.split(r"\b(junto|frente|esquina|esq\.?|jto|dentro|sobre)\b", d, flags=re.I)[0]
    d = re.sub(r"^\s*(sala|furgo)\s+en\s+", "", d, flags=re.I)
    return d.split("/Furgo")[0].strip(" ,.-")


def nominatim(q):
    import requests

    time.sleep(1.1)  # política de uso: 1 petición por segundo
    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"format": "json", "limit": 1, "countrycodes": "es", "q": q},
        headers={"User-Agent": UA},
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    return (float(j[0]["lat"]), float(j[0]["lon"])) if j else None


def geolocalizar(muni, lugar, direccion, seeds, cache, online):
    sd = match_seed(muni, lugar, direccion, seeds)
    if sd:
        return sd["lat"], sd["lon"], sd["lugar"], sd["direccion"], "verificada"
    key = f"{norm(muni)}|{norm(direccion)}"
    if key not in cache and online:
        res = None
        try:
            res = nominatim(f"{query_dir(direccion)}, {muni}, Comunidad de Madrid, España")
            tipo = "direccion"
            if not res:
                res = nominatim(f"{muni}, Comunidad de Madrid, España")
                tipo = "municipio"
        except Exception as e:  # sin red o límite: se reintenta en la próxima ejecución
            print(f"  aviso: no se pudo geocodificar {key}: {e}", file=sys.stderr)
        if res:
            cache[key] = {"lat": res[0], "lon": res[1], "precision": tipo}
    c = cache.get(key)
    if c:
        return c["lat"], c["lon"], bonito(lugar), direccion, c["precision"]
    return None, None, bonito(lugar), direccion, "sin_ubicacion"


# ---------- construcción ----------
def build(rows, online=True, hoy=None):
    hoy = hoy or dt.date.today()
    seeds = load("seeds.json", [])
    cache = load("coords_cache.json", {})
    entradas = []
    for muni, lugar, dire, fecha, horario in rows:
        try:
            f = dt.date.fromisoformat(iso(fecha))
        except ValueError:
            continue
        if (hoy - f).days > MAX_AGE_DAYS:
            continue
        d = clean_dir(dire)
        lat, lon, nombre, dir_ok, prec = geolocalizar(muni, lugar, d, seeds, cache, online)
        entradas.append({
            "fecha": f.isoformat(),
            "municipio": muni,
            "lugar": nombre,
            "direccion": dir_ok,
            "tipo": tipo_de(dire),
            "horarios": horas(horario),
            "lat": lat,
            "lon": lon,
            "precision": prec,
        })
    # une duplicados exactos (misma fecha y mismo sitio)
    vistos, unicos = set(), []
    for e in entradas:
        k = (e["fecha"], e["municipio"], e["lat"], e["lon"], e["direccion"])
        if k not in vistos:
            vistos.add(k)
            unicos.append(e)
    unicos.sort(key=lambda e: (e["fecha"], e["municipio"], e["lugar"]))
    return unicos, cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", help="JSON con filas [municipio, lugar, dirección, fecha, horario]")
    ap.add_argument("--hoy", help="fecha simulada AAAA-MM-DD (pruebas)")
    args = ap.parse_args()

    if args.offline:
        rows = json.loads(pathlib.Path(args.offline).read_text(encoding="utf-8"))
    else:
        rows = fetch_rows()
    if not rows:
        sys.exit("La web no devolvió ningún punto; no se modifica data/puntos.json")

    hoy = dt.date.fromisoformat(args.hoy) if args.hoy else None
    entradas, cache = build(rows, online=not args.offline, hoy=hoy)
    if not entradas:
        sys.exit("No quedó ningún punto vigente; no se modifica data/puntos.json")

    salida = DATA / "puntos.json"
    previo = load("puntos.json", {})
    if previo.get("entradas") == entradas:
        print("Sin cambios.")
    else:
        doc = {
            "actualizado": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "fuente": URL,
            "entradas": entradas,
        }
        salida.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(entradas)} entradas escritas en {salida}")
    (DATA / "coords_cache.json").write_text(json.dumps(cache, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    sin = [e for e in entradas if e["lat"] is None]
    if sin:
        print(f"{len(sin)} entradas sin ubicación:", {e['direccion'] for e in sin})


if __name__ == "__main__":
    main()
