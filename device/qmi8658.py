# qmi8658.py — minimal driver for the QMI8658C 6-axis IMU on the
# RP2040-LCD-1.28. We only need the accelerometer (tilt + gestures), but
# the gyro is enabled too so you can extend later.
#
# Board pin map: I2C0  SDA=GP6  SCL=GP7.  Default 7-bit address 0x6B.
from machine import Pin, I2C
import time

_WHO_AM_I = 0x00
_CTRL1    = 0x02   # serial interface / auto-increment
_CTRL2    = 0x03   # accelerometer: ODR + full-scale
_CTRL3    = 0x04   # gyroscope: ODR + full-scale
_CTRL7    = 0x08   # enable accel/gyro
_AX_L     = 0x35   # accel X low byte; X,Y,Z are 6 consecutive bytes


class QMI8658:
    def __init__(self, addr=0x6B, sda=6, scl=7, freq=400_000):
        self.i2c = I2C(0, sda=Pin(sda), scl=Pin(scl), freq=freq)
        self.addr = addr
        who = self._r(_WHO_AM_I)
        if who != 0x05:
            # Try the alternate address before giving up
            self.addr = 0x6A
            who = self._r(_WHO_AM_I)
        self.ok = (who == 0x05)
        if self.ok:
            self._setup()

    def _r(self, reg):
        try:
            return self.i2c.readfrom_mem(self.addr, reg, 1)[0]
        except OSError:
            return 0xFF

    def _w(self, reg, val):
        self.i2c.writeto_mem(self.addr, reg, bytes((val,)))

    def _setup(self):
        self._w(_CTRL1, 0x60)   # auto-increment reads, address auto-step
        self._w(_CTRL2, 0x23)   # accel: +/-8g, ODR ~250 Hz
        self._w(_CTRL3, 0x53)   # gyro:  +/-512 dps, ODR ~250 Hz
        self._w(_CTRL7, 0x03)   # enable accelerometer + gyroscope
        time.sleep_ms(20)
        # +/-8g range -> 4096 LSB per g
        self._scale = 1.0 / 4096.0

    def accel(self):
        """Return (ax, ay, az) in g. Flat & screen-up reads ~ (0, 0, +1)."""
        if not self.ok:
            return (0.0, 0.0, 1.0)
        d = self.i2c.readfrom_mem(self.addr, _AX_L, 6)
        x = self._s16(d[0], d[1]) * self._scale
        y = self._s16(d[2], d[3]) * self._scale
        z = self._s16(d[4], d[5]) * self._scale
        return (x, y, z)

    @staticmethod
    def _s16(lo, hi):
        v = (hi << 8) | lo
        return v - 65536 if v & 0x8000 else v
