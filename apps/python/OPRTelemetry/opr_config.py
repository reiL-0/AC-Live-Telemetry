"""Carga de configuracion para OPR Telemetry.

Lee `config.ini` junto al script. Si no existe, lo crea copiando
`config.ini.example` y devuelve valores por defecto (sin destinos -> pausa).

Destinos: una seccion `[backend:nombre]` por backend (url, token, server).
`[backend]` a secas (formato viejo) sigue valiendo: es un destino "default"
que acepta cualquier servidor.

Modulo con prefijo `opr_` a proposito: todas las apps de AC comparten
`sys.modules`, asi que un `config.py` "pelado" chocaria con el de otra app.
"""
import configparser
import os
import shutil

LAST_FILE = "last_backend.txt"


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

    if not os.path.isfile(cfg.path):
        example = os.path.join(app_dir, "config.ini.example")
        if os.path.isfile(example):
            try:
                shutil.copyfile(example, cfg.path)
            except OSError:
                pass
        return cfg  # sin destinos -> pausa

    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(cfg.path)
    except configparser.Error:
        return cfg

    def get(section, option, default):
        try:
            return parser.get(section, option).strip()
        except (configparser.NoSectionError, configparser.NoOptionError):
            return default

    for section in parser.sections():
        if section == "backend":
            name, server = "default", "*"
        elif section.startswith("backend:") and section[8:].strip():
            name, server = section[8:].strip(), get(section, "server", "")
        else:
            continue
        url = get(section, "url", "http://localhost:5000").rstrip("/")
        cfg.backends.append(Backend(name, url, get(section, "token", ""), server))

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
