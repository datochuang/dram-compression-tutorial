"""Example contents for the address-space view.

Builds the bytes of each example symbol, lays the symbols out in two logical
segments, cuts the segments into 4096 B pages and compresses every page with
the same LZ4 block codec the simulator uses. Only the sizes go into the page.
"""
import math
import random
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'sim'))
from lz4sim.codec import compress  # noqa: E402

PAGE, CHUNK = 4096, 512


def fir_coeffs(n, rnd):
    out = bytearray()
    i = 0
    while len(out) < n:
        bank, k = divmod(i, 64)
        x = (k - 31.5) / (3.0 + bank % 5)
        v = int(30000 * (math.sin(x) / x) * (0.54 - 0.46 * math.cos(2 * math.pi * k / 63)))
        out += struct.pack('<h', v)
        i += 1
    return bytes(out[:n])


def machine_code(n, rnd):
    blob = Path('/bin/ls').read_bytes()
    start = blob.find(b'\x7f\x23\x03\xd5')          # first arm64 pacibsp, inside __text
    if start < 0:
        start = len(blob) // 3
    return blob[start:start + n]


def font_glyphs(n, rnd):
    out = bytearray()
    while len(out) < n:
        rows = [0] * 16
        for r in range(2, 14):
            if rnd.random() < 0.45:
                a = rnd.randrange(1, 4)
                rows[r] = ((1 << rnd.randrange(2, 6)) - 1) << a & 0xFF
        out += bytes(rows)
    return bytes(out[:n])


def rx_queue(n, rnd):
    out = bytearray()
    seq = 0x2A10
    while len(out) < n:
        hdr = struct.pack('<HHIHH', 0xA55A, seq & 0xFFFF, 0x0A000001 + rnd.randrange(4), 0x1F90, 96)
        body = bytes(rnd.randrange(256) for _ in range(40)) + bytes(56)
        out += hdr + body
        seq += 1
    return bytes(out[:n])


def log_ring(n, rnd):
    mods = ['net', 'ui', 'media', 'pm', 'fs']
    msgs = ['link up speed=%d', 'frame drop count=%d', 'buffer low level=%d', 'retry seq=%d', 'state change to %d',
            'timeout after %d ms', 'cache flush pages=%d']
    out = bytearray()
    t = 118204
    while len(out) < n:
        t += rnd.randrange(3, 900)
        out += ('[%8d.%03d] %-5s: %s\n' % (t // 1000, t % 1000, rnd.choice(mods), rnd.choice(msgs) % rnd.choice((2, 4, 8, 16, 32, 64, 128, 250, 500, 1000)))).encode()
    return bytes(out[:n])


def cal_table(n, rnd):
    out = bytearray()
    i = 0
    while len(out) < n:
        out += struct.pack('<f', round((1.0 + 0.002 * math.sin(i / 7.0) + rnd.gauss(0, 0.0004)) * 131072) / 131072)
        i += 1
    return bytes(out[:n])


def ui_state(n, rnd):
    out = bytearray()
    i = 0
    while len(out) < n:
        out += struct.pack('<HHHHIIQ', i, rnd.randrange(480), rnd.randrange(800), rnd.randrange(64), 0x00FFFFFF, 0, 0)
        out += bytes(8) if i % 3 else bytes(rnd.randrange(256) for _ in range(8))
        i += 1
    return bytes(out[:n])


SEGMENTS = [
    dict(id='ro', kind='ro', base=0x00120000, symbols=[
        ('fir_taps', 3891, fir_coeffs), ('parse_cfg', 4967, machine_code), ('glyphs', 3430, font_glyphs)]),
    dict(id='rw', kind='rw', base=0x00630000, symbols=[
        ('rx_queue', 5325, rx_queue), ('log_ring', 7373, log_ring), ('cal_tbl', 3277, cal_table), ('ui_state', 4505, ui_state)]),
]


def build():
    rnd = random.Random(20261111)
    segs, pages, symbols = [], [], []
    for s in SEGMENTS:
        blob, off = bytearray(), 0
        for name, size, gen in s['symbols']:
            blob += gen(size, rnd)
            symbols.append(dict(id=name, seg=s['id'], kind=s['kind'], addr=s['base'] + off, size=size))
            off += size
        assert len(blob) % PAGE == 0, (s['id'], len(blob))
        first = len(pages)
        for i in range(len(blob) // PAGE):
            raw = bytes(blob[i * PAGE:(i + 1) * PAGE])
            size = len(compress(raw))
            page = dict(vpn=(s['base'] >> 12) + i, seg=s['id'], kind=s['kind'], size=size)
            if s['kind'] == 'rw':
                w = bytearray(raw)
                for k in range(8):                      # what the page compresses to after a small write
                    w[1800 + 37 * k] ^= 0x5A
                page['size_w'] = len(compress(bytes(w)))
            pages.append(page)
        segs.append(dict(id=s['id'], kind=s['kind'], base=s['base'], first=first, pages=len(blob) // PAGE))
    return dict(page=PAGE, chunk=CHUNK, segments=segs, symbols=symbols, pages=pages, init=initial_layout(pages))


# The window of DRAM the page draws: 7 frames, 16 chunks of the RO part of the pool, 32 chunks of the RW part.
FRAMES = [4, 'o', None, 2, None, 3, None]           # page index, 'o' = a page that is not drawn, None = free
RO_POOL = 'oaabbbbbbbcccccc'                         # a, b, c = RO pages 0, 1, 2, laid down in order at build time
RW_POOL = 'oyy.xoozz.yyo..xxoy.zo..yoz..o..'         # x, y, z = RW pages 5, 6, 7; '.' = free
RW_ORDER = {5: [4, 15, 16], 6: [10, 11, 1, 2, 24, 18], 7: [7, 8, 20, 26]}    # stream order as the COT lists it
FREE_STACK = [31, 30, 28, 27, 23, 22, 19, 14, 13, 9, 3]                        # bottom to top
LRU = [2, 4, 3]                                      # oldest first


def initial_layout(pages):
    n_ro = len(RO_POOL)
    owners = [None] * (n_ro + len(RW_POOL))
    cot = {}
    for i, ch in enumerate(RO_POOL):
        if ch == 'o':
            owners[i] = 'o'
        else:
            p = 'abc'.index(ch)
            owners[i] = p
            cot.setdefault(p, []).append(i)
    letters = {'x': 5, 'y': 6, 'z': 7}
    for i, ch in enumerate(RW_POOL):
        owners[n_ro + i] = 'o' if ch == 'o' else letters.get(ch)
    for p, order in RW_ORDER.items():
        assert sorted(order) == [i for i, ch in enumerate(RW_POOL) if letters.get(ch) == p], p
        cot[p] = [n_ro + i for i in order]
    assert sorted(FREE_STACK) == [i for i, ch in enumerate(RW_POOL) if ch == '.']
    for p, chunks in cot.items():
        assert len(chunks) == math.ceil(pages[p]['size'] / CHUNK), (p, pages[p]['size'], len(chunks))
    for p in range(len(pages)):
        hot, cold = p in FRAMES, p in cot
        assert hot or cold, p
        assert pages[p]['kind'] == 'ro' or hot != cold, p
        assert pages[p]['kind'] != 'ro' or cold, p
    assert sorted(LRU) == sorted(f for f in FRAMES if isinstance(f, int))
    return dict(frames=FRAMES, chunks=owners, cot={str(k): v for k, v in cot.items()}, stack=[n_ro + i for i in FREE_STACK],
                lru=LRU, n_ro=n_ro, frame0=0x0A0, ro_chunk0=0x1C0, rw_chunk0=0xB40)


if __name__ == '__main__':
    d = build()
    for p in d['pages']:
        print(hex(p['vpn']), p['kind'], p['size'], math.ceil(p['size'] / CHUNK), p.get('size_w'))
    print(d['init'])
