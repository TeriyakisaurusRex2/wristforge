# WristForge — getting faces onto the watch

Firmware for the **Waveshare RP2040-LCD-1.28** (GC9A01 240×240 round LCD +
QMI8658 IMU). It renders the *same `.face.json` files the WristForge simulator
exports*, so designing in the browser and running on the watch use one schema.

## The big idea: flash MicroPython **once**, then just copy files

You do **not** reflash to change a watch face. You flash MicroPython one time;
after that, changing the design is just copying a `.json` file onto the board and
soft-rebooting. That's the fast iteration loop.

```
device/
  gc9a01.py     display driver (SPI -> GC9A01)
  qmi8658.py    IMU driver (I2C -> accelerometer)
  watchface.py  the renderer (device twin of the simulator's renderFace)
  main.py       the watch runtime (clock, gestures, face switching)
  classic.json  } the two faces, identical schema to the sim's export
  minimal.json  }
```

---

## Step 1 — Flash MicroPython (one time)

1. Download the MicroPython UF2 for the Raspberry Pi Pico / RP2040:
   <https://micropython.org/download/RPI_PICO/> → grab the latest `.uf2`.
2. **Hold the BOOT button** on the board, plug the USB-C into your PC, then
   release BOOT. A USB drive called **RPI-RP2** appears.
3. Drag the `.uf2` onto **RPI-RP2**. It reboots and is now running MicroPython.

(The plain board has no buttons besides BOOT/RESET — BOOT is the small one used
for flashing.)

## Step 2 — Copy the watch files

**Easiest — Thonny (GUI):**
1. Install Thonny (<https://thonny.org>).
2. Bottom-right of Thonny → choose interpreter **"MicroPython (Raspberry Pi Pico)"**.
3. View → Files. In the bottom (device) pane, upload all 6 files from this
   `device/` folder to the board's root. Right-click a local file → *Upload to /*.
4. The board auto-runs `main.py` on boot — press the RESET button (or Ctrl-D in
   Thonny's REPL) and the watch face appears.

**Or — mpremote (command line, from this folder):**
```powershell
pip install mpremote
# find the COM port (Device Manager, or: mpremote connect list)
mpremote connect COM5 fs cp gc9a01.py qmi8658.py watchface.py main.py classic.json minimal.json :
mpremote connect COM5 reset
```

## Step 3 — Use it

- **Wrist raise** or **tap** → wake the screen to full brightness.
- **Double-tap** → switch face (Classic ⇄ Minimal).
- After 10 s of stillness the screen **dims** (always-on style) and hides the
  second hand to save power. Tweak `TIMEOUT_MS` / `DIM_BL` in `main.py`.

---

## Iterating designs (the loop you wanted)

1. Design a face in the WristForge simulator → **Export JSON**.
2. Copy that file into the board, e.g. `sunset.face.json`.
3. Add it to the `FACES` tuple at the top of `main.py`:
   ```python
   FACES = ('classic.json', 'minimal.json', 'sunset.face.json')
   ```
4. Soft-reboot (RESET / Ctrl-D). Cycle to it with double-tap. **No reflashing.**

## Setting the time

The RP2040 RTC is blank on cold boot, so `main.py` seeds it from `START_TIME`:
```python
START_TIME = (2026, 6, 13, 5, 10, 8, 30, 0)  # (Y, M, D, weekday, h, m, s, subsec)
```
Edit, re-copy `main.py`, reboot. (A future upgrade: set it from the PC clock over
USB serial, or add an RTC chip — noted in the project plan.)

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| **Red & blue swapped** | In `gc9a01.py` `_INIT`, change MADCTL `(0x36, (0x08,)…)` to `(0x36, (0x00,)…)`. |
| **Blank / white screen** | Open Thonny REPL, hit RESET, read the error. Usually a missing file or a typo in an edited `.json`. |
| **Garbled / flickering pixels** | Lower SPI speed: `GC9A01(spi_baud=30_000_000)` in `main.py`. |
| **"IMU init failed"** | Driver auto-tries 0x6B then 0x6A. If still failing, gestures are disabled but the clock runs fine. |
| **Wrong time** | Edit `START_TIME` and re-copy `main.py`. |

## Known placeholders (this board's limits)

- **Battery %** is a fixed `BATTERY_PCT` — the plain RP2040-LCD-1.28 has no fuel
  gauge / battery-sense ADC, so we can't read a real level yet. The `-B` (metal
  case) variant and add-on dividers can; we can wire that up later.
- **Steps** is a fixed `STEPS` value — a real pedometer off the IMU is a planned
  step.

## Previewing the device renderer on your PC

`../preview/simcheck.py` mocks `framebuf`/`machine` with PIL and runs
`watchface.py` unmodified, writing `preview/classic.png` + `preview/minimal.png`.
Run `python preview/simcheck.py` after editing the renderer to sanity-check it
without flashing. (Text renders as blocks in that preview only — a host-font
limitation; on the board it uses the real 8×8 font.)
