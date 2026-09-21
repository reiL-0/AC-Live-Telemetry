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
    return {
        "pos": {"x": round(200 * math.cos(ang), 3), "y": 0.0,
                "z": round(200 * math.sin(ang), 3)},
        "rotation": {"x": round((ang + math.pi / 2) % (2 * math.pi), 4), "y": 0.0, "z": 0.0},
        "speedKmh": 187.0,
        "gear": 4,
        "rpm": 6200,
        "throttle": round(0.5 + 0.5 * math.sin(ang * 3), 3),
        "brake": 0.0,
        "clutch": 1.0,
        "steerAngle": round(12 * math.sin(ang), 2),
        "steamId": steam_id,
        "lap": int(t // LAP_S),
        "spline": round((t % LAP_S) / LAP_S, 4),
        "lastLapMs": int(LAP_S * 1000) if t >= LAP_S else 0,
        "car": "probe_car",
        "track": "probe_track",
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
