"""Arma el paquete para Content Manager: dist/OPRTelemetry-<version>.zip

Content Manager instala un .zip arrastrandolo a su ventana (o Content > Apps)
si dentro tiene la estructura de la carpeta raiz de AC: apps/python/OPRTelemetry/...

Se excluyen `config.ini` (lleva el token del piloto), `last_backend.txt` y los
__pycache__: al actualizar la app desde CM no se pisa la config del piloto.

    python dev/build_zip.py
"""
import configparser
import hashlib
import os
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "apps", "python", "OPRTelemetry")
SKIP_DIRS = {"__pycache__"}
SKIP_FILES = {"config.ini", "last_backend.txt"}


def main():
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(os.path.join(APP, "manifest.ini"), encoding="utf-8")
    version = ini.get("ABOUT", "VERSION")

    out_dir = os.path.join(ROOT, "dist")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, "OPRTelemetry-{0}.zip".format(version))

    files = []
    for base, dirs, names in os.walk(APP):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        files += [os.path.join(base, n) for n in sorted(names)
                  if n not in SKIP_FILES and not n.endswith(".pyc")]

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for path in files:
            arc = "apps/python/OPRTelemetry/" + os.path.relpath(path, APP).replace(os.sep, "/")
            z.write(path, arc)
            print("  " + arc)

    with open(out, "rb") as f:
        print("\n{0}\nMD5 del zip: {1}".format(out, hashlib.md5(f.read()).hexdigest()))


if __name__ == "__main__":
    main()
