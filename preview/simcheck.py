# preview/simcheck.py — host-side preview of the DEVICE renderer.
# Mocks MicroPython's `framebuf` and `machine` with PIL so device/watchface.py
# runs unmodified on a PC and writes PNGs here. Nothing here is flashed; it's a
# way to eyeball the device code without hardware.  Run:  python preview/simcheck.py
#
# NOTE: numerals / complication text render as blocks here because PIL's font
# doesn't fit MicroPython's 8px grid. On the board these use the built-in 8x8
# font and look like crisp blocky digits. Geometry/colors are faithful.
import sys, os, types
from PIL import Image, ImageDraw, ImageFont

DEVICE = os.path.join(os.path.dirname(__file__), '..', 'device')
sys.path.insert(0, DEVICE)
OUT = os.path.dirname(__file__)
FONT = ImageFont.load_default()


def decode(c):                                   # byte-swapped RGB565 -> (r,g,b)
    o = ((c & 0xFF) << 8) | (c >> 8)
    return (((o >> 11) & 0x1F) << 3, ((o >> 5) & 0x3F) << 2, (o & 0x1F) << 3)


class FrameBuffer:
    def __init__(self, buf, w, h, fmt):
        self.w, self.h = w, h
        self.mono = (fmt == MONO_HLSB)
        self.img = Image.new('1' if self.mono else 'RGB', (w, h), 0)
        self.d = ImageDraw.Draw(self.img)
    def _c(self, c): return 1 if self.mono else decode(c)
    def fill(self, c): self.d.rectangle([0, 0, self.w, self.h], fill=self._c(c))
    def pixel(self, x, y, c=None):
        if c is None:
            return self.img.getpixel((x, y)) if 0 <= x < self.w and 0 <= y < self.h else 0
        self.img.putpixel((x, y), self._c(c))
    def hline(self, x, y, w, c): self.d.line([x, y, x + w, y], fill=self._c(c))
    def vline(self, x, y, h, c): self.d.line([x, y, x, y + h], fill=self._c(c))
    def line(self, x1, y1, x2, y2, c): self.d.line([x1, y1, x2, y2], fill=self._c(c))
    def rect(self, x, y, w, h, c, f=False):
        self.d.rectangle([x, y, x + w - 1, y + h - 1],
                         fill=self._c(c) if f else None, outline=None if f else self._c(c))
    def fill_rect(self, x, y, w, h, c): self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=self._c(c))
    def ellipse(self, x, y, xr, yr, c, f=False, m=0xF):
        bb = [x - xr, y - yr, x + xr, y + yr]
        self.d.ellipse(bb, fill=self._c(c)) if f else self.d.ellipse(bb, outline=self._c(c))
    def poly(self, x, y, coords, c, f=False):
        pts = [(x + coords[i], y + coords[i + 1]) for i in range(0, len(coords), 2)]
        self.d.polygon(pts, fill=self._c(c)) if f else self.d.polygon(pts, outline=self._c(c))
    def text(self, s, x, y, c): self.d.text((x, y - 1), s, fill=self._c(c), font=FONT)


RGB565, MONO_HLSB = 1, 3
_fb = types.ModuleType('framebuf')
_fb.FrameBuffer, _fb.RGB565, _fb.MONO_HLSB = FrameBuffer, RGB565, MONO_HLSB
sys.modules['framebuf'] = _fb
_m = types.ModuleType('machine')
for n in ('Pin', 'SPI', 'PWM', 'I2C', 'RTC', 'ADC'):
    setattr(_m, n, type(n, (), {'__init__': lambda self, *a, **k: None}))
sys.modules['machine'] = _m

import json, watchface

st = {'h': 10, 'm': 8, 's': 37, 'day': 13, 'weekday': 'FRI',
      'battery': 78, 'charging': False, 'steps': 6210, 'aod': False}

for fn in ('classic.json', 'minimal.json'):
    cv = FrameBuffer(None, 240, 240, RGB565)
    with open(os.path.join(DEVICE, fn)) as f:
        watchface.render(cv, json.load(f), st)
    mask = Image.new('L', (240, 240), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, 239, 239], fill=255)
    out = Image.new('RGB', (240, 240), (0, 0, 0))
    out.paste(cv.img, (0, 0), mask)
    path = os.path.join(OUT, fn.replace('.json', '.png'))
    out.save(path)
    print('wrote', path)
