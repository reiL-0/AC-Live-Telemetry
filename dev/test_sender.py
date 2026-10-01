"""Prueba la conexion keep-alive del Sender y el pico de freno, sin AC.
    python dev/test_sender.py
"""
import http.server
import os
import sys
import threading
import time
import types

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "python", "OPRTelemetry"))
sys.path.insert(0, APP)

brake = {"v": 0.0}
ac = types.ModuleType("ac")
ac.log = lambda m: None
ac.getCarState = lambda car, what: brake["v"] if what == "brake" else 0.0
acsys = types.ModuleType("acsys")
acsys.CS = types.SimpleNamespace(Brake="brake")
sys.modules["ac"], sys.modules["acsys"] = ac, acsys

import opr_sender  # noqa: E402
import opr_telemetry  # noqa: E402

# --- servidor HTTP/1.1 que cuenta conexiones y peticiones ---
stats = {"conns": 0, "reqs": 0}


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self):
        stats["conns"] += 1
        http.server.BaseHTTPRequestHandler.setup(self)

    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        stats["reqs"] += 1
        self.send_response(204)
        self.send_header("Content-Length", "0")
        self.end_headers()

    log_message = lambda *a: None


srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
s = opr_sender.Sender("http://127.0.0.1:%d" % srv.server_port, "t", 2.0)
for _ in range(5):
    s._send({"a": 1})
assert (stats["reqs"], stats["conns"]) == (5, 1), stats     # una sola conexion para las 5 muestras

s._conn.sock.close()                                         # el servidor "cierra" la conexion inactiva
s._send({"a": 1})
assert stats["reqs"] == 6 and s.state == "ok", (stats, s.state)   # reintenta con una conexion nueva
assert stats["conns"] == 2, stats

# --- pico de freno entre dos envios ---
opr_telemetry.sample_peaks(0)
for v in (0.0, 0.9, 0.0):                                    # toque corto entre dos muestras
    brake["v"] = v
    opr_telemetry.sample_peaks(0)
assert opr_telemetry._brake_peak == 0.9
srv.shutdown()

# --- http.client en cache sin SSL (otra app de AC lo importo antes) -> el Sender lo recarga ---
sys.modules["ssl"] = None
sys.modules.pop("http.client")
import http.client  # noqa: E402
assert not hasattr(http.client, "HTTPSConnection")
del sys.modules["ssl"]
c = opr_sender.Sender("https://127.0.0.1:1", "t", 2.0)._connection()
assert type(c).__name__ == "HTTPSConnection", c
print("ok")
