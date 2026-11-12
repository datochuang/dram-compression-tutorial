"""The LZ4 HW as the kernel sees it in the host simulation: one function, one job.

    completion = hw.run(descriptor)

The descriptor and the completion are the byte layouts of interface.json. The
ring, the doorbell and the interrupt are left out on purpose; they carry the
same two structures and add nothing to the control procedure.

The HW keeps nothing between two calls. It touches the frame and the chunks the
descriptor names and nothing else, and it refuses a descriptor that points
outside the frame area or the chunk pool.

Fault injection, for the paths of the kernel that a healthy HW never takes:

    hw.inject('COMPRESS', 'bus_error')     the next COMPRESS ends with BUS_ERROR; its chunks hold rubbish
    hw.inject('DECOMPRESS', 'bus_error')   the next DECOMPRESS ends with BUS_ERROR; its frame holds rubbish
    hw.inject('DECOMPRESS', 'bad_stream')  the next DECOMPRESS says BAD_STREAM although the stored stream is good
    hw.inject('COMPRESS', 'bad_data')      the next COMPRESS says OK and stores a stream, with the right CRC-32,
                                           of a page that differs from the frame in one byte
    hw.down = True                         the driver has given up (timeout, reset and resend all failed):
                                           run returns None
"""
from collections import Counter
from math import ceil

from .codec import crc32


class Lz4Hw:
    def __init__(self, spec, cfg, dram, codec, log=None):
        self.spec, self.cfg, self.dram, self.codec = spec, cfg, dram, codec
        self.log = log or (lambda *a, **k: None)
        self.OP, self.ST = spec.enum['opcode'], spec.enum['status']
        self.BD, self.FL = spec.enum['bad_desc'], spec.enum['flag']
        self.st = Counter()
        self.watch = None                                 # told about every frame and chunk the HW reads or writes
        self.faults = []                                  # (opcode name, mode), each used up by the next job of that opcode
        self.down = False

    def inject(self, opcode, mode):
        self.faults.append((opcode, mode))

    def _fault(self, d):
        name = self.spec.enum_name['opcode'][d['opcode']]
        for x in self.faults:
            if x[0] == name:
                self.faults.remove(x)
                self.st['injected_' + x[1]] += 1
                return x[1]
        return None

    def run(self, raw_desc):
        if self.down:
            self.st['no_answer'] += 1
            return None
        d = self.spec.unpack('job_desc', raw_desc)
        aux = self.check(d)
        fault = None if aux else self._fault(d)
        if aux:
            cpl = self._cpl(self.ST.BAD_DESC, d, aux=aux)
        elif fault == 'bus_error':
            cpl = self.bus_error(d)
        elif d['opcode'] == self.OP.COMPRESS:
            cpl = self.compress(d, wrong=fault == 'bad_data')
        else:
            cpl = self.decompress(d, fail=fault == 'bad_stream')
        self.st['jobs'] += 1
        self.st[self.spec.enum_name['opcode'].get(d['opcode'], '?') + '_' + self.spec.enum_name['status'][cpl['status']]] += 1
        return self.spec.pack('completion', cpl)

    def _cpl(self, status, d, length=0, checksum=0, flags=0, aux=0):
        return {'status': status, 'flags': flags, 'length': length, 'checksum': checksum, 'tag': d['tag'], 'aux': aux}

    def check(self, d):
        """What the HW verifies by itself before it touches memory. Returns a bad_desc code or 0."""
        cfg, B = self.cfg, self.BD
        n = d['count']
        if d['opcode'] not in (self.OP.COMPRESS, self.OP.DECOMPRESS):
            return B.OPCODE
        if not 1 <= n <= self.spec.const.CHUNK_SLOTS:
            return B.COUNT
        if any(c >= cfg.pool_chunks for c in d['chunk'][:n]):
            return B.CHUNK_RANGE
        if d['frame_pa'] % cfg.page or not cfg.fc_base <= d['frame_pa'] < cfg.fc_base + cfg.frames * cfg.page:
            return B.FRAME_RANGE
        room = min(cfg.page, n * cfg.chunk)
        if d['opcode'] == self.OP.COMPRESS:
            if not 0 < d['limit'] <= room:
                return B.LENGTH
        elif not 0 < d['comp_len'] <= room or (d['flags'] & self.FL.RAW and d['comp_len'] != cfg.page):
            return B.LENGTH
        return 0

    def bus_error(self, d):
        """The bus refused an access in the middle of the job. What the job was allowed to write is undefined."""
        cfg, dram, w = self.cfg, self.dram, self.watch
        if d['opcode'] == self.OP.COMPRESS:
            if w:
                w.hw_reads(d['frame_pa'])
            for c in d['chunk'][:d['count']]:
                if w:
                    w.hw_writes_chunk(c)
                dram.write(cfg.chunk_pa(c), b'\xEE' * cfg.chunk)
        else:
            if w:
                w.hw_writes(d['frame_pa'])
            dram.write(d['frame_pa'], b'\xEE' * cfg.page)
        self.log('HW', 'bus_error', frame_pa=d['frame_pa'])
        return self._cpl(self.ST.BUS_ERROR, d)

    def compress(self, d, wrong=False):
        """Frame to chunks. Above `limit` the answer is INCOMPRESSIBLE and the frame is untouched."""
        cfg, dram = self.cfg, self.dram
        chunks = d['chunk'][:d['count']]
        if self.watch:
            self.watch.hw_reads(d['frame_pa'])
        page = dram.read(d['frame_pa'], cfg.page)
        if wrong:                                         # fault injection: the encoder got one byte wrong
            page = bytes([page[0] ^ 0xFF]) + bytes(page[1:])
        stream, flags = self.codec.compress(page), 0
        if stream is None or len(stream) > d['limit']:
            if d['limit'] < cfg.page:
                self.log('HW', 'compress', frame_pa=d['frame_pa'], result='INCOMPRESSIBLE',
                         stream_len=len(stream) if stream else cfg.page, limit=d['limit'])
                return self._cpl(self.ST.INCOMPRESSIBLE, d)
            stream, flags = page, self.FL.RAW
        used = ceil(len(stream) / cfg.chunk)
        for i in range(used):
            if self.watch:
                self.watch.hw_writes_chunk(chunks[i])
            dram.write(cfg.chunk_pa(chunks[i]), stream[i * cfg.chunk:(i + 1) * cfg.chunk])
        self.log('HW', 'compress', frame_pa=d['frame_pa'], stream_len=len(stream), wrote_chunks=chunks[:used],
                 crc=crc32(stream))
        return self._cpl(self.ST.OK, d, len(stream), crc32(stream), flags)

    def decompress(self, d, fail=False):
        """Chunks to frame. The CRC-32 is checked before a single byte of the frame is written."""
        cfg, dram = self.cfg, self.dram
        L = d['comp_len']
        chunks = d['chunk'][:ceil(L / cfg.chunk)]
        if self.watch:
            self.watch.hw_writes(d['frame_pa'])           # also on BAD_STREAM: real hardware may have written part of it
            for c in chunks:
                self.watch.hw_reads_chunk(c)
        stream = b''.join(dram.read(cfg.chunk_pa(c), cfg.chunk) for c in chunks)[:L]
        page = None
        if crc32(stream) == d['checksum'] and not fail:   # fail: fault injection, the decoder got it wrong
            page = stream if d['flags'] & self.FL.RAW else self.codec.decompress(stream, cfg.page)
        if page is None:
            self.log('HW', 'decompress', read_chunks=chunks, stream_len=L, result='BAD_STREAM',
                     crc=crc32(stream), expected_crc=d['checksum'])
            return self._cpl(self.ST.BAD_STREAM, d)
        dram.write(d['frame_pa'], page)
        self.log('HW', 'decompress', read_chunks=chunks, stream_len=L, crc=crc32(stream), frame_pa=d['frame_pa'])
        return self._cpl(self.ST.OK, d, cfg.page, d['checksum'], d['flags'] & self.FL.RAW)
