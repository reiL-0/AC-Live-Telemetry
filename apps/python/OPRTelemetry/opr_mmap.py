"""Lectura de la orientacion del auto desde la memoria compartida de AC.

El modulo `ac` expone pedales, marcha, rpm, velocidad y posicion, pero NO la
rotacion del auto. Eso vive en el bloque `acpmf_physics` (SPageFilePhysics).
Aca leemos solo los 3 floats que necesitamos: heading, pitch, roll (radianes).

Offsets de SPageFilePhysics (todos los campos son 4 bytes, sin padding):
    0  int   packetId
    4  float gas
    8  float brake
    12 float fuel
    16 int   gear
    20 int   rpms
    24 float steerAngle
    28 float speedKmh
    32 float velocity[3]
    44 float accG[3]
    56 float wheelSlip[4]
    72 float wheelLoad[4]
    88 float wheelsPressure[4]
    104 float wheelAngularSpeed[4]
    120 float tyreWear[4]
    136 float tyreDirtyLevel[4]
    152 float tyreCoreTemperature[4]
    168 float camberRAD[4]
    184 float suspensionTravel[4]
    200 float drs
    204 float tc
    208 float heading   <-- aca
    212 float pitch
    216 float roll
    348 float brakeTemp[4]
    368 float tyreTempI[4] / 384 tyreTempM[4] / 400 tyreTempO[4]

Tambien leemos `acpmf_static` (SPageFileStatic) para el limite de RPM del auto
actual - no todos los autos tienen el mismo. Ahi los campos son mixtos
(wchar_t de 2 bytes + int/float de 4), asi que hay padding antes de cada
int/float para alinearlo a 4 bytes. Offsets hasta el campo que nos interesa:
    0   wchar_t smVersion[15]        (30 bytes)
    30  wchar_t acVersion[15]        (30 bytes)
    60  int     numberOfSessions
    64  int     numCars
    68  wchar_t carModel[33]         (66 bytes)
    134 wchar_t track[33]            (66 bytes)
    200 wchar_t playerName[33]       (66 bytes)
    266 wchar_t playerSurname[33]    (66 bytes)
    332 wchar_t playerNick[33]       (66 bytes)
    398 (+2 padding)
    400 int     sectorCount
    404 float   maxTorque
    408 float   maxPower
    412 int     maxRpm   <-- aca
"""
import struct

try:
    import mmap
except ImportError:  # pragma: no cover
    mmap = None

_TAG = "Local\\acpmf_physics"
_MAP_SIZE = 512          # sobra para llegar al offset 208..220
_OFF_HEADING = 208
_OFF_FUEL = 12
_OFF_ACC_G = 44          # accG[3]: x = lateral, y = vertical, z = longitudinal (G)
_OFF_PRESSURE = 88       # wheelsPressure[4]: FL, FR, RL, RR (psi)
_OFF_TYRE_WEAR = 120     # tyreWear[4]: FL, FR, RL, RR (escala de AC, ~100 = nuevo)
_OFF_SUSP = 184          # suspensionTravel[4]: FL, FR, RL, RR (metros)
_OFF_TYRE_CORE = 152     # tyreCoreTemperature[4]: FL, FR, RL, RR (°C)

_OFF_BRAKE_TEMP = 348    # brakeTemp[4] (°C)
_OFF_TYRE_I, _OFF_TYRE_M, _OFF_TYRE_O = 368, 384, 400   # tyreTempI/M/O[4]: cara interna / media / externa (°C)

_TAG_GFX = "Local\\acpmf_graphics"
_MAP_SIZE_GFX = 512
_OFF_COMPOUND = 176      # wchar_t tyreCompound[33]

_TAG_STATIC = "Local\\acpmf_static"
_MAP_SIZE_STATIC = 800   # sobra para llegar al offset 412..416
_OFF_MAX_RPM = 412

_mm = None
_mm_static = None
_mm_gfx = None


def _open():
    global _mm
    if _mm is not None or mmap is None:
        return
    try:
        _mm = mmap.mmap(-1, _MAP_SIZE, _TAG, mmap.ACCESS_READ)
    except (OSError, ValueError, TypeError):
        _mm = None  # fuera de Windows / AC no corriendo (el 3er arg es Windows-only)


def _open_static():
    global _mm_static
    if _mm_static is not None or mmap is None:
        return
    try:
        _mm_static = mmap.mmap(-1, _MAP_SIZE_STATIC, _TAG_STATIC, mmap.ACCESS_READ)
    except (OSError, ValueError, TypeError):
        _mm_static = None


def heading_pitch_roll():
    """(heading, pitch, roll) en radianes, o None si la memoria compartida
    no esta disponible."""
    _open()
    if _mm is None:
        return None
    try:
        return struct.unpack_from("<fff", _mm, _OFF_HEADING)
    except (OSError, ValueError, struct.error):
        close()
        return None


def extras():
    """Dict con lo que la app manda ademas de lo basico, o None sin memoria compartida.
    Ruedas en orden FL, FR, RL, RR; core/I/M/O en °C, presion en psi, suspension en m."""
    _open()
    if _mm is None:
        return None
    try:
        wheels = lambda off: struct.unpack_from("<ffff", _mm, off)
        acc = struct.unpack_from("<fff", _mm, _OFF_ACC_G)
        return {"fuel": struct.unpack_from("<f", _mm, _OFF_FUEL)[0], "acc": (acc[0], acc[2]),
                "tyre": wheels(_OFF_TYRE_CORE), "press": wheels(_OFF_PRESSURE), "wear": wheels(_OFF_TYRE_WEAR),
                "susp": wheels(_OFF_SUSP), "brake": wheels(_OFF_BRAKE_TEMP),
                "tyreI": wheels(_OFF_TYRE_I), "tyreM": wheels(_OFF_TYRE_M), "tyreO": wheels(_OFF_TYRE_O)}
    except (OSError, ValueError, struct.error):
        close()
        return None


def compound():
    """Nombre del compuesto montado (SPageFileGraphic.tyreCompound), o "" si no se pudo leer."""
    global _mm_gfx
    if _mm_gfx is None and mmap is not None:
        try:
            _mm_gfx = mmap.mmap(-1, _MAP_SIZE_GFX, _TAG_GFX, mmap.ACCESS_READ)
        except (OSError, ValueError, TypeError):
            return ""
    try:
        return _mm_gfx[_OFF_COMPOUND:_OFF_COMPOUND + 66].decode("utf-16-le").split("\x00")[0]
    except (OSError, ValueError, TypeError):
        close()
        return ""


def max_rpm():
    """Limite de RPM del auto actual (SPageFileStatic.maxRpm), o 0 si no hay
    memoria compartida (fuera de Windows/AC)."""
    _open_static()
    if _mm_static is None:
        return 0
    try:
        return struct.unpack_from("<i", _mm_static, _OFF_MAX_RPM)[0]
    except (OSError, ValueError, struct.error):
        close()
        return 0


def close():
    global _mm, _mm_static, _mm_gfx
    for mm in (_mm, _mm_static, _mm_gfx):
        try:
            if mm is not None:
                mm.close()
        except Exception:
            pass
    _mm = _mm_static = _mm_gfx = None
