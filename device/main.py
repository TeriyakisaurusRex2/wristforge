# main.py — WristForge watch runtime for the Waveshare RP2040-LCD-1.28
#
# Boots the display + IMU, keeps time on the RP2040 RTC, and renders a face
# once per second. Gestures mirror the simulator:
#   wrist raise / tap  -> wake screen to full brightness
#   double tap         -> switch to the next face (Classic <-> Minimal)
#   inactivity         -> dim screen (always-on style), hide the second hand
#
# Faces are plain JSON (same files the WristForge simulator exports), so to add
# a design you just copy another .json here and add it to FACES below.
import json
import math
from machine import RTC
from time import ticks_ms, ticks_diff, sleep_ms
from gc9a01 import GC9A01
import watchface

# ---------- config you can tweak ----------
FACES        = ('classic.json', 'minimal.json')
TIMEOUT_MS   = 10_000     # ms of stillness before the screen dims
DIM_BL       = 8          # backlight % while dimmed
FULL_BL      = 100        # backlight % while active
BATTERY_PCT  = 78         # placeholder; this board has no fuel gauge (see README)
STEPS        = 6210       # placeholder pedometer value

# Set the clock once here (the RP2040 RTC is unset on cold boot).
# (year, month, day, weekday, hour, minute, second, subsecond)
START_TIME   = (2026, 6, 13, 5, 10, 8, 30, 0)

# ---------- boot ----------
lcd = GC9A01()
rtc = RTC()
rtc.datetime(START_TIME)

try:
    from qmi8658 import QMI8658
    imu = QMI8658()
except Exception as e:
    imu = None
    print('IMU init failed:', e)

faces = []
for fn in FACES:
    with open(fn) as fp:
        faces.append(json.load(fp))
face_idx = 0


def weekday(y, m, d):
    # Sakamoto's algorithm -> 0=Sunday .. 6=Saturday
    t = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    if m < 3:
        y -= 1
    return (y + y // 4 - y // 100 + y // 400 + t[m - 1] + d) % 7


def make_state(aod):
    dt = rtc.datetime()
    return {
        'h': dt[4], 'm': dt[5], 's': dt[6],
        'day': dt[2], 'weekday': watchface.WD[weekday(dt[0], dt[1], dt[2])],
        'battery': BATTERY_PCT, 'charging': False, 'steps': STEPS,
        'aod': aod,
    }


def draw(aod):
    watchface.render(lcd, faces[face_idx], make_state(aod))
    lcd.show()


# ---------- gesture state ----------
prev_mag = 1.0
prev_az = 1.0
last_tap = 0
active = True
active_until = ticks_ms() + TIMEOUT_MS


def wake():
    global active, active_until
    if not active:
        active = True
        lcd.backlight(FULL_BL)
    active_until = ticks_ms() + TIMEOUT_MS


# ---------- main loop ----------
lcd.backlight(FULL_BL)
draw(aod=False)
last_sec = -1

while True:
    now = ticks_ms()

    # --- IMU gestures ---
    if imu:
        ax, ay, az = imu.accel()
        mag = math.sqrt(ax * ax + ay * ay + az * az)

        # tap: sharp magnitude spike from rest
        if mag > 2.1 and prev_mag < 1.5 and ticks_diff(now, last_tap) > 140:
            if ticks_diff(now, last_tap) < 400:      # second tap -> double tap
                face_idx = (face_idx + 1) % len(faces)
                wake(); last_sec = -1                 # force immediate redraw
                last_tap = 0
            else:                                    # first/single tap -> wake
                wake(); last_tap = now

        # wrist raise: screen tilts up toward your face (az climbs past level)
        if prev_az < 0.6 and az > 0.88:
            wake()

        prev_mag = mag
        prev_az = az

    # --- screen timeout ---
    if active and ticks_diff(now, active_until) > 0:
        active = False
        lcd.backlight(DIM_BL)
        last_sec = -1                                # redraw once in dim/AOD style

    # --- render once per second (or when forced) ---
    sec = rtc.datetime()[6]
    if sec != last_sec:
        last_sec = sec
        draw(aod=not active)

    sleep_ms(30)
