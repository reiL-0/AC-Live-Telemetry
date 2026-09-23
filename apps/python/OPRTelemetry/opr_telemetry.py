"""Lectura de la telemetria del auto local.

Usa el modulo `ac` para pedales / marcha / rpm / velocidad / posicion / steer,
y `opr_mmap` para la orientacion. Devuelve el dict ya con el esquema exacto
que espera `POST /api/telemetry/ingest`, o None si no estamos en un auto.
"""
try:
    import ac
    import acsys
except ImportError:  # fuera de AC (para poder importar el modulo en dev)
    ac = None
    acsys = None

try:
    import winreg
except ImportError:  # fuera de Windows
    winreg = None

import opr_mmap

_STEAM64_BASE = 76561197960265728
_steam_id = ""
_ident = None  # (auto, pista, largo_m); no cambia durante la sesion


def _r(v, n):
    return round(v, n)


def _steam():
    """SteamID64 del usuario activo de Steam (registro de Windows), o ""."""
    global _steam_id
    if not _steam_id and winreg is not None:
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess")
            uid = winreg.QueryValueEx(key, "ActiveUser")[0]
            if uid:
                _steam_id = str(_STEAM64_BASE + uid)
        except Exception:
            pass
    return _steam_id


def _car_track(car_id):
    global _ident
    if _ident is None:
        track = ac.getTrackName(car_id)
        cfg = ac.getTrackConfiguration(car_id)
        try:
            length = float(ac.getTrackLength(car_id) or 0.0)   # metros
        except Exception:
            length = 0.0
        _ident = (ac.getCarName(car_id), track + "/" + cfg if cfg else track, length)
    return _ident


def read(car_id=0):
    """Payload listo para enviar, o None si getCarState no devuelve nada util
    (menus, repeticion sin auto, etc.)."""
    if ac is None:
        return None

    pos = ac.getCarState(car_id, acsys.CS.WorldPosition) or (0.0, 0.0, 0.0)
    px, py, pz = pos[0], pos[1], pos[2]
    speed = ac.getCarState(car_id, acsys.CS.SpeedKMH) or 0.0

    if px == 0.0 and py == 0.0 and pz == 0.0 and speed == 0.0:
        return None

    gas = ac.getCarState(car_id, acsys.CS.Gas) or 0.0
    brake = ac.getCarState(car_id, acsys.CS.Brake) or 0.0
    clutch = ac.getCarState(car_id, acsys.CS.Clutch)
    if clutch is None:
        clutch = 1.0  # 1.0 = embrague suelto en AC
    gear = ac.getCarState(car_id, acsys.CS.Gear) or 0       # 0=R, 1=N, 2=1a... (igual que ACSP)
    rpm = ac.getCarState(car_id, acsys.CS.RPM) or 0.0
    steer = ac.getCarState(car_id, acsys.CS.Steer) or 0.0   # grados

    lap = ac.getCarState(car_id, acsys.CS.LapCount) or 0
    spline = ac.getCarState(car_id, acsys.CS.NormalizedSplinePosition) or 0.0
    last_lap = ac.getCarState(car_id, acsys.CS.LastLap) or 0   # ms
    lap_time = ac.getCarState(car_id, acsys.CS.LapTime) or 0   # ms de la vuelta en curso
    best_lap = ac.getCarState(car_id, acsys.CS.BestLap) or 0   # ms, mejor de la sesion
    ex = opr_mmap.extras()
    zero4 = (0.0, 0.0, 0.0, 0.0)
    ex = ex or {}
    g = lambda k: ex.get(k, zero4)
    acc = ex.get("acc", (0.0, 0.0))
    car, track, track_len = _car_track(car_id)

    hpr = opr_mmap.heading_pitch_roll()
    heading, pitch, roll = hpr if hpr is not None else (0.0, 0.0, 0.0)

    return {
        "pos": {"x": _r(px, 3), "y": _r(py, 3), "z": _r(pz, 3)},
        "rotation": {"x": _r(heading, 4), "y": _r(pitch, 4), "z": _r(roll, 4)},
        "speedKmh": _r(speed, 1),
        "gear": int(round(gear)),
        "rpm": int(round(rpm)),
        "throttle": _r(gas, 3),
        "brake": _r(brake, 3),
        "clutch": _r(clutch, 3),
        "steerAngle": _r(steer, 2),
        "rpmMax": int(opr_mmap.max_rpm()),   # limite del auto actual; 0 si no se pudo leer
        # extras para el backend de graficas (el backend de OPR WP los ignora)
        "steamId": _steam(),
        "lap": int(lap),
        "spline": _r(spline, 4),
        "lastLapMs": int(last_lap),
        "lapTimeMs": int(lap_time),
        "bestLapMs": int(best_lap),
        "fuel": _r(ex.get("fuel", 0.0), 2),                          # litros; 0 fuera de AC
        "tyreTemp": [_r(t, 1) for t in g("tyre")],        # FL, FR, RL, RR (°C, nucleo)
        "tyrePress": [_r(p, 2) for p in g("press")],       # FL, FR, RL, RR (psi)
        "tyreWear": [_r(w, 2) for w in g("wear")],         # FL, FR, RL, RR (escala AC, ~100 = nuevo)
        "suspTravel": [_r(t, 4) for t in g("susp")],       # FL, FR, RL, RR (metros)
        "tyreTempI": [_r(t, 1) for t in g("tyreI")],   # cara interna / media / externa (°C)
        "tyreTempM": [_r(t, 1) for t in g("tyreM")],
        "tyreTempO": [_r(t, 1) for t in g("tyreO")],
        "brakeTemp": [_r(t, 0) for t in g("brake")],   # °C
        "tyreCompound": opr_mmap.compound(),
        "gLat": _r(acc[0], 2),
        "gLong": _r(acc[1], 2),
        "car": car,
        "track": track,
        "trackLen": _r(track_len, 1),         # metros; 0 si AC no lo dio
    }


def shutdown():
    opr_mmap.close()
