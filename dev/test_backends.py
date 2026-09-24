"""Prueba la eleccion de destino sin abrir AC (simula el modulo `ac`).
    python dev/test_backends.py
"""
import os
import sys
import tempfile
import types

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "python", "OPRTelemetry"))
sys.path.insert(0, APP)

# --- `ac` falso -----------------------------------------------------------
server = {"ip": "", "port": 0, "name": ""}
labels = {}
ac = types.ModuleType("ac")
ac.log = lambda m: None
ac.newApp = lambda n: 1
ac.setSize = ac.setTitle = ac.drawBorder = ac.setPosition = ac.setFontSize = lambda *a: None
ac.addLabel = lambda w, t: 10
ac.addButton = lambda w, t: 11
ac.addOnClickedListener = lambda b, cb: labels.__setitem__("click", cb)
ac.setText = lambda h, t: labels.__setitem__("text", t)
ac.getServerIP = lambda: server["ip"]
ac.getServerHttpPort = lambda: server["port"]
ac.getServerName = lambda: server["name"]
sys.modules["ac"] = ac

import opr_config  # noqa: E402

INI = """
[backend:opr]
url = http://127.0.0.1:1
token = t1
server = Open Paddock, 5.6.7.8

[backend:graficas]
url = http://127.0.0.1:2/
token = t2
server = *

[backend:privado]
url = http://127.0.0.1:3
token =
server = 9.9.9.9:8081
"""
d = tempfile.mkdtemp()
with open(os.path.join(d, "config.ini"), "w") as f:
    f.write(INI)
cfg = opr_config.load(d)
assert [b.name for b in cfg.backends] == ["opr", "graficas", "privado"]
assert cfg.backends[1].url == "http://127.0.0.1:2"          # sin "/" final

# --- pick ----------------------------------------------------------------
pick = lambda ip, port, name: opr_config.pick(cfg.backends, ip, port, name)
assert pick("1.1.1.1", 80, "OPEN PADDOCK Racing #1") == 0     # por nombre, sin mayusculas
assert pick("5.6.7.8", 8081, "otro") == 0                     # por IP
assert pick("9.9.9.9", 8081, "x") == 2                        # por IP:puerto
assert pick("9.9.9.9", 9999, "x") == 1                        # otro puerto -> comodin
assert pick("", 0, "") == 1                                   # sin servidor -> comodin
assert opr_config.pick([b for b in cfg.backends if b.name == "privado"], "1.1.1.1", 0, "x") is None

# --- formato viejo ---------------------------------------------------------
d2 = tempfile.mkdtemp()
with open(os.path.join(d2, "config.ini"), "w") as f:
    f.write("[backend]\nurl = http://x:5000\ntoken = abc\n")
old = opr_config.load(d2).backends
assert len(old) == 1 and old[0].name == "default" and old[0].server == "*" and old[0].token == "abc"

# --- config_defaults.ini (viene en el zip) + config.ini (lo del piloto, lo guarda CM) ---
import shutil  # noqa: E402
d3 = tempfile.mkdtemp()
shutil.copy(os.path.join(APP, "config_defaults.ini"), d3)
solo = opr_config.load(d3)                                     # recien instalada: sin config.ini
assert [b.name for b in solo.backends] == ["graficas"]        # "extra" sin url: apagado
import re  # noqa: E402
with open(os.path.join(APP, "config_defaults.ini")) as f:
    names = re.findall(r"^\[(.+)\]", f.read(), re.M)
assert all(re.match(r"^[\w -]+$", n) for n in names), names    # si no, Content Manager no muestra el archivo
b = solo.backends[0]
assert (b.url, b.token, b.server) == ("https://oppenpaddockracing.site", "", "*"), vars(b)
assert (solo.send_interval_ms, solo.timeout_seconds, solo.debug) == (120, 2.0, False)
with open(os.path.join(d3, "config.ini"), "w", encoding="utf-8-sig") as f:   # como lo guarda CM: con BOM
    f.write("[backend graficas]\ntoken = abc123 ; Tu token\n\n[backend extra]\nurl = http://h:9\ntoken = z\nserver = 1.2.3.4\n\n[telemetry]\ndebug = 1\n")
mix = opr_config.load(d3)
b = mix.backends[0]
assert (b.url, b.token, b.server) == ("https://oppenpaddockracing.site", "abc123", "*"), vars(b)
assert mix.debug and mix.send_interval_ms == 120
assert [(x.name, x.url, x.server) for x in mix.backends[1:]] == [("extra", "http://h:9", "1.2.3.4")]
with open(os.path.join(d3, "config.ini"), "w") as f:            # config.ini del formato anterior: se combina con los defaults
    f.write("[backend:graficas]\ntoken = viejo\n")
leg = opr_config.load(d3).backends
assert [(x.name, x.url, x.token) for x in leg] == [("graficas", "https://oppenpaddockracing.site", "viejo")], leg

# --- app: deteccion + boton ---------------------------------------------------
import OPRTelemetry as app  # noqa: E402

app.APP_DIR = d                                                # que no toque la config real
app.acMain("1.0")                                              # carga config, registra el boton, autoselecciona
assert app._idx == 1 and not app._manual                       # sin servidor -> "graficas"
server.update(ip="1.1.1.1", port=80, name="Open Paddock #2")
app._autoselect()
assert app._idx == 0 and app._sender.state != "no_token"
old_sender = app._sender
labels["click"]()                                              # boton: siguiente destino
assert app._idx == 1 and app._manual and app._sender is not old_sender
assert opr_config.load_last(d) == "graficas"
labels["click"](); labels["click"]()                           # -> privado (sin token) -> opr
assert app._idx == 0
labels["click"](); labels["click"]()                           # opr -> graficas -> privado
assert app._idx == 2 and app._sender.state == "no_token"
app._autoselect()                                              # mismo servidor: respeta lo manual
assert app._idx == 2 and app._manual
server.update(ip="5.6.7.8")                                    # otro servidor: vuelve a auto
app._autoselect()
assert app._idx == 0 and not app._manual
app._render()
assert "opr" in labels["text"] and "auto" in labels["text"]

# ninguno coincide y sin comodin -> ultimo elegido a mano, o nada
app._cfg.backends = [b for b in app._cfg.backends if b.name != "graficas"]
server.update(ip="7.7.7.7", name="zzz")
opr_config.save_last(d, "nada")
app._autoselect()
assert app._idx is None and app._sender is None
app._render()
assert "sin destino" in labels["text"]

if app._sender:
    app._sender.stop()
print("ok")
