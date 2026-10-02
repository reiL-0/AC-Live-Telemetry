"""Clave automatica de esta instalacion, para destinos con `token = auto`.

Se genera sola la primera vez y queda en device_key.txt (el zip no lo trae: cada instalacion
tiene la suya). El servidor la liga al SteamID del piloto cuando figura conectado. Si el piloto le
pasa la carpeta de la app a otro, el servidor la rechaza (esa clave es de otro SteamID) y la app
genera una nueva con renew().
"""
import binascii
import os

FILE = "device_key.txt"


def _new():
    return "auto_" + binascii.hexlify(os.urandom(16)).decode("ascii")   # el servidor espera auto_ + 32 hex


def load(app_dir):
    """La clave guardada, o una nueva (que se guarda) si no hay o esta danada."""
    try:
        with open(os.path.join(app_dir, FILE)) as f:
            key = f.read().strip()
        if key.startswith("auto_") and len(key) == 37:
            return key
    except (IOError, OSError):
        pass
    return renew(app_dir)


def renew(app_dir):
    key = _new()
    try:
        with open(os.path.join(app_dir, FILE), "w") as f:
            f.write(key)
    except (IOError, OSError):
        pass   # sin escritura: la clave vale esta sesion y la proxima sera otra (el servidor la rota)
    return key
