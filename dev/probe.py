"""Prueba el endpoint SIN abrir Assetto Corsa.

Manda telemetria sintetica (un auto dando vueltas en circulo) a
`POST /api/telemetry/ingest`, reutilizando el mismo `opr_sender.Sender` que
usa la app in-game. Sirve para desarrollar el backend antes de tener AC.

    python dev/probe.py --url http://localhost:5000 --token EL_TOKEN --hz 8
"""
import argparse
import math
import os
import sys
import time

APP = os.path.abspath(os.path.join(os.path.dirname(__file__),
                                   "..", "apps", "python", "OPRTelemetry"))
sys.path.insert(0, APP)

from opr_sender import Sender  # noqa: E402


LAP_S = 20.0  # segundos por vuelta sintetica


def sample(t, steam_id=""):
    ang = t * 0.6
    s = math.sin(ang * 3)                      # >0 acelera, <0 frena
    speed = 150 + 90 * s
    gear = 2 + min(5, int(speed // 50))        # 0=R, 1=N, 2=1a...
    rpm = 3500 + 4800 * ((speed % 50) / 50)    # sube dentro de cada marcha, cae al cambiar
    lap = int(t // LAP_S)
    pace = 1 + 0.01 * math.sin(lap * 1.7)      # cada vuelta +-1% mas lenta/rapida: el delta se mueve
    heat = 70 + 25 * max(0.0, -s)              # las gomas se calientan al frenar
    return {
        "pos": {"x": round(200 * math.cos(ang), 3), "y": 0.0,
                "z": round(200 * math.sin(ang), 3)},
        "rotation": {"x": round((ang + math.pi / 2) % (2 * math.pi), 4), "y": 0.0, "z": 0.0},
        "speedKmh": round(speed, 1),
        "gear": gear,
        "rpm": int(rpm),
        "rpmMax": 8500,
        "throttle": round(max(0.0, s), 3),
        "brake": round(max(0.0, -s) * 0.9, 3),
        "clutch": 1.0,
        "steerAngle": round(90 * math.sin(ang * 2), 2),
        "steamId": steam_id,
        "lap": lap,
        "spline": round((t % LAP_S) / LAP_S, 4),
        "lastLapMs": int(LAP_S * 1000) if t >= LAP_S else 0,
        "lapTimeMs": int((t % LAP_S) * 1000 * pace),
        "fuel": round(max(0.0, 60 - t * 0.19), 2),   # ~3.8 L por vuelta
        "tyreTemp": [round(heat + 6, 1), round(heat + 2, 1), round(heat - 5, 1), round(heat - 7, 1)],
        "tyreTempI": [round(heat + 9 - i, 1) for i in (0, 1, 2, 3)],      # cara interna mas caliente que la externa
        "tyreTempM": [round(heat + 6 - i * 2, 1) for i in (0, 1, 2, 3)],
        "tyreTempO": [round(heat - 4 - i, 1) for i in (0, 1, 2, 3)],
        "brakeTemp": [int(150 + 600 * max(0.0, -s) - i * 40) for i in (0, 1, 2, 3)],
        "tyreCompound": "SM",
        "tyrePress": [27.8, 28.1, 27.2, 27.4],       # psi
        "tyreWear": [round(98.5 - t * 0.02 - i * 0.3, 2) for i in range(4)],   # escala AC, ~100 = nuevo
        "suspTravel": [round(0.05 + 0.02 * math.sin(ang * 4 + i) + 0.01 * max(0.0, s), 4) for i in range(4)],   # m
        "gLat": round(1.4 * math.sin(ang * 2), 2),
        "gLong": round(1.2 * s, 2),
        "car": "probe_car",
        "track": "probe_track",
        "trackLen": 1256.6,                    # circulo de radio 200 m
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5000")
    ap.add_argument("--token", required=True)
    ap.add_argument("--steam-id", default="", help="SteamID64 (17 digitos) del piloto que simula")
    ap.add_argument("--hz", type=float, default=8.0)
    ap.add_argument("--seconds", type=float, default=0.0, help="0 = infinito")
    args = ap.parse_args()

    s = Sender(args.url, args.token, timeout=2.0, debug=True)
    s.start()
    period = 1.0 / max(0.5, args.hz)
    t0 = time.monotonic()
    last_report = 0.0
    try:
        while True:
            now = time.monotonic() - t0
            if args.seconds and now >= args.seconds:
                break
            s.submit(sample(now, args.steam_id))
            if now - last_report >= 1.0:
                last_report = now
                print("[{0:6.1f}s] state={1:<10} sent={2:<5} code={3} {4}".format(
                    now, s.state, s.sent, s.last_code, s.detail))
            time.sleep(period)
    except KeyboardInterrupt:
        pass
    finally:
        s.stop()


if __name__ == "__main__":
    main()
