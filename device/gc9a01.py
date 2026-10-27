# gc9a01.py — GC9A01 round LCD driver for the Waveshare RP2040-LCD-1.28
# Pure MicroPython. Subclasses framebuf.FrameBuffer so you draw with the
# standard framebuf API (fill, line, ellipse, poly, text...) into a full
# 240x240 RGB565 buffer, then call show() to blit it to the panel.
#
# Board pin map (fixed on the RP2040-LCD-1.28):
#   DC=GP8  CS=GP9  CLK=GP10  MOSI/DIN=GP11  RST=GP12  Backlight=GP25
from machine import Pin, SPI, PWM
import framebuf
import time

# Canonical GC9A01 power-on sequence: (cmd, (data bytes...), delay_ms)
# This is the standard init shared by the Waveshare / russhughes / LVGL drivers.
_INIT = (
    (0xEF, (), 0), (0xEB, (0x14,), 0),
    (0xFE, (), 0), (0xEF, (), 0), (0xEB, (0x14,), 0),
    (0x84, (0x40,), 0), (0x85, (0xFF,), 0), (0x86, (0xFF,), 0), (0x87, (0xFF,), 0),
    (0x88, (0x0A,), 0), (0x89, (0x21,), 0), (0x8A, (0x00,), 0), (0x8B, (0x80,), 0),
    (0x8C, (0x01,), 0), (0x8D, (0x01,), 0), (0x8E, (0xFF,), 0), (0x8F, (0xFF,), 0),
    (0xB6, (0x00, 0x20), 0),
    (0x36, (0x08,), 0),   # MADCTL: BGR panel. If red/blue look swapped, try 0x00.
    (0x3A, (0x05,), 0),   # COLMOD: 16 bit/pixel (RGB565)
    (0x90, (0x08, 0x08, 0x08, 0x08), 0),
    (0xBD, (0x06,), 0), (0xBC, (0x00,), 0),
    (0xFF, (0x60, 0x01, 0x04), 0),
    (0xC3, (0x13,), 0), (0xC4, (0x13,), 0), (0xC9, (0x22,), 0), (0xBE, (0x11,), 0),
    (0xE1, (0x10, 0x0E), 0), (0xDF, (0x21, 0x0C, 0x02), 0),
    (0xF0, (0x45, 0x09, 0x08, 0x08, 0x26, 0x2A), 0),
    (0xF1, (0x43, 0x70, 0x72, 0x36, 0x37, 0x6F), 0),
    (0xF2, (0x45, 0x09, 0x08, 0x08, 0x26, 0x2A), 0),
    (0xF3, (0x43, 0x70, 0x72, 0x36, 0x37, 0x6F), 0),
    (0xED, (0x1B, 0x0B), 0), (0xAE, (0x77,), 0), (0xCD, (0x63,), 0),
    (0x70, (0x07, 0x07, 0x04, 0x0E, 0x0F, 0x09, 0x07, 0x08, 0x03), 0),
    (0xE8, (0x34,), 0),
    (0x62, (0x18, 0x0D, 0x71, 0xED, 0x70, 0x70, 0x18, 0x0F, 0x71, 0xEF, 0x70, 0x70), 0),
    (0x63, (0x18, 0x11, 0x71, 0xF1, 0x70, 0x70, 0x18, 0x13, 0x71, 0xF3, 0x70, 0x70), 0),
    (0x64, (0x28, 0x29, 0xF1, 0x01, 0xF1, 0x00, 0x07), 0),
    (0x66, (0x3C, 0x00, 0xCD, 0x67, 0x45, 0x45, 0x10, 0x00, 0x00, 0x00), 0),
    (0x67, (0x00, 0x3C, 0x00, 0x00, 0x00, 0x01, 0x54, 0x10, 0x32, 0x98), 0),
    (0x74, (0x10, 0x85, 0x80, 0x00, 0x00, 0x4E, 0x00), 0),
    (0x98, (0x3E, 0x07), 0),
    (0x35, (), 0), (0x21, (), 0),   # tearing effect on, display inversion on
    (0x11, (), 120),                # sleep out
    (0x29, (), 20),                 # display on
)


class GC9A01(framebuf.FrameBuffer):
    def __init__(self, spi_baud=60_000_000):
        self.width = 240
        self.height = 240
        self.cs = Pin(9, Pin.OUT, value=1)
        self.dc = Pin(8, Pin.OUT, value=0)
        self.rst = Pin(12, Pin.OUT, value=1)
        self.bl = PWM(Pin(25))
        self.bl.freq(2000)
        self.spi = SPI(1, spi_baud, polarity=0, phase=0,
                       sck=Pin(10), mosi=Pin(11), miso=None)
        # 240*240*2 = 115200 bytes. Fits in the RP2040's 264 KB SRAM.
        self.buffer = bytearray(self.width * self.height * 2)
        super().__init__(self.buffer, self.width, self.height, framebuf.RGB565)
        self._reset()
        self._init()
        self.backlight(100)

    # --- low level ---
    def _cmd(self, c):
        self.dc(0); self.cs(0); self.spi.write(bytes((c,))); self.cs(1)

    def _data(self, d):
        self.dc(1); self.cs(0); self.spi.write(bytes(d)); self.cs(1)

    def _reset(self):
        self.rst(1); time.sleep_ms(50)
        self.rst(0); time.sleep_ms(50)
        self.rst(1); time.sleep_ms(50)

    def _init(self):
        for cmd, data, delay in _INIT:
            self._cmd(cmd)
            if data:
                self._data(data)
            if delay:
                time.sleep_ms(delay)

    # --- public ---
    def backlight(self, pct):
        # pct 0..100 -> 16-bit PWM duty
        self.bl.duty_u16(int(max(0, min(100, pct)) * 655.35))

    def show(self):
        # window = full panel (0..239, 0..239), then stream the framebuffer
        self._cmd(0x2A); self._data((0x00, 0x00, 0x00, 0xEF))
        self._cmd(0x2B); self._data((0x00, 0x00, 0x00, 0xEF))
        self._cmd(0x2C)
        self.dc(1); self.cs(0); self.spi.write(self.buffer); self.cs(1)


def rgb(r, g, b):
    """#rrggbb components -> the byte-swapped RGB565 value framebuf needs so
    colors come out correct on this panel."""
    c = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
    return ((c << 8) | (c >> 8)) & 0xFFFF


def hex_rgb(h):
    """'#1b1e26' (or '1b1e26') -> packed RGB565 for this panel."""
    h = h.lstrip('#')
    return rgb(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
