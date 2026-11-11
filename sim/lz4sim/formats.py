"""Bit-exact data layouts shared by the kernel, the accelerator and trace consumers.

Multi-byte fields are little-endian. Chunk numbers are 24-bit.

COT entry, 32 bytes
    0     flags      bit0 VALID, bit1 RO, bit2 RAW
    1     count      chunks in use, 0..8
    2..3  comp_len   bytes of the stored stream (4096 when RAW)
    4..7  checksum   CRC-32 of the stored stream
    8..31 chunk[0..7] 24-bit chunk numbers, unused slots zero

List chunk (baseline free-chunk stack), 512 bytes
    0..2    next       24-bit number of the next list chunk, 0xFFFFFF when none
    3..509  numbers    169 free chunk numbers, 24-bit each
    510,511 unused

Baseline descriptor, 16 bytes:  opcode u8, flags u8, limit u16, handle u32, frame_pa u32, tag u32
Software-variant descriptor, 48 bytes:
    opcode u8, count u8, limit u16, frame_pa u32, comp_len u16, flags u16, checksum u32, tag u32,
    chunk[0..7] 8 x 24-bit, 4 bytes pad
Completion, 16 bytes: status u8, flags u8, length u16, checksum u32, tag u32, aux u32
"""
import struct
from dataclasses import dataclass

ENTRY_SIZE = 32
CHUNK_SLOTS = 8
LIST_NUMBERS = 169
NO_CHUNK = 0xFFFFFF

F_VALID = 0x01
F_RO = 0x02
F_RAW = 0x04

OP_COMPRESS, OP_DECOMPRESS, OP_INVALIDATE, OP_INIT = 1, 2, 3, 4
OP_NAME = {OP_COMPRESS: 'COMPRESS', OP_DECOMPRESS: 'DECOMPRESS',
           OP_INVALIDATE: 'INVALIDATE', OP_INIT: 'INIT'}

(ST_OK, ST_INCOMPRESSIBLE, ST_POOL_FULL, ST_BAD_STREAM,
 ST_BAD_HANDLE, ST_BUS_ERROR, ST_BAD_DESC) = range(7)
ST_NAME = {ST_OK: 'OK', ST_INCOMPRESSIBLE: 'INCOMPRESSIBLE', ST_POOL_FULL: 'POOL_FULL',
           ST_BAD_STREAM: 'BAD_STREAM', ST_BAD_HANDLE: 'BAD_HANDLE',
           ST_BUS_ERROR: 'BUS_ERROR', ST_BAD_DESC: 'BAD_DESC'}


def pack24(n):
    return int(n).to_bytes(3, 'little')


def unpack24(b):
    return int.from_bytes(b, 'little')


@dataclass
class COTEntry:
    flags: int = 0
    count: int = 0
    comp_len: int = 0
    checksum: int = 0
    chunks: tuple = ()

    @property
    def valid(self):
        return bool(self.flags & F_VALID)

    @property
    def ro(self):
        return bool(self.flags & F_RO)

    @property
    def raw(self):
        return bool(self.flags & F_RAW)

    def pack(self):
        if self.count > CHUNK_SLOTS or len(self.chunks) != self.count:
            raise ValueError('count must equal the number of chunks, at most 8')
        b = bytearray(ENTRY_SIZE)
        b[0] = self.flags
        b[1] = self.count
        struct.pack_into('<HI', b, 2, self.comp_len, self.checksum)
        for i, c in enumerate(self.chunks):
            b[8 + 3 * i:11 + 3 * i] = pack24(c)
        return bytes(b)

    @classmethod
    def unpack(cls, b):
        flags, count = b[0], b[1]
        comp_len, checksum = struct.unpack_from('<HI', b, 2)
        n = min(count, CHUNK_SLOTS)
        chunks = tuple(unpack24(b[8 + 3 * i:11 + 3 * i]) for i in range(n))
        return cls(flags, count, comp_len, checksum, chunks)

    def to_dict(self):
        return {'flags': self.flags, 'count': self.count, 'comp_len': self.comp_len,
                'checksum': self.checksum, 'chunks': list(self.chunks)}


EMPTY_ENTRY = bytes(ENTRY_SIZE)


def pack_list_chunk(next_chunk, numbers, chunk_size=512):
    if len(numbers) > LIST_NUMBERS:
        raise ValueError('a list chunk holds at most 169 numbers')
    b = bytearray(chunk_size)
    b[0:3] = pack24(next_chunk)
    for i, n in enumerate(numbers):
        b[3 + 3 * i:6 + 3 * i] = pack24(n)
    return bytes(b)


def unpack_list_chunk(b, count=LIST_NUMBERS):
    nxt = unpack24(b[0:3])
    numbers = [unpack24(b[3 + 3 * i:6 + 3 * i]) for i in range(count)]
    return nxt, numbers


BASELINE_DESC_FMT = '<BBHIII'


@dataclass
class BaselineDesc:
    opcode: int
    handle: int = 0
    frame_pa: int = 0
    limit: int = 0
    tag: int = 0
    flags: int = 0
    SIZE = 16

    def pack(self):
        return struct.pack(BASELINE_DESC_FMT, self.opcode, self.flags, self.limit,
                           self.handle, self.frame_pa, self.tag)

    @classmethod
    def unpack(cls, b):
        opcode, flags, limit, handle, frame_pa, tag = struct.unpack_from(BASELINE_DESC_FMT, b)
        return cls(opcode, handle, frame_pa, limit, tag, flags)

    def to_dict(self):
        return {'opcode': OP_NAME.get(self.opcode, self.opcode), 'handle': self.handle,
                'frame_pa': self.frame_pa, 'limit': self.limit, 'tag': self.tag}


VARIANT_DESC_FMT = '<BBHIHHII'


@dataclass
class VariantDesc:
    opcode: int
    frame_pa: int = 0
    chunks: tuple = ()
    limit: int = 0
    comp_len: int = 0
    flags: int = 0
    checksum: int = 0
    tag: int = 0
    SIZE = 48

    @property
    def count(self):
        return len(self.chunks)

    def pack(self):
        if len(self.chunks) > CHUNK_SLOTS:
            raise ValueError('at most 8 chunks')
        head = struct.pack(VARIANT_DESC_FMT, self.opcode, len(self.chunks), self.limit,
                           self.frame_pa, self.comp_len, self.flags, self.checksum, self.tag)
        body = bytearray(28)
        for i, c in enumerate(self.chunks):
            body[3 * i:3 * i + 3] = pack24(c)
        return head + bytes(body)

    @classmethod
    def unpack(cls, b):
        opcode, count, limit, frame_pa, comp_len, flags, checksum, tag = \
            struct.unpack_from(VARIANT_DESC_FMT, b)
        chunks = tuple(unpack24(b[20 + 3 * i:23 + 3 * i]) for i in range(min(count, CHUNK_SLOTS)))
        return cls(opcode, frame_pa, chunks, limit, comp_len, flags, checksum, tag)

    def to_dict(self):
        return {'opcode': OP_NAME.get(self.opcode, self.opcode), 'frame_pa': self.frame_pa,
                'chunks': list(self.chunks), 'limit': self.limit, 'comp_len': self.comp_len,
                'flags': self.flags, 'checksum': self.checksum, 'tag': self.tag}


COMPLETION_FMT = '<BBHIII'


@dataclass
class Completion:
    status: int
    length: int = 0
    checksum: int = 0
    tag: int = 0
    flags: int = 0
    aux: int = 0
    SIZE = 16

    def pack(self):
        return struct.pack(COMPLETION_FMT, self.status, self.flags, self.length,
                           self.checksum, self.tag, self.aux)

    @classmethod
    def unpack(cls, b):
        status, flags, length, checksum, tag, aux = struct.unpack_from(COMPLETION_FMT, b)
        return cls(status, length, checksum, tag, flags, aux)
