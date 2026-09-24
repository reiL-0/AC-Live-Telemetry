"""OPR Telemetry - app in-game de Assetto Corsa.

Lee la telemetria del auto del jugador local (acelerador, freno, embrague,
marcha, rpm, posicion, rotacion, velocidad, angulo de direccion) y la envia
cada ~120 ms al backend de Open Paddock Racing League por HTTP POST.

El envio corre en un hilo aparte (opr_sender.Sender). `acUpdate` solo arma el
sample y lo deja en un slot; si el backend no responde el dato se descarta y
se reintenta en el proximo tick - el juego nunca se traba.

Entradas del juego: solo `ac.getCarState(0, ...)` - el auto propio. El destino
(que piloto es) lo decide el token, nunca un campo del JSON.

Destinos: config.ini define varios `[backend nombre]`. Al unirse a un servidor la
app lee su IP / puerto / nombre y elige el destino que coincida; el boton "Cambiar
destino" permite elegir uno a mano (vale hasta que cambie el servidor).
"""
import os
import sys
import time
import traceback

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import ac  # noqa: E402

# El Python de AC no trae _socket.pyd ni _ssl.pyd (http.client los necesita): van en esta
# carpeta y se encuentran por el sys.path de arriba. Si un import falla, AC solo dice
# "ERROR LOADING MODULE" sin el motivo; lo dejamos en py_log.txt antes de propagarlo.
try:
    import opr_config  # noqa: E402
    import opr_telemetry  # noqa: E402
    from opr_sender import Sender  # noqa: E402
except Exception:
    ac.log("OPR Telemetry: error al cargar la app (faltan _socket.pyd / _ssl.pyd?)\n" + traceback.format_exc())
    raise

APP_NAME = "OPR Telemetry"

DETECT_EVERY_S = 5.0   # cada cuanto se revisa a que servidor estamos conectados

_app_window = None
_label = None
_button = None
_sender = None
_cfg = None
_idx = None            # indice del destino activo en _cfg.backends
_manual = False        # el destino lo eligio el piloto con el boton
_server_key = None     # (ip, puerto, nombre) del ultimo servidor detectado
_interval_s = 0.12
_last_submit = 0.0
_last_detect = 0.0
_error_logged = False

_STATE_TEXT = {
    "starting":  "iniciando...",
    "no_token":  "falta el token en config.ini",
    "no_backend": "sin destino para este servidor",
    "ok":        "OK - enviados: {sent}",
    "waiting":   "esperando (auto no conectado aun)",
    "no_net":    "sin conexion al backend",
    "bad_token": "TOKEN INVALIDO - revisa config.ini",
    "http_err":  "error {code}",
    "cooldown":  "rate-limit, reintentando...",
}


def acMain(ac_version):
    global _app_window, _label, _button, _cfg, _interval_s

    _app_window = ac.newApp(APP_NAME)
    ac.setSize(_app_window, 300, 130)
    ac.setTitle(_app_window, APP_NAME)
    ac.drawBorder(_app_window, 0)

    _label = ac.addLabel(_app_window, "")
    ac.setPosition(_label, 12, 34)
    ac.setFontSize(_label, 14)

    _button = ac.addButton(_app_window, "Cambiar destino")
    ac.setPosition(_button, 12, 96)
    ac.setSize(_button, 140, 24)
    ac.addOnClickedListener(_button, _on_click)

    try:
        _cfg = opr_config.load(APP_DIR)
    except Exception:
        ac.log("OPR Telemetry: error leyendo config.ini\n" + traceback.format_exc())
        _cfg = opr_config.Config()

    _interval_s = _cfg.send_interval_ms / 1000.0
    if not _cfg.backends:
        ac.log("OPR Telemetry: config.ini sin [backend ...] - la app queda en pausa")
    _autoselect()
    return APP_NAME


def _call(name, default):
    """ac.<name>() tolerante: si esa version de AC no la trae, devuelve `default`."""
    try:
        return getattr(ac, name)() or default
    except Exception:
        return default


def _autoselect():
    """Si cambio el servidor, elige el destino que le corresponde."""
    global _server_key, _manual
    key = (str(_call("getServerIP", "")), int(_call("getServerHttpPort", 0)),
           str(_call("getServerName", "")))
    if key == _server_key:
        return
    _server_key = key
    _manual = False
    ac.log("OPR Telemetry: servidor ip={0} puerto_http={1} nombre={2}".format(*key))
    idx = opr_config.pick(_cfg.backends, *key)
    if idx is None:  # ninguno coincide: el ultimo elegido a mano, si existe
        last = opr_config.load_last(APP_DIR)
        idx = next((i for i, b in enumerate(_cfg.backends) if b.name == last), None)
    _use(idx)


def _use(idx):
    """Activa el destino `idx` (o ninguno). No bloquea: el sender viejo termina solo."""
    global _sender, _idx
    if _sender is not None:
        _sender.stop(wait=False)
    _idx = idx
    if idx is None:
        _sender = None
        return
    b = _cfg.backends[idx]
    _sender = Sender(b.url, b.token, _cfg.timeout_seconds, _cfg.debug)
    if b.token:
        _sender.start()
        ac.log("OPR Telemetry: destino '{0}' -> {1}".format(b.name, b.url))
    else:
        _sender.state = "no_token"
        ac.log("OPR Telemetry: destino '{0}' sin token en config.ini".format(b.name))


def _on_click(*args):
    """Boton: pasa al siguiente destino y lo recuerda como ultimo elegido."""
    global _manual
    if not _cfg.backends:
        return
    idx = 0 if _idx is None else (_idx + 1) % len(_cfg.backends)
    _manual = True
    _use(idx)
    opr_config.save_last(APP_DIR, _cfg.backends[idx].name)


def acUpdate(delta_t):
    global _last_submit, _last_detect, _error_logged
    try:
        _render()

        now = time.monotonic()
        if now - _last_detect >= DETECT_EVERY_S:
            _last_detect = now
            _autoselect()

        if _sender is None or _sender.state in ("no_token", "bad_token"):
            return

        if now - _last_submit < _interval_s:
            return
        _last_submit = now

        sample = opr_telemetry.read(0)
        if sample is not None:
            _sender.submit(sample)
    except Exception:
        if not _error_logged:
            _error_logged = True
            ac.log("OPR Telemetry: excepcion en acUpdate\n" + traceback.format_exc())


def _render():
    if _label is None:
        return
    if _idx is None or _sender is None:
        text = _STATE_TEXT["no_backend"] if _cfg.backends else _STATE_TEXT["no_token"]
        head = APP_NAME
    else:
        st = _sender
        text = _STATE_TEXT.get(st.state, st.state).format(sent=st.sent, code=st.last_code)
        if st.detail and st.state in ("no_net", "http_err"):
            text += "\n" + st.detail
        head = "{0} -> {1} ({2})".format(APP_NAME, _cfg.backends[_idx].name,
                                         "manual" if _manual else "auto")
    ac.setText(_label, head + "\n" + text)


def acShutdown():
    try:
        if _sender is not None:
            _sender.stop()
        opr_telemetry.shutdown()
    except Exception:
        pass
