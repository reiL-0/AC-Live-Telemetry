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
_OFF_TYRE_CORE = 152     # tyreCoreTemperature[4]: FL, FR, RL, RR (°C)

_TAG_STATIC = "Local\\acpmf_static"
_MAP_SIZE_STATIC = 800   # sobra para llegar al offset 412..416
_OFF_MAX_RPM = 412

_mm = None
_mm_static = None


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
    """(litros, temp. nucleo x4 °C, presion x4 psi, (G lat, G long)), o None sin memoria compartida.
    Ruedas en orden FL, FR, RL, RR."""
    _open()
    if _mm is None:
        return None
    try:
        acc = struct.unpack_from("<fff", _mm, _OFF_ACC_G)
        return (struct.unpack_from("<f", _mm, _OFF_FUEL)[0],
                struct.unpack_from("<ffff", _mm, _OFF_TYRE_CORE),
                struct.unpack_from("<ffff", _mm, _OFF_PRESSURE),
                (acc[0], acc[2]))
    except (OSError, ValueError, struct.error):
        close()
        return None


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
    global _mm, _mm_static
    for mm in (_mm, _mm_static):
        try:
            if mm is not None:
                mm.close()
        except Exception:
            pass
    _mm = _mm_static = None
