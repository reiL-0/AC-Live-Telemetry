"""Carga de configuracion para OPR Telemetry.

Lee `config_defaults.ini` (viene con la app: valores por defecto + descripciones
para el editor de Content Manager) y encima `config.ini` (lo del piloto, sobre todo
el token; lo crea CM al guardar y el zip no lo trae, asi una actualizacion no lo
pisa). Las claves de config.ini ganan. Sin ninguno de los dos -> sin destinos -> pausa.

Destinos: una seccion `[backend nombre]` por backend (url, token, server). Content
Manager solo muestra un .ini si TODOS sus nombres de seccion son letras, numeros, espacio o guion, asi que
el separador es un espacio; `[backend:nombre]` (formato anterior) sigue valiendo, y
si el mismo nombre aparece en config_defaults.ini y en config.ini se combinan clave
a clave. Un destino sin `url` se ignora (asi el "extra" del zip queda apagado).
`[backend]` a secas (formato viejo) es un destino "default" que acepta cualquier servidor.

Modulo con prefijo `opr_` a proposito: todas las apps de AC comparten
`sys.modules`, asi que un `config.py` "pelado" chocaria con el de otra app.
"""
import configparser
import os
import re

_BACKEND_RE = re.compile(r"^backend[: ]\s*(.+)$", re.IGNORECASE)
LAST_FILE = "last_backend.txt"
DEFAULTS_FILE = "config_defaults.ini"


class Backend(object):
    def __init__(self, name, url, token, server):
        self.name = name
        self.url = url
        self.token = token
        self.server = server  # patrones separados por coma; "*" = cualquiera


class Config(object):
    def __init__(self):
        self.backends = []
        self.send_interval_ms = 120
        self.timeout_seconds = 2.0
        self.debug = False
        self.path = ""


def load(app_dir):
    cfg = Config()
    cfg.path = os.path.join(app_dir, "config.ini")

    # ";" al final de una linea = comentario (formato del editor de CM: "clave = valor ; descripcion").
    # utf-8-sig: CM puede guardar con BOM.
    parser = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=(";",))
    try:
        parser.read([os.path.join(app_dir, DEFAULTS_FILE), cfg.path], encoding="utf-8-sig")
    except (configparser.Error, UnicodeDecodeError):
        return cfg

    def get(section, option, default):
        try:
            return parser.get(section, option).strip()
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    found = {}   # nombre -> {url, token, server}; defaults primero, config.ini encima
    for section in parser.sections():
        m = _BACKEND_RE.match(section)
        if section == "backend":
            name = "default"
        elif m:
            name = m.group(1).strip()
        else:
            continue
        e = found.setdefault(name, {"url": "http://localhost:5000", "token": "",
                                    "server": "*" if name == "default" else ""})
        for key in e:
            if parser.has_option(section, key):
                e[key] = parser.get(section, key).strip()
    for name, e in found.items():
        if e["url"]:
            cfg.backends.append(Backend(name, e["url"].rstrip("/"), e["token"], e["server"]))

    try:
        cfg.send_interval_ms = int(float(get("telemetry", "send_interval_ms", "120")))
    except ValueError:
        pass
    try:
        cfg.timeout_seconds = float(get("telemetry", "timeout_seconds", "2.0"))
    except ValueError:
        pass
    cfg.debug = get("telemetry", "debug", "0").lower() in ("1", "true", "yes", "on")
    return cfg


def _matches(pattern, ip, port, name):
    """`pattern` = IP, IP:puerto_http o parte del nombre del servidor."""
    p = pattern.strip().lower()
    if not p:
        return False
    if p == ip.lower() or p == "{0}:{1}".format(ip, port).lower():
        return bool(ip)
    return p in name.lower()


def pick(backends, ip, port, name):
    """Indice del destino para este servidor, o None. Gana el primero que
    coincida por IP / IP:puerto / nombre; si ninguno, el primero con `*`."""
    fallback = None
    for i, b in enumerate(backends):
        pats = [x for x in b.server.split(",") if x.strip()]
        if any(_matches(x, ip, port, name) for x in pats if x.strip() != "*"):
            return i
        if fallback is None and any(x.strip() == "*" for x in pats):
            fallback = i
    return fallback


def load_last(app_dir):
    """Nombre del ultimo destino elegido a mano, o ""."""
    try:
        with open(os.path.join(app_dir, LAST_FILE)) as f:
            return f.read().strip()
    except (IOError, OSError):
        return ""


def save_last(app_dir, name):
    try:
        with open(os.path.join(app_dir, LAST_FILE), "w") as f:
            f.write(name)
    except (IOError, OSError):
        pass
