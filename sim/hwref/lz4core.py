"""Reference model of the LZ4 core of the accelerator: what the RTL has to reproduce byte for byte.

    encode(page)     the stream the encoder writes for one 4096 B page, and the sequences it chose
    decode(stream)   the page the decoder produces, or the first check that failed
    crc32(stream)    the checksum that goes into the completion and the COT entry

The stream is a plain LZ4 block: any LZ4 decoder opens what encode() writes, and
decode() opens what any LZ4 compressor writes for one page.

The encoder is the plain greedy one: one hash table, one candidate per position,
the first match is taken, the table is empty at the start of every page. Which
hash and how many table entries were chosen from measurements, see hwref.study.

Nothing here knows about descriptors, chunks or the bus; that is hwref.job.
"""
import zlib
from dataclasses import dataclass, field

PAGE = 4096
MINMATCH = 4          # shortest match
MFLIMIT = 12          # no match starts in the last 12 bytes of the page
LASTLITERALS = 5      # the last 5 bytes of the page are always literals
HASH_BITS = 10        # the hash table has 1024 entries


def crc32(data):
    """CRC-32 of zlib and Ethernet: polynomial 0x04C11DB7 reflected, start 0xFFFFFFFF, result inverted."""
    return zlib.crc32(bytes(data)) & 0xFFFFFFFF


def hash4(v, bits=HASH_BITS):
    """XOR of the 32-bit value cut into fields of `bits` bits, lowest field first."""
    h = 0
    while v:
        h ^= v & ((1 << bits) - 1)
        v >>= bits
    return h


@dataclass
class Encoded:
    stream: bytes
    seqs: list = field(default_factory=list)     # (literals, match length, offset); the last one has match length 0
    searched: int = 0                            # positions that went through the hash table

    @property
    def matches(self):
        return sum(1 for _, m, _ in self.seqs if m)


def put_length(out, n):
    """The extra bytes behind a 4-bit length field that holds 15: 255 as long as 255 or more is left, then the rest."""
    n -= 15
    while n >= 255:
        out.append(255)
        n -= 255
    out.append(n)


def put_sequence(out, literals, match_len, offset):
    """One LZ4 sequence. match_len 0 means the last sequence of the block: literals only."""
    ll = len(literals)
    ml = match_len - MINMATCH if match_len else 0
    out.append((min(ll, 15) << 4) | min(ml, 15))             # token
    if ll >= 15:
        put_length(out, ll)
    out += literals
    if match_len:
        out += offset.to_bytes(2, 'little')
        if ml >= 15:
            put_length(out, ml)


def encode(page, hash_bits=HASH_BITS):
    """Compress one page into an LZ4 block."""
    page = bytes(page)
    n = len(page)
    out, seqs = bytearray(), []
    table = [None] * (1 << hash_bits)            # hash -> last position seen with it; None: nothing yet in this page
    word = [int.from_bytes(page[i:i + 4], 'little') for i in range(max(0, n - 3))]
    last_start = n - MFLIMIT                     # last position where a match may start
    match_end = n - LASTLITERALS                 # a match stops before this position
    anchor = 0                                   # first byte not yet written to the stream
    ip = 0                                       # position being looked at
    searched = 0
    while ip <= last_start:
        h = hash4(word[ip], hash_bits)
        cand = table[h]                          # read the entry, then replace it: every position looked at goes in
        table[h] = ip
        searched += 1
        if cand is None or word[cand] != word[ip]:
            ip += 1                              # no match here; this byte becomes a literal
            continue
        length = MINMATCH
        while ip + length < match_end and page[cand + length] == page[ip + length]:
            length += 1
        put_sequence(out, page[anchor:ip], length, ip - cand)
        seqs.append((ip - anchor, length, ip - cand))
        ip += length                             # positions inside the match are not put into the table
        anchor = ip
    put_sequence(out, page[anchor:], 0, 0)
    seqs.append((n - anchor, 0, 0))
    return Encoded(bytes(out), seqs, searched)


# ---- decoder
OK, UNDERRUN, OVERFLOW, OFFSET, SHORT = 'OK', 'UNDERRUN', 'OVERFLOW', 'OFFSET', 'SHORT'
DECODE_ERRORS = {
    UNDERRUN: 'stream 在一個 sequence 的中間就用完了',
    OVERFLOW: '照 stream 做下去，輸出會超過 4096 B',
    OFFSET: 'offset 是 0，或比已經輸出的 byte 數還大',
    SHORT: 'stream 正常結束，輸出卻不到 4096 B',
}


@dataclass
class Decoded:
    page: bytes = None           # None unless status is OK
    status: str = OK
    at: int = 0                  # stream position where the check failed
    produced: int = 0            # output bytes at that moment
    seqs: list = field(default_factory=list)


def decode(stream, size=PAGE):
    """Open one LZ4 block that has to give exactly `size` bytes. Stops at the first check that fails."""
    s = bytes(stream)
    n = len(s)
    out, seqs = bytearray(), []
    i = 0                                        # next stream byte

    def fail(status):
        return Decoded(None, status, i, len(out), seqs)

    while True:
        if i >= n:
            return fail(UNDERRUN)
        token = s[i]
        i += 1
        ll = token >> 4                          # literal length
        if ll == 15:
            while True:
                if i >= n:
                    return fail(UNDERRUN)
                b = s[i]
                i += 1
                ll += b
                if len(out) + ll > size:         # checked at every byte, so the counter never needs more than 13 bits
                    return fail(OVERFLOW)
                if b != 255:
                    break
        if len(out) + ll > size:
            return fail(OVERFLOW)
        if i + ll > n:
            return fail(UNDERRUN)
        out += s[i:i + ll]
        i += ll
        if i == n:                               # the block ends behind the literals of its last sequence
            seqs.append((ll, 0, 0))
            break
        if i + 2 > n:
            return fail(UNDERRUN)
        offset = s[i] | (s[i + 1] << 8)
        i += 2
        if offset == 0 or offset > len(out):
            return fail(OFFSET)
        ml = (token & 15) + MINMATCH             # match length
        if token & 15 == 15:
            while True:
                if i >= n:
                    return fail(UNDERRUN)
                b = s[i]
                i += 1
                ml += b
                if len(out) + ml > size:
                    return fail(OVERFLOW)
                if b != 255:
                    break
        if len(out) + ml > size:
            return fail(OVERFLOW)
        for _ in range(ml):                      # byte by byte: the match may overlap what it is producing
            out.append(out[len(out) - offset])
        seqs.append((ll, ml, offset))
    if len(out) != size:
        return fail(SHORT)
    return Decoded(bytes(out), OK, i, len(out), seqs)


# ---- cycle counts of the baseline micro-architecture. Estimates from counting, not measurements.
BEAT = 8              # bytes per bus beat and per internal word
HISTORY = 24          # the decoder keeps its last 24 output bytes in a register; shorter offsets copy from it


def beats(n):
    return -(-n // BEAT)


def encode_cycles(e, per_match=6):
    """One position per cycle while searching. A match costs `per_match` fixed cycles (the compare stage, token,
    offset, three to refill the pipeline), one cycle per further 8 B of match, and the literals in front of it
    at 8 B per cycle after one cycle of read latency."""
    c = e.searched
    for ll, ml, _ in e.seqs:
        lit = 1 + beats(ll) if ll else 0
        c += (per_match + ml // BEAT + lit) if ml else (1 + lit)
    return c


def decode_cycles(seqs):
    """Per sequence: a token cycle, the literals at 8 B per cycle, an offset cycle, one cycle of read latency and
    the match at 8 B per cycle; one more cycle when the offset is under HISTORY and the copy comes out of the
    history register instead of the page buffer."""
    c = 0
    for ll, ml, off in seqs:
        c += 1 + ((ll - 15) // 255 + 1 if ll >= 15 else 0) + beats(ll)
        if ml:
            c += 2 + ((ml - 19) // 255 + 1 if ml >= 19 else 0) + beats(ml) + (1 if off < HISTORY else 0)
    return c
