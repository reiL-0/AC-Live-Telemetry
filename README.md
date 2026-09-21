# AC Live Telemetry

App Python para **Assetto Corsa** (se instala con Content Manager o a mano) que lee la
telemetría de **tu auto** y la envía cada ~120 ms por HTTP a un backend: pedales, marcha,
rpm, velocidad, dirección, posición y rotación. Nace para el live-map de
[Open Paddock Racing League](https://github.com/reiL-0), pero funciona con cualquier
backend que implemente el [contrato](#contrato-del-endpoint).

## Cómo funciona

```
AC (loop de render)
  acUpdate  ── lee ac.getCarState(0, ...) + memoria compartida (heading)
            └─ deja el sample en un slot
hilo worker ── POST <url>/api/telemetry/ingest   Authorization: Bearer <token>
            └─ si falla: descarta y reintenta al próximo tick (nunca traba el juego)
```

- **Solo tu auto.** Lee `ac.getCarState(0, ...)`; no tiene acceso a otros pilotos. La
  identidad del piloto la decide el backend a partir del **token**, no el JSON.
- **Nunca bloquea el juego.** El envío corre en un hilo aparte con un único slot: si la red
  falla o tarda, se pierde ese sample, no se acumula cola.
- **No manda tiempos.** Vueltas, sectores y posición de carrera no salen de acá; solo
  telemetría instantánea del auto.
- **Varios destinos.** Al unirte a un servidor de AC la app elige a qué backend enviar
  según su IP, puerto HTTP o nombre (ver [Configuración](#configuración)).

## Instalación

### Con Content Manager (recomendado)

1. Genera el paquete: `python dev/build_zip.py` → `dist/OPRTelemetry-<versión>.zip`.
2. Arrastra el `.zip` a la ventana de Content Manager y confirma.
3. Activa la app en *Settings → Assetto Corsa → Python Apps* de CM.
4. Abre AC una vez: la app crea `config.ini` a partir de `config.ini.example`. Edítalo
   (destinos y tokens) y reinicia AC.

El zip no incluye `config.ini`, así que **actualizar la app desde CM no borra tu token**.

### A mano

1. Copia `apps/python/OPRTelemetry/` a `.../steamapps/common/assettocorsa/apps/python/`.
2. Copia `config.ini.example` a `config.ini` y complétalo.
3. En AC: *Settings → General → UI Modules → OPR Telemetry* = ON.

Dentro de una sesión, activa el ícono de la app: el recuadro muestra el estado
(`OK - enviados: N`, `esperando`, `sin conexión`, `TOKEN INVÁLIDO`…).

## Configuración

`config.ini` tiene un bloque `[backend:nombre]` por destino y un bloque `[telemetry]`:

```ini
[backend:opr]
url = https://tu-dominio-de-opr
token = EL_TOKEN_DEL_PILOTO
server = Open Paddock          ; IP, IP:puerto_http o parte del nombre; "*" = cualquier otro

[telemetry]
send_interval_ms = 120         ; 100-150 recomendado
timeout_seconds = 2.0
debug = 0                      ; 1 = log de cada envío en py_log.txt (nunca el token)
```

- Cada backend tiene su propio token; un token solo sirve en su backend.
- Al entrar a un servidor, la app escribe su IP, puerto y nombre en `py_log.txt`: usa esos
  valores en `server`. La coincidencia no distingue mayúsculas y admite varios valores
  separados por coma.
- El botón **Cambiar destino** de la ventana elige uno a mano (vale mientras no cambies de
  servidor; se recuerda en `last_backend.txt` para servidores sin coincidencia).
- Un `[backend]` a secas (formato viejo) sigue funcionando.

## Contrato del endpoint

```
POST <url>/api/telemetry/ingest
Authorization: Bearer <token>
Content-Type: application/json

{
  "pos":      {"x": float, "y": float, "z": float},
  "rotation": {"x": float, "y": float, "z": float},   // radianes (x = heading)
  "speedKmh": float,
  "gear": int,        // 0=R, 1=N, 2=1ª...
  "rpm": int,
  "throttle": float,  // 0..1
  "brake": float,     // 0..1
  "clutch": float,    // 0..1  (1.0 = embrague suelto)
  "steerAngle": float // grados
}
```

Además envía `steamId` (SteamID64 leído del registro de Windows), `lap`, `spline`,
`lastLapMs`, `car` y `track`; un backend puede ignorarlos.

| Código | Significado | Reacción de la app |
|---|---|---|
| `204` | Aceptado | `enviados++`, estado `OK` |
| `401` | Token inválido | deja de enviar y muestra `TOKEN INVÁLIDO` |
| `409` | Piloto aún no conectado en el backend | sigue probando en silencio |
| `429` | Rate-limit | pausa ~2 s y reintenta |
| red caída / timeout / TLS | — | `sin conexión`, reintenta al próximo tick |

## Estructura

```
apps/python/OPRTelemetry/       <- la carpeta que se instala en AC
  OPRTelemetry.py               entry points de AC (acMain / acUpdate / acShutdown)
  opr_config.py                 lee config.ini (lo crea si no existe) y elige destino
  opr_telemetry.py              arma el JSON desde ac.getCarState + opr_mmap
  opr_mmap.py                   heading/pitch/roll desde acpmf_physics
  opr_sender.py                 hilo worker + slot + POST HTTP
  manifest.ini                  nombre y versión
  config.ini.example            plantilla (el config.ini real está gitignoreado)
dev/build_zip.py                arma el paquete para Content Manager
dev/probe.py                    manda telemetría sintética sin abrir AC
dev/test_backends.py            prueba la elección de destino sin AC
```

Los módulos llevan el prefijo `opr_` a propósito: todas las apps de AC comparten
`sys.modules` y un `config.py` "pelado" chocaría con el de otra app.

## Desarrollo

```
python dev/test_backends.py                                   # lógica de destinos, sin AC
python dev/probe.py --url http://localhost:5000 --token TOKEN --hz 8   # telemetría sintética
```

Con AC: pon `debug = 1` en `config.ini` y mira `.../assettocorsa/logs/py_log.txt`.

Para publicar una versión nueva, sube `VERSION` en `manifest.ini` y vuelve a correr
`python dev/build_zip.py`.

### Gotchas del entorno AC

- **Python 3.3.5** embebido: nada de f-strings ni `typing`; usa `.format()`.
- **HTTPS**: el Python de AC no verifica certificados (OpenSSL viejo). Funciona contra
  endpoints TLS 1.2; si un túnel falla desde el juego, prueba `http://` o LAN directa.
- La rotación no está en el módulo `ac`: sale de `acpmf_physics` (offset 208). Fuera de
  Windows/AC se envía en ceros.

## Licencia

[MIT](LICENSE)
