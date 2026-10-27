# watchface.py — renders a face dict (the SAME schema the WristForge
# simulator exports) into a framebuf. This is the device twin of renderFace()
# in the browser: same fields, same layout, just framebuf primitives instead
# of canvas. Drop a new .face.json on the board and it draws with no code change.
import math
from array import array
from gc9a01 import hex_rgb

TAU = math.pi * 2
C = 120                      # screen centre (240/240 panel)
WD = ('SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT')


# ---------- small framebuf helpers ----------
def _rot(cx, cy, lx, ly, a):
    ca, sa = math.cos(a), math.sin(a)
    return (cx + lx * ca - ly * sa, cy + lx * sa + ly * ca)


def _poly(fb, pts, color, fill=True):
    flat = array('h')
    for x, y in pts:
        flat.append(int(x)); flat.append(int(y))
    fb.poly(0, 0, flat, color, fill)


def _thick_line(fb, x1, y1, x2, y2, w, color):
    if w <= 1:
        fb.line(int(x1), int(y1), int(x2), int(y2), color)
        return
    dx, dy = x2 - x1, y2 - y1
    d = math.hypot(dx, dy) or 1
    px, py = -dy / d * w / 2, dx / d * w / 2     # perpendicular offset
    _poly(fb, ((x1 + px, y1 + py), (x2 + px, y2 + py),
               (x2 - px, y2 - py), (x1 - px, y1 - py)), color, True)


def _fill_circle(fb, cx, cy, r, color):
    fb.ellipse(int(cx), int(cy), int(r), int(r), color, True)


# 8x8 built-in font scaled up into blocky pixels (no external font needed)
def text_w(s, scale):
    return len(s) * 8 * scale


def _text(fb, s, x, y, color, scale=1):
    if scale <= 1:
        fb.text(s, int(x), int(y), color)
        return
    import framebuf
    w = len(s) * 8
    buf = bytearray(((w + 7) // 8) * 8)        # MONO_HLSB: ceil(w/8) bytes per row, 8 rows
    tmp = framebuf.FrameBuffer(buf, w, 8, framebuf.MONO_HLSB)
    tmp.fill(0)
    tmp.text(s, 0, 0, 1)
    x = int(x); y = int(y)
    for py in range(8):
        for px in range(w):
            if tmp.pixel(px, py):
                fb.fill_rect(x + px * scale, y + py * scale, scale, scale, color)


def _text_centered(fb, s, cx, cy, color, scale=1):
    _text(fb, s, cx - text_w(s, scale) / 2, cy - 4 * scale, color, scale)


def _font_scale(size):
    return max(1, round(size / 8))


# ---------- seven-segment (ports 1:1 from the simulator) ----------
def _seg_h(fb, cx, cy, L, t, color):
    _poly(fb, ((cx - L / 2, cy), (cx - L / 2 + t * 0.7, cy - t / 2),
               (cx + L / 2 - t * 0.7, cy - t / 2), (cx + L / 2, cy),
               (cx + L / 2 - t * 0.7, cy + t / 2),
               (cx - L / 2 + t * 0.7, cy + t / 2)), color, True)


def _seg_v(fb, cx, cy, L, t, color):
    _poly(fb, ((cx, cy - L / 2), (cx + t / 2, cy - L / 2 + t * 0.7),
               (cx + t / 2, cy + L / 2 - t * 0.7), (cx, cy + L / 2),
               (cx - t / 2, cy + L / 2 - t * 0.7),
               (cx - t / 2, cy - L / 2 + t * 0.7)), color, True)


_SEGS = {'0': 'abcdef', '1': 'bc', '2': 'abged', '3': 'abgcd', '4': 'fgbc',
         '5': 'afgcd', '6': 'afgedc', '7': 'abc', '8': 'abcdefg', '9': 'abcfgd'}


def _digit(fb, x, y, w, h, t, segs, color):
    L = w - t * 1.2
    Lv = h / 2 - t * 1.5
    if 'a' in segs: _seg_h(fb, x + w / 2, y + t / 2, L, t, color)
    if 'g' in segs: _seg_h(fb, x + w / 2, y + h / 2, L, t, color)
    if 'd' in segs: _seg_h(fb, x + w / 2, y + h - t / 2, L, t, color)
    if 'f' in segs: _seg_v(fb, x + t / 2, y + h * 0.27, Lv, t, color)
    if 'b' in segs: _seg_v(fb, x + w - t / 2, y + h * 0.27, Lv, t, color)
    if 'e' in segs: _seg_v(fb, x + t / 2, y + h * 0.73, Lv, t, color)
    if 'c' in segs: _seg_v(fb, x + w - t / 2, y + h * 0.73, Lv, t, color)


def _seven(fb, cx, cy, h, s, color):
    t = h * 0.11; w = h * 0.55; sp = w * 0.28; colon = w * 0.45
    total = sum(colon if ch == ':' else w for ch in s) + sp * (len(s) - 1)
    x = cx - total / 2; y = cy - h / 2
    for ch in s:
        if ch == ':':
            fb.fill_rect(int(x + colon / 2 - t / 2), int(y + h * 0.30 - t / 2),
                         int(t), int(t), color)
            fb.fill_rect(int(x + colon / 2 - t / 2), int(y + h * 0.70 - t / 2),
                         int(t), int(t), color)
            x += colon + sp
        else:
            _digit(fb, x, y, w, h, t, _SEGS.get(ch, ''), color)
            x += w + sp
    return total


# ---------- hands ----------
def _hand(fb, angle, s):
    color = hex_rgb(s['color'])
    ln = s['len']; w = s['w']; tail = s.get('tail', 0); style = s['style']
    if style == 'taper':
        pts = ((-w / 2, tail), (-w * 0.18, -ln), (w * 0.18, -ln), (w / 2, tail))
    else:  # baton / rect -> filled quad
        pts = ((-w / 2, -ln), (w / 2, -ln), (w / 2, tail), (-w / 2, tail))
    _poly(fb, [_rot(C, C, px, py, angle) for px, py in pts], color, True)
    if style == 'baton':                       # round cap at the tip
        tx, ty = _rot(C, C, 0, -ln, angle)
        _fill_circle(fb, tx, ty, w / 2, color)


# ---------- complications ----------
def _battery_arc(fb, x, y, c, st):
    size = c['size']; r = size * 1.3
    a0 = math.pi * 0.75; sweep = math.pi * 1.5
    pct = st['battery'] / 100.0
    track = hex_rgb(c['color'])
    if st['charging']:
        fillc = hex_rgb('#4fd07a')
    elif pct < 0.2:
        fillc = hex_rgb('#e34f4f')
    elif pct < 0.4:
        fillc = hex_rgb('#e3a14f')
    else:
        fillc = hex_rgb(c['accent'])
    steps = 40
    for i in range(steps):
        a = a0 + sweep * i / (steps - 1)
        px, py = x + math.cos(a) * r, y + math.sin(a) * r
        _fill_circle(fb, px, py, 1, track)
    n = int(steps * pct)
    for i in range(n):
        a = a0 + sweep * i / (steps - 1)
        px, py = x + math.cos(a) * r, y + math.sin(a) * r
        _fill_circle(fb, px, py, max(1, size * 0.17), fillc)
    _text_centered(fb, str(int(st['battery'])), x, y, track, _font_scale(size))


def _complication(fb, kind, x, y, c, st):
    color = hex_rgb(c['color']); size = c['size']
    if kind == 'date':
        _text_centered(fb, st['weekday'], x, y - size, color, _font_scale(size * 0.9))
        _text_centered(fb, str(st['day']), x, y + size * 0.5, color, _font_scale(size * 1.6))
    elif kind == 'weekday':
        _text_centered(fb, st['weekday'], x, y, color, _font_scale(size))
    elif kind == 'battery':
        _battery_arc(fb, x, y, c, st)
    elif kind == 'steps':
        _text_centered(fb, str(st['steps']), x, y - size * 0.3, color, _font_scale(size * 1.1))
        _text_centered(fb, 'STEPS', x, y + size, color, 1)


_SLOT_POS = {'top': (0, -1), 'right': (1, 0), 'bottom': (0, 1), 'left': (-1, 0)}


# ---------- background ----------
def _background(fb, bg):
    typ = bg['type']
    if typ == 'solid':
        fb.fill(hex_rgb(bg['c1'])); return
    c1 = bg['c1'].lstrip('#'); c2 = bg['c2'].lstrip('#')
    r1, g1, b1 = int(c1[0:2], 16), int(c1[2:4], 16), int(c1[4:6], 16)
    r2, g2, b2 = int(c2[0:2], 16), int(c2[2:4], 16), int(c2[4:6], 16)
    if typ == 'radial':
        steps = 24
        for i in range(steps):
            k = i / (steps - 1)
            col = _mix(r1, g1, b1, r2, g2, b2, k)
            rr = 124 * (1 - i / steps)
            fb.ellipse(C, C, int(rr), int(rr), col, True)
    else:  # linear bands (top -> bottom, good enough for the round panel)
        bands = 30
        bh = 240 / bands
        for i in range(bands):
            k = i / (bands - 1)
            fb.fill_rect(0, int(i * bh), 240, int(bh + 1),
                         _mix(r1, g1, b1, r2, g2, b2, k))


def _mix(r1, g1, b1, r2, g2, b2, k):
    from gc9a01 import rgb
    return rgb(int(r1 + (r2 - r1) * k), int(g1 + (g2 - g1) * k), int(b1 + (b2 - b1) * k))


# ============================================================
# main entry: draw one full frame
# ============================================================
def render(fb, f, st):
    _background(fb, f['bg'])

    ring = f.get('ring', {})
    if ring.get('show'):
        col = hex_rgb(ring['color']); r = ring['r']
        for dr in range(ring['w']):          # emulate stroke width
            fb.ellipse(C, C, r - dr, r - dr, col, False)

    t = f.get('ticks', {})
    if t.get('show'):
        r1 = 120 - t['inset']
        minor = t.get('minorCount', 0)
        major = t.get('majorCount', 0)
        if minor:
            mc = hex_rgb(t['minorColor'])
            ratio = minor // major if major else 0
            for i in range(minor):
                if ratio and i % ratio == 0:
                    continue
                a = i / minor * TAU - math.pi / 2
                ux, uy = math.cos(a), math.sin(a)
                fb.line(int(C + ux * (r1 - t['minorLen'])), int(C + uy * (r1 - t['minorLen'])),
                        int(C + ux * r1), int(C + uy * r1), mc)
        if major:
            mc = hex_rgb(t['majorColor']); shape = t.get('majorShape', 'line')
            mlen = t['majorLen']; mw = t['majorW']
            for i in range(major):
                a = i / major * TAU - math.pi / 2
                ux, uy = math.cos(a), math.sin(a)
                if shape == 'dot':
                    _fill_circle(fb, C + ux * (r1 - mlen / 2), C + uy * (r1 - mlen / 2),
                                 max(1, mlen / 2), mc)
                elif shape == 'wedge':
                    px, py = -uy, ux
                    _poly(fb, ((C + ux * r1 + px * mw, C + uy * r1 + py * mw),
                               (C + ux * r1 - px * mw, C + uy * r1 - py * mw),
                               (C + ux * (r1 - mlen), C + uy * (r1 - mlen))), mc, True)
                else:
                    _thick_line(fb, C + ux * (r1 - mlen), C + uy * (r1 - mlen),
                                C + ux * r1, C + uy * r1, mw, mc)

    nm = f.get('numerals', {})
    if nm.get('mode', 'none') != 'none':
        nums = (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12) if nm['mode'] == 'all' else (12, 3, 6, 9)
        col = hex_rgb(nm['color']); sc = _font_scale(nm['size']); rr = nm['r']
        for n in nums:
            a = n / 12 * TAU - math.pi / 2
            _text_centered(fb, str(n), C + math.cos(a) * rr, C + math.sin(a) * rr, col, sc)

    comp = f.get('comp', {})
    for slot, (sx, sy) in _SLOT_POS.items():
        kind = f.get('slots', {}).get(slot, 'none')
        if kind and kind != 'none':
            _complication(fb, kind, C + sx * comp['dist'], C + sy * comp['dist'], comp, st)

    dig = f.get('digital', {})
    if dig.get('show'):
        h = st['h']
        if not dig.get('fmt24', True):
            h = h % 12 or 12
        s = '{:02d}:{:02d}'.format(h if dig.get('fmt24', True) else h, st['m'])
        if dig.get('showSeconds') and not st['aod']:
            s += ':{:02d}'.format(st['s'])
        col = hex_rgb(dig['color']); cx = C + dig['x']; cy = C + dig['y']
        if dig.get('style') == 'seven':
            _seven(fb, cx, cy, dig['size'], s, col)
        else:
            _text_centered(fb, s, cx, cy, col, _font_scale(dig['size']))

    hd = f.get('hands', {})
    if hd.get('show'):
        aH = ((st['h'] % 12) + st['m'] / 60 + st['s'] / 3600) / 12 * TAU
        aM = (st['m'] + st['s'] / 60) / 60 * TAU
        aS = st['s'] / 60 * TAU
        _hand(fb, aH, hd['hour'])
        _hand(fb, aM, hd['minute'])
        sec = hd.get('second', {})
        if sec.get('show') and not st['aod']:
            _hand(fb, aS, sec)
        hub = hd.get('hub', {})
        _fill_circle(fb, C, C, hub['r'], hex_rgb(hub['color']))
        if hub.get('ring'):
            fb.ellipse(C, C, int(hub['r'] + 2), int(hub['r'] + 2), hex_rgb(hub['ring']), False)
