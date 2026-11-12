"""What the encoder parameters cost and buy, measured on pages: stream length, chunks per page, estimated cycles.

Four sets of 4096 B pages, none of them the product:

    heap        pages of this Python process's own heap: objects, pointers, small strings.
                The nearest thing to RW data that can be had on this machine. Differs a little
                from run to run because the addresses inside the pointers do.
    text        Python source files of the standard library.
    binaries    pages cut out of executables on this machine: code and its constant data.
                The hardware never compresses such pages (the RO image is compressed by the
                build tool) but it decompresses them.
    synthetic   the pages of the host simulation's workload: random bytes mixed with one
                repeated 4 B pattern. Fine for the control procedure, weak as LZ4 input.

The numbers choose between variants. They do not promise a ratio for the product.
"""
import ctypes
import gc
import glob
import hashlib
import os
import random
from math import ceil

from . import lz4core as C

BINARIES = ('/bin/zsh', '/usr/bin/vim', '/usr/bin/ssh', '/bin/bash', '/usr/bin/tar')
CHUNK = 512
RW_LIMIT = 7 * CHUNK                          # an RW page over 7 chunks is stored raw in 8
SET_ZH = {'heap': 'heap（Python 程序自己的 heap）', 'text': 'text（Python 原始碼）',
          'binaries': 'binaries（本機的執行檔）', 'synthetic': 'synthetic（host simulation 的 workload）'}

# name, arguments of encode_variant. The first one is the encoder of the hardware.
VARIANTS = (
    ('**硬體採用：1024 格，XOR hash**', dict()),
    ('256 格', dict(hash_bits=8)),
    ('512 格', dict(hash_bits=9)),
    ('2048 格', dict(hash_bits=11)),
    ('4096 格', dict(hash_bits=12)),
    ('乘法 hash，1024 格', dict(hash_fn='mul')),
    ('乘法 hash，4096 格', dict(hash_fn='mul', hash_bits=12)),
    ('match 開頭後 2 個位置也放進 table', dict(post_insert=2)),
    ('match 結尾前 2 個位置也放進 table', dict(tail_insert=2)),
    ('match 往回延伸', dict(back=True)),
)


def hash_mul(v, bits):
    """The hash of the LZ4 reference code: top bits of the low 32 bits of v * 2654435761."""
    return ((v * 2654435761) & 0xFFFFFFFF) >> (32 - bits)


def encode_variant(page, hash_bits=C.HASH_BITS, hash_fn='xor', post_insert=0, tail_insert=0, back=False):
    """lz4core.encode with the knobs the study turns. With the defaults it gives the same bytes."""
    page = bytes(page)
    n = len(page)
    hf = C.hash4 if hash_fn == 'xor' else hash_mul
    out, seqs = bytearray(), []
    table = [None] * (1 << hash_bits)
    word = [int.from_bytes(page[i:i + 4], 'little') for i in range(max(0, n - 3))]
    last_start, match_end = n - C.MFLIMIT, n - C.LASTLITERALS
    anchor = ip = searched = 0
    while ip <= last_start:
        h = hf(word[ip], hash_bits)
        cand, table[h] = table[h], ip
        searched += 1
        if cand is None or word[cand] != word[ip]:
            ip += 1
            continue
        length = C.MINMATCH
        while ip + length < match_end and page[cand + length] == page[ip + length]:
            length += 1
        start = ip
        if back:                                 # take pending literals into the match
            while start > anchor and cand > 0 and page[start - 1] == page[cand - 1]:
                start, cand, length = start - 1, cand - 1, length + 1
        C.put_sequence(out, page[anchor:start], length, start - cand)
        seqs.append((start - anchor, length, start - cand))
        end = start + length
        for q in list(range(ip + 1, ip + 1 + post_insert)) + list(range(end - tail_insert, end)):
            if ip < q <= last_start:
                table[hf(word[q], hash_bits)] = q
        ip = anchor = end
    C.put_sequence(out, page[anchor:], 0, 0)
    seqs.append((n - anchor, 0, 0))
    return C.Encoded(bytes(out), seqs, searched)


# ---- the page sets
def synthetic_pages(n, seed=1):
    from lz4sim.config import SMALL
    from lz4sim.workload import Workload
    w = Workload(SMALL, seed=seed)
    return [w.ro_page() if i % 2 else w.rw_page() for i in range(n)]


def _cut(data, n, seed):
    pool = [data[o:o + C.PAGE] for o in range(0, len(data) - C.PAGE + 1, C.PAGE)]
    return random.Random(seed).sample(pool, min(n, len(pool)))


def binary_pages(n, seed=1, files=BINARIES):
    """Returns the pages and what they were cut from."""
    data, src = b'', []
    for path in files:
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                one = f.read()
            src.append({'file': path, 'bytes': len(one), 'sha256': hashlib.sha256(one).hexdigest()[:16]})
            data += one[:len(one) - len(one) % C.PAGE]
    return _cut(data, n, seed), src


def text_pages(n, seed=1):
    files = sorted(glob.glob(os.path.join(os.path.dirname(os.__file__), '*.py')))[:80]
    return _cut(b''.join(open(f, 'rb').read() for f in files), n, seed)


def heap_pages(n, seed=1):
    """4096 B pages around live objects of this process, read straight out of its memory."""
    import argparse, decimal, email, json, logging, unittest, xml.dom.minidom  # noqa: F401,E401  more objects to look at
    keep = [{'id': i, 'name': 'item%d' % i, 'v': [i * 0.5, i, str(i)], 't': (i, i + 1)} for i in range(20000)]
    pages = sorted({id(o) & ~(C.PAGE - 1) for o in gc.get_objects()})
    out = [ctypes.string_at(a, C.PAGE) for a in random.Random(seed).sample(pages, min(n, len(pages)))]
    del keep
    return out


def page_sets(n=300, seed=1):
    bins, src = binary_pages(n, seed)
    sets = {'heap': heap_pages(n, seed), 'text': text_pages(n, seed), 'binaries': bins, 'synthetic': synthetic_pages(n, seed)}
    return {k: v for k, v in sets.items() if v}, src


# ---- measurements
def chunks(length):
    """Chunks one stored page takes: 8 when the stream is not shorter than the page."""
    return ceil(length / CHUNK) if length < C.PAGE else C.PAGE // CHUNK


def _row(lengths):
    n = len(lengths)
    return {'pages': n, 'mean_len': sum(lengths) / n, 'mean_chunks': sum(chunks(x) for x in lengths) / n,
            'over_rw_limit_pct': 100 * sum(1 for x in lengths if x > RW_LIMIT) / n}


def _lib(mode):
    import lz4.block
    kw = dict(store_size=False)
    if mode == 'hc':
        kw.update(mode='high_compression', compression=9)
    return lambda p: len(lz4.block.compress(p, **kw))


def _pct(xs, q):
    ys = sorted(xs)
    return ys[min(len(ys) - 1, max(0, ceil(q / 100 * len(ys)) - 1))]


def _dist(xs):
    return {'mean': sum(xs) / len(xs), 'p50': _pct(xs, 50), 'p99': _pct(xs, 99), 'max': max(xs)}


# The bus the job estimate assumes: no wait states, these fixed latencies. Assumptions.
RD_LAT = 3            # cycles from a read address to its first data beat
WR_RESP = 2           # cycles from the last write beat to the write response
BURST = 64            # beats in a 512 B burst
FETCH = RD_LAT + 6 + 2                # descriptor, 6 beats, and the checks
POST = 1 + 2 + WR_RESP                # completion, 2 beats
LOAD = 8 * (RD_LAT + BURST)           # the frame into the page buffer
LAST_WRITE = 1 + BURST + WR_RESP      # the burst that is still on its way when the core is done
STORE = 8 * (1 + BURST) + WR_RESP     # the page buffer to the frame


def job_cycles(e):
    """Estimated cycles of a whole job for one page whose encoding is `e`, bus included."""
    raw = len(e.stream) >= C.PAGE
    comp = FETCH + LOAD + C.encode_cycles(e) + LAST_WRITE + POST + (STORE if raw else 0)
    supply = chunks(len(e.stream)) * (RD_LAT + BURST)                 # the chunks cannot arrive faster than this
    core = C.PAGE // C.BEAT if raw else C.decode_cycles(e.seqs)
    behind = FETCH + max(core + RD_LAT, supply) + LAST_WRITE + POST   # frame written while decoding
    after = FETCH + max(core + RD_LAT, supply) + STORE + POST         # frame written after the CRC check
    return comp, behind, after


def cycles(pages):
    enc, dec, seqs, comp, behind, after = [], [], [], [], [], []
    for p in pages:
        e = C.encode(p)
        enc.append(C.encode_cycles(e))
        dec.append(C.decode_cycles(e.seqs))
        seqs.append(len(e.seqs))
        a, b, c = job_cycles(e)
        comp.append(a)
        behind.append(b)
        after.append(c)
    return {'encode_core': _dist(enc), 'decode_core': _dist(dec), 'sequences': _dist(seqs),
            'compress_job': _dist(comp), 'decompress_job': _dist(behind), 'decompress_job_store_after': _dist(after)}


def run(n=300, seed=1):
    sets, src = page_sets(n, seed)
    out = {'sources': src, 'pages_per_set': n, 'sets': {}}
    for name, pages in sets.items():
        rows = [dict(_row([len(encode_variant(p, **kw).stream) for p in pages]), name=label) for label, kw in VARIANTS]
        rows.append(dict(_row([_lib('fast')(p) for p in pages]), name='liblz4，預設'))
        rows.append(dict(_row([_lib('hc')(p) for p in pages]), name='liblz4 HC，level 9'))
        out['sets'][name] = {'rows': rows, 'cycles': cycles(pages)}
    return out
