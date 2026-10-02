"""Envio de telemetria en un hilo aparte del loop de render.

Diseno: un unico 'slot' con el ultimo sample. Lo viejo se descarta, nunca se
acumula una cola. El worker se despierta con un Event, manda el sample por
HTTP y vuelve a dormir. Nada bloqueante toca el hilo principal del juego.

Codigos del backend:
    204  aceptado
    401  token invalido      -> se deja de enviar, se avisa en la UI
    409  guid no conectado   -> se sigue probando, sin alarmar (es lo normal
                                hasta que el leaderboard vea al piloto)
    429  rate-limit          -> pausa corta y reintento
"""
import json
import threading
import time
from urllib.parse import urlsplit

try:
    import ac
except ImportError:
    ac = None

INGEST_PATH = "/api/telemetry/ingest"


def _log(msg):
    if ac is not None:
        ac.log("OPR Telemetry: " + msg)


def _seconds(v):
    """Retry-After (segundos) -> int entre 0 y 600; 0 si falta o no es un numero."""
    try:
        return max(0, min(600, int(v)))
    except (TypeError, ValueError):
        return 0


class Sender(object):
    def __init__(self, url, token, timeout, debug=False, regen=None):
        parts = urlsplit(url if "://" in url else "http://" + url)
        self._scheme = parts.scheme or "http"
        self._host = parts.hostname or "localhost"
        self._port = parts.port or (443 if self._scheme == "https" else 80)
        self._path = parts.path.rstrip("/") + INGEST_PATH
        self._token = token or ""
        self._timeout = timeout
        self._debug = debug
        self._regen = regen        # () -> clave nueva; solo con `token = auto` (ver opr_key.py)

        self._lock = threading.Lock()
        self._latest = None
        self._wake = threading.Event()
        self._stop = False
        self._thread = None
        self._cooldown_until = 0.0
        self._conn = None

        # estado que lee el hilo principal para el recuadro
        self.state = "starting"
        self.sent = 0
        self.last_code = 0
        self.detail = ""

    # -- lo que llama el hilo principal ---------------------------------
    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="opr-telemetry-sender")
        self._thread.daemon = True
        self._thread.start()

    def submit(self, sample):
        if self.state == "bad_token":
            return
        with self._lock:
            self._latest = sample
        self._wake.set()

    def stop(self, wait=True):
        self._stop = True
        self._wake.set()
        t = self._thread
        if wait and t is not None:
            t.join(timeout=2.0)

    # -- worker --------------------------------------------------------
    def _run(self):
        _log("worker iniciado -> {0}://{1}:{2}{3}".format(
            self._scheme, self._host, self._port, self._path))
        while not self._stop:
            self._wake.wait(timeout=1.0)
            self._wake.clear()
            if self._stop:
                break
            with self._lock:
                sample = self._latest
                self._latest = None
            if sample is None:
                continue
            if time.monotonic() < self._cooldown_until:
                continue
            self._send(sample)

    def _connection(self):
        # http.client y ssl se importan aqui (hilo del sender), no al cargar la app: cargar
        # _ssl.pyd tarda ~100 ms y AC avisa "app lenta" si eso ocurre en su hilo.
        import http.client
        if self._scheme == "https":
            try:
                import ssl  # noqa: F401  http.client lo importa en silencio y, si falla, no define HTTPSConnection
            except ImportError as e:  # p. ej. "DLL load failed": suele faltar el runtime VC++ 2010
                raise RuntimeError("sin SSL (_ssl.pyd no carga): " + str(e))
            if not hasattr(http.client, "HTTPSConnection"):
                # Las apps de AC comparten interprete: otra app pudo importar http.client cuando _ssl
                # aun no cargaba y dejarlo en cache sin HTTPSConnection. Con _ssl disponible, se recarga.
                try:
                    from importlib import reload
                except ImportError:  # Python 3.3
                    from imp import reload
                reload(http.client)
            return http.client.HTTPSConnection(self._host, self._port, timeout=self._timeout)
        return http.client.HTTPConnection(self._host, self._port, timeout=self._timeout)

    def _drop(self):
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def _send(self, sample):
        body = json.dumps(sample).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer " + self._token,
        }
        reason = retry = None
        # Conexion keep-alive: abrir TCP+TLS por cada muestra (~250 ms via Cloudflare) no da para 8 Hz.
        for attempt in (0, 1):
            reused = self._conn is not None
            try:
                if self._conn is None:
                    self._conn = self._connection()
                self._conn.request("POST", self._path, body=body, headers=headers)
                resp = self._conn.getresponse()
                code = resp.status
                reason = resp.getheader("X-OPR-Reason")
                retry = resp.getheader("Retry-After")
                resp.read()
                break
            except Exception as exc:  # red caida, timeout, DNS, TLS...
                self._drop()
                if reused and attempt == 0:
                    continue  # la conexion pudo caducar en el servidor: una vez mas, con una nueva
                self.state = "no_net"
                self.detail = str(exc)[:80]
                if self._debug:
                    _log("sin red: " + self.detail)
                return

        self.last_code = code
        pause = _seconds(retry)     # orden del servidor (no esta conectado / servidor no autorizado): dejar de enviar
        if pause:
            self._cooldown_until = time.monotonic() + pause
        if code == 204:
            self.state = "ok"
            self.sent += 1
        elif code == 409:
            self.state = "waiting"
        elif code == 403:
            self.state = "unauthorized"
        elif code == 401:
            if reason == "key-other-steamid" and self._regen:
                self._token = self._regen()      # la carpeta de la app vino de otro piloto: clave propia
                self.state = "waiting"
                _log("la clave era de otro piloto: se genero una propia")
            else:
                self.state = "bad_token"
                _log("token invalido (401) - revisa config.ini")
        elif code == 429:
            self.state = "cooldown"
            if not pause:
                self._cooldown_until = time.monotonic() + 2.0
        else:
            self.state = "http_err"
            self.detail = "HTTP {0}".format(code)
        if self._debug and code != 204:
            _log("respuesta {0}".format(code))
