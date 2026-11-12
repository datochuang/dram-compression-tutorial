"""Reference model of one job: 48 B descriptor and memory in, 16 B completion and memory out.

This is what an RTL test bench compares against once the ring has handed the
engine a descriptor. The byte layouts come from interface.json, the LZ4 stream
from hwref.lz4core. The model also records every memory access it makes, in
bursts, so a test bench can check that the RTL stays inside the same addresses.

The order of the bursts is the baseline's, not a requirement. What is required
is listed in `defined`: the bytes of memory whose value the job fixes.
"""
from dataclasses import dataclass, field
from math import ceil

from ifsim.spec import SPEC

from . import lz4core as C

CHUNK = SPEC.const.CHUNK_SIZE
PAGE = SPEC.const.PAGE_SIZE
SLOTS = SPEC.const.CHUNK_SLOTS
OP, ST, BD, FL = SPEC.enum['opcode'], SPEC.enum['status'], SPEC.enum['bad_desc'], SPEC.enum['flag']


class BusError(Exception):
    pass


class Mem:
    """Sparse byte memory. read() and write() are bursts and are logged; peek() and poke() are the test bench."""

    def __init__(self):
        self.blocks = {}
        self.log = []                # ('R' or 'W', address, bytes)
        self.bad = set()             # 512 B block addresses that answer with a bus error

    def _span(self, pa, n):
        while n:
            base, off = pa - pa % CHUNK, pa % CHUNK
            k = min(n, CHUNK - off)
            yield base, off, k
            pa, n = pa + k, n - k

    def peek(self, pa, n):
        return b''.join(bytes(self.blocks.get(b, bytes(CHUNK))[o:o + k]) for b, o, k in self._span(pa, n))

    def poke(self, pa, data):
        i = 0
        for b, o, k in self._span(pa, len(data)):
            self.blocks.setdefault(b, bytearray(CHUNK))[o:o + k] = data[i:i + k]
            i += k

    def _burst(self, kind, pa, n):
        self.log.append((kind, pa, n))
        if any(b in self.bad for b, _, _ in self._span(pa, n)):
            raise BusError(pa)

    def read(self, pa, n):
        self._burst('R', pa, n)
        return self.peek(pa, n)

    def write(self, pa, data):
        self._burst('W', pa, len(data))
        self.poke(pa, data)


@dataclass
class Regs:
    """The four registers that fence in what a job may touch."""
    pool_base: int
    pool_chunks: int
    frame_base: int
    frame_count: int

    def chunk_pa(self, c):
        return self.pool_base + c * CHUNK


@dataclass
class Result:
    completion: dict
    raw: bytes                                   # the 16 B as they are written to the completion ring
    stream: bytes = None                         # what was written to or read from the chunks
    defined: list = field(default_factory=list)  # (address, bytes): memory whose content this job fixes
    undefined: list = field(default_factory=list)  # (address, bytes): memory the job may have changed to anything


def check(d, regs):
    """The checks the hardware makes before it touches a frame or a chunk, in this order. Returns a bad_desc code or 0."""
    n = d['count']
    if d['opcode'] not in (OP.COMPRESS, OP.DECOMPRESS):
        return BD.OPCODE
    if not 1 <= n <= SLOTS:
        return BD.COUNT
    if any(c >= regs.pool_chunks for c in d['chunk'][:n]):
        return BD.CHUNK_RANGE
    if d['frame_pa'] % PAGE or not regs.frame_base <= d['frame_pa'] < regs.frame_base + regs.frame_count * PAGE:
        return BD.FRAME_RANGE
    room = min(PAGE, n * CHUNK)
    if d['opcode'] == OP.COMPRESS:
        if not 0 < d['limit'] <= room:
            return BD.LENGTH
    elif not 0 < d['comp_len'] <= room or (d['flags'] & FL.RAW and d['comp_len'] != PAGE):
        return BD.LENGTH
    return 0


def _done(d, status, length=0, checksum=0, flags=0, aux=0, **kw):
    cpl = {'status': status, 'flags': flags, 'length': length, 'checksum': checksum, 'tag': d['tag'], 'aux': aux}
    return Result(cpl, SPEC.pack('completion', cpl), **kw)


def compress(d, regs, mem):
    listed = [(regs.chunk_pa(c), CHUNK) for c in d['chunk'][:d['count']]]
    try:
        page = b''.join(mem.read(d['frame_pa'] + o, CHUNK) for o in range(0, PAGE, CHUNK))
        stream, flags = C.encode(page).stream, 0
        if len(stream) >= PAGE or len(stream) > d['limit']:
            if d['limit'] < PAGE:
                return _done(d, ST.INCOMPRESSIBLE, undefined=listed)
            stream, flags = page, FL.RAW
        used = ceil(len(stream) / CHUNK)
        for i in range(used):                    # every chunk is written whole; behind the stream come zeros
            mem.write(listed[i][0], stream[i * CHUNK:(i + 1) * CHUNK].ljust(CHUNK, b'\0'))
    except BusError:
        return _done(d, ST.BUS_ERROR, undefined=listed)
    defined = [(listed[i][0], min(CHUNK, len(stream) - i * CHUNK)) for i in range(used)]
    tail = len(stream) % CHUNK
    return _done(d, ST.OK, len(stream), C.crc32(stream), flags, stream=stream, defined=defined,
                 undefined=[(listed[used - 1][0] + tail, CHUNK - tail)] if tail else [])


def decompress(d, regs, mem):
    frame = [(d['frame_pa'], PAGE)]
    length = d['comp_len']
    try:
        stream = b''.join(mem.read(regs.chunk_pa(c), CHUNK) for c in d['chunk'][:ceil(length / CHUNK)])[:length]
        page = None
        if C.crc32(stream) == d['checksum']:
            page = stream if d['flags'] & FL.RAW else C.decode(stream).page
        if page is None:
            return _done(d, ST.BAD_STREAM, stream=stream, undefined=frame)
        for o in range(0, PAGE, CHUNK):
            mem.write(d['frame_pa'] + o, page[o:o + CHUNK])
    except BusError:
        return _done(d, ST.BUS_ERROR, undefined=frame)
    return _done(d, ST.OK, PAGE, d['checksum'], d['flags'] & FL.RAW, stream=stream, defined=frame)


def run(raw_desc, regs, mem):
    """One job. `mem.log` afterwards holds the bursts on frames and chunks."""
    d = SPEC.unpack('job_desc', bytes(raw_desc))
    aux = check(d, regs)
    if aux:
        return _done(d, ST.BAD_DESC, aux=aux)
    return compress(d, regs, mem) if d['opcode'] == OP.COMPRESS else decompress(d, regs, mem)


def allowed(d, regs):
    """Address ranges a job with this descriptor may touch, as (kind, address, bytes): HW-MEM-1."""
    if check(d, regs):
        return []
    chunks = [regs.chunk_pa(c) for c in d['chunk'][:d['count']]]
    if d['opcode'] == OP.COMPRESS:
        return [('R', d['frame_pa'], PAGE)] + [('W', a, CHUNK) for a in chunks]
    return [('R', a, CHUNK) for a in chunks[:ceil(d['comp_len'] / CHUNK)]] + [('W', d['frame_pa'], PAGE)]
