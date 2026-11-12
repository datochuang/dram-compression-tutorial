"""Test vectors for the RTL, all produced by the reference models and all reproducible from seeds.

    encode_vectors()     pages with what the encoder has to write for them
    decode_vectors()     streams the encoder never writes but the decoder has to open
    bad_streams()        streams the decoder has to refuse, one per kind of damage
    job_vectors()        descriptor and memory in, completion and memory out
    write(out_dir)       all of them as files

A page that needs a particular length or offset in its stream is not written by
hand. It is built from a seed, encoded, and kept only when the stream has the
property, so every vector stays honest when the encoder changes.
"""
import functools
import json
import os
import random
import struct

from ifsim.spec import SPEC

from . import job as J
from . import lz4core as C

PAGE, CHUNK = C.PAGE, J.CHUNK
OP, ST, BD, FL = J.OP, J.ST, J.BD, J.FL

# The address map of the examples: the full-size machine of the simulators.
REGS = J.Regs(pool_base=0x86100000, pool_chunks=563200, frame_base=0x97400000, frame_count=35840)
RING = dict(JOB_BASE=0x80180000, JOB_SIZE=64, CPL_BASE=0x80181000, CPL_SIZE=64)


# ---- pages
def _find(build, want, tries=3000):
    for seed in range(tries):
        page = build(random.Random(seed))
        if len(page) == PAGE and want(C.encode(page)):
            return page
    raise RuntimeError('no seed gives a page with the wanted property')


def _pad(b):
    return bytes(b[:PAGE]).ljust(PAGE, b'\0')


def records_page(seed=15, used=3436):
    """What a page of kernel or driver data tends to look like: small records with ids, counters, pointers and
    names, and an unused rest. With the default arguments its stream is 1837 B, the length of the example in the
    interface spec."""
    r = random.Random(seed)
    names = [b'uart0', b'spi1', b'timer', b'modem_rx', b'modem_tx', b'heap', b'log', b'nvram', b'usb_ep1', b'audio']
    ptrs = [0x9A3F0000 + r.randrange(1 << 12) * 8 for _ in range(16)]
    out, i = bytearray(), 0
    while len(out) < used:
        out += struct.pack('<IHHII', 0x1000 + i, r.randrange(4), r.randrange(600), r.choice(ptrs),
                           r.getrandbits(32) if r.random() < 0.25 else 0)
        out += r.choice(names).ljust(12, b'\0')
        if r.random() < 0.15:
            out += r.randbytes(r.choice((4, 8, 20)))
        i += 1
    return bytes(out).ljust(PAGE, b'\0')[:PAGE]


def words_page(seed=3):
    r = random.Random(seed)
    vocab = [bytes(r.choice(b'abcdefghijklmnopqrstuvwxyz') for _ in range(r.randrange(2, 9))) for _ in range(180)]
    out = bytearray()
    while len(out) < PAGE:
        out += r.choice(vocab) + r.choice((b' ', b' ', b' ', b', ', b'.\n', b'_', b'('))
    return bytes(out[:PAGE])


def few_symbols_page(seed=5, symbols=b'ab'):
    r = random.Random(seed)
    return bytes(r.choice(symbols) for _ in range(PAGE))


def runs_page(seed=9):
    r = random.Random(seed)
    out = bytearray()
    while len(out) < PAGE:
        out += bytes([r.randrange(256)]) * r.choice((1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 40, 300))
    return bytes(out[:PAGE])


def lit_page(ll):
    """First sequence has exactly `ll` literals in front of its match."""
    if ll == 0:           # two matches back to back: A B B A
        return _find(lambda r: _pad((lambda a, b: a + b + b + a)(r.randbytes(8), r.randbytes(8))),
                     lambda e: any(l == 0 and m for l, m, _ in e.seqs[1:]))
    if ll < 4:            # a period of `ll` bytes: the match starts right behind the first period
        return _find(lambda r: _pad(r.randbytes(ll) * 6 + r.randbytes(40)), lambda e: e.seqs[0][0] == ll and e.seqs[0][1])
    return _find(lambda r: _pad((lambda a: a + a[:8] + r.randbytes(24))(r.randbytes(ll))),
                 lambda e: e.seqs[0][0] == ll and e.seqs[0][1])


def match_page(ml):
    """First sequence has a match of exactly `ml` bytes."""
    def build(r):
        a = r.randbytes(ml + 8)
        return _pad(a + a[:ml] + bytes([a[ml] ^ 0x5A]) + r.randbytes(24))
    return _find(build, lambda e: e.seqs[0][1] == ml)


def offset_page(off):
    """One period of `off` random bytes repeated over the whole page: the first match has offset `off`."""
    return _find(lambda r: (r.randbytes(off) * (PAGE // off + 1))[:PAGE], lambda e: e.seqs[0][2] == off and e.seqs[0][0] == off)


def late_match_page(at):
    """8 bytes at the start of the page come back at position `at`, with zeros in between."""
    def build(r):
        a = bytes(x | 1 for x in r.randbytes(8))
        return _pad(a + bytes(at - 8) + a)
    if at <= PAGE - C.MFLIMIT:
        return _find(build, lambda e: any(o == at for _, _, o in e.seqs))
    return _find(build, lambda e: e.seqs[-1][0] == PAGE - at and not any(o == at for _, _, o in e.seqs))


def length_page(target):
    """A page whose stream is exactly `target` bytes: random bytes, then zeros, then a few random bytes."""
    for tail in (8, 9, 10, 11, 12, 13, 0, 1, 2, 3):
        k = max(0, target - 34)
        for _ in range(8):                                   # the stream grows by one byte per random byte, nearly
            r = random.Random(target)
            page = r.randbytes(k) + bytes(PAGE - k - tail) + r.randbytes(tail)
            got = len(C.encode(page).stream)
            if got == target:
                return page
            k = min(PAGE - tail, max(0, k + target - got))
    raise RuntimeError(f'no page found with a {target} B stream')


LIT = (0, 1, 2, 3, 14, 15, 16, 269, 270, 271, 525)
MATCH = (4, 5, 18, 19, 20, 273, 274, 275, 529)
OFFSET = (1, 2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 31, 32, 33, 255, 256, 257, 1024, 2047)
LENGTH = (511, 512, 513, 1023, 1024, 1025, 3583, 3584, 3585, 4094, 4095, 4096, 4097)


@functools.lru_cache(maxsize=None)
def encode_vectors():
    """List of (name, what it is for, page)."""
    v = [('example', 'the page of the worked example in the design spec', records_page()),
         ('zeros', 'one match that runs to 5 bytes before the end of the page; 16 extra length bytes', bytes(PAGE)),
         ('random', 'nothing matches: one sequence of 4096 literals, stream longer than the page',
          random.Random(11).randbytes(PAGE)),
         ('words', 'text-like, several hundred short sequences', words_page()),
         ('two_symbols', 'almost every position matches; short offsets, hash entries reused at once', few_symbols_page()),
         ('four_symbols', 'as two_symbols with longer literal runs', few_symbols_page(6, b'acgt')),
         ('runs', 'runs of one byte with lengths around 8 and 16: overlapping matches of every short length', runs_page())]
    v += [(f'lit_{n}', f'literal length {n} in the first sequence that has a match', lit_page(n)) for n in LIT]
    v += [(f'match_{n}', f'match length {n}', match_page(n)) for n in MATCH]
    v += [(f'offset_{n}', f'offset {n}, match from position {n} to the end', offset_page(n)) for n in OFFSET]
    v += [('offset_4084', 'largest offset the encoder can produce; match starts at the last allowed position',
           late_match_page(PAGE - C.MFLIMIT)),
          ('late_4085', 'the same 8 bytes one position later: no match may start there', late_match_page(PAGE - C.MFLIMIT + 1))]
    v += [(f'len_{n}', f'stream of exactly {n} B', length_page(n)) for n in LENGTH]
    return v


def _seq(literals, match_len=0, offset=0):
    out = bytearray()
    C.put_sequence(out, literals, match_len, offset)
    return bytes(out)


@functools.lru_cache(maxsize=None)
def decode_vectors():
    """List of (name, what it is for, stream, page): valid streams that do not come from the encoder."""
    r = random.Random(21)
    v = []
    a = r.randbytes(4)
    v.append(('dec_offset_4092', 'largest offset a 4096 B block can hold; ends with an empty last sequence',
              _seq(a + b'\0', PAGE - 9, 1) + _seq(b'', 4, PAGE - 4) + _seq(b''), a + bytes(PAGE - 8) + a))
    lit = r.randbytes(20)
    v.append(('dec_match_to_end', 'match runs to the very last byte of the page', _seq(lit, PAGE - 20, 20) + _seq(b''),
              (lit * (PAGE // 20 + 1))[:PAGE]))
    for off in (1, 2, 3, 5, 7, 8, 9, 15, 16, 17):
        for ml in (4, 7, 8, 9, 15, 16, 17, 23):
            lit = r.randbytes(off + 3)
            body = lit + bytes(lit[len(lit) - off + i % off] for i in range(ml))
            n = PAGE - len(body)                             # the rest of the page: one byte repeated
            v.append((f'dec_overlap_{off}_{ml}', f'offset {off}, match length {ml}',
                      _seq(lit, ml, off) + _seq(b'Z', n - 6, 1) + _seq(b'ZZZZZ'), body + b'Z' * n))
    try:
        import lz4.block
        import lz4
        for name, page in (('words', words_page()), ('example', records_page()), ('runs', runs_page())):
            v.append((f'dec_liblz4_{name}', f'liblz4 {lz4.library_version_string()}, default level', lz4.block.compress(page, store_size=False), page))
            v.append((f'dec_liblz4hc_{name}', f'liblz4 {lz4.library_version_string()}, high compression level 9: what the build tool may use for RO pages',
                      lz4.block.compress(page, store_size=False, mode='high_compression', compression=9), page))
    except ImportError:
        pass
    for name, _, stream, page in v:
        assert C.decode(stream).page == page and len(stream) <= PAGE, name
    return v


@functools.lru_cache(maxsize=None)
def bad_streams():
    """List of (name, what is wrong, stream, the check of lz4core.decode that fires)."""
    good = C.encode(lit_page(14))                            # first sequence: 14 literals, match of 8
    s = good.stream
    l0, m0, _ = good.seqs[0]
    first_lits_end = 1 + l0                                  # token and l0 literals (l0 is under 15 in this page)
    assert l0 < 15 and m0 < 19
    zeros = C.encode(bytes(PAGE)).stream
    half = bytes(2048)
    rest = _seq(b'\0', PAGE - 16 - 6, 1) + _seq(bytes(5))   # what would complete the page behind 16 bytes of output
    v = [('bad_cut_in_literals', 'stream ends in the middle of a run of literals', s[:first_lits_end - 1], C.UNDERRUN),
         ('bad_cut_in_offset', 'stream ends after the first byte of an offset', s[:first_lits_end + 1], C.UNDERRUN),
         ('bad_cut_in_length', 'stream ends in the extra bytes of a match length', zeros[:8], C.UNDERRUN),
         ('bad_cut_after_match', 'stream ends behind a match, where a token has to follow', s[:first_lits_end + 2], C.UNDERRUN),
         ('bad_cut_after_literals', 'stream ends behind the literals of an early sequence: a proper end, but far too little output',
          s[:first_lits_end], C.SHORT),
         ('bad_half_page', 'a correct block of a 2048 B page', C.encode(half).stream, C.SHORT),
         ('bad_offset_zero', 'offset 0', _seq(b'12345678', 8, 0) + rest, C.OFFSET),
         ('bad_offset_far', 'offset 9 after 8 bytes of output', _seq(b'12345678', 8, 9) + rest, C.OFFSET),
         ('bad_literals_over', 'last sequence has 6 literals where 5 fit', _seq(b'\0', PAGE - 6, 1) + _seq(bytes(6)), C.OVERFLOW),
         ('bad_match_over', 'match of 4096 after 1 byte of output', _seq(b'\0', PAGE, 1) + _seq(b''), C.OVERFLOW),
         ('bad_length_runaway', '4096 bytes of 0xFF: a literal length that never ends', b'\xff' * PAGE, C.OVERFLOW),
         ('bad_extra_byte', 'one byte behind a complete block', s + b'\0', C.UNDERRUN),
         ('bad_extra_sequence', 'a match behind a complete block', s + b'\x01\x00\x00', C.OVERFLOW)]
    for name, _, stream, why in v:
        d = C.decode(stream)
        assert d.status == why and 0 < len(stream) <= PAGE, (name, d.status)
    return v


# ---- jobs
def desc(opcode, frame=0x97A1C000, chunks=(0x1C044, 0x1C045, 0x30A71, 0x30A75, 0x412E0, 0x412E1, 0x66B3F), count=None,
         limit=0, comp_len=0, flags=0, checksum=0, tag=0x2A8, rsvd=0):
    return dict(opcode=opcode, count=len(chunks) if count is None else count, limit=limit, frame_pa=frame, comp_len=comp_len,
                flags=flags, checksum=checksum, tag=tag, chunk=tuple(chunks), rsvd=rsvd)


@functools.lru_cache(maxsize=None)
def job_vectors():
    """List of dicts: name, note, regs, desc, mem_before, completion, mem_after, undefined, allowed, bus_error_at."""
    out = []
    pages = {n: p for n, _, p in encode_vectors()}
    seven = (0x1C044, 0x1C045, 0x30A71, 0x30A75, 0x412E0, 0x412E1, 0x66B3F)
    eight = seven + (0x00000,)
    frame = 0x97A1C000

    def add(name, note, d, before, regs=REGS, bad=(), provisional=False):
        mem = J.Mem()
        for pa, data in before:
            mem.poke(pa, data)
        mem.bad = set(bad)
        raw = SPEC.pack('job_desc', d)
        res = J.run(raw, regs, mem)
        out.append({'name': name, 'note': note, 'provisional': provisional,
                    'regs': {'POOL_BASE': regs.pool_base, 'POOL_CHUNKS': regs.pool_chunks,
                             'FRAME_BASE': regs.frame_base, 'FRAME_COUNT': regs.frame_count},
                    'desc': raw.hex(), 'desc_fields': {k: list(x) if isinstance(x, tuple) else x for k, x in d.items()},
                    'mem_before': [{'pa': pa, 'hex': bytes(data).hex()} for pa, data in before],
                    'bus_error_at': sorted(bad),
                    'completion': res.raw.hex(), 'completion_fields': res.completion,
                    'status': SPEC.enum_name['status'][res.completion['status']],
                    'mem_after': [{'pa': pa, 'hex': mem.peek(pa, n).hex()} for pa, n in res.defined],
                    'undefined': [{'pa': pa, 'bytes': n} for pa, n in res.undefined],
                    'allowed': [{'kind': k, 'pa': pa, 'bytes': n} for k, pa, n in J.allowed(d, regs)]})
        return res

    def chunk_mem(stream, chunks):
        return [(REGS.chunk_pa(chunks[i // CHUNK]), stream[i:i + CHUNK].ljust(CHUNK, b'\xEE')) for i in range(0, len(stream), CHUNK)]

    def both(name, note, page, chunks=seven, limit=3584):
        """A COMPRESS and, when it stored something, the DECOMPRESS that brings the page back."""
        res = add('c_' + name, note, desc(OP.COMPRESS, frame, chunks, limit=limit), [(frame, page)])
        c = res.completion
        if c['status'] == ST.OK:
            used = chunks[:-(-c['length'] // CHUNK)]
            add('d_' + name, 'the stream stored by c_' + name, desc(OP.DECOMPRESS, frame + PAGE, used, comp_len=c['length'],
                flags=c['flags'], checksum=c['checksum'], tag=0x2A9), chunk_mem(res.stream, used))
        return res

    both('example', 'the worked example of the design spec', pages['example'])
    both('zeros', 'shortest stream there is, 26 B in one chunk', pages['zeros'])
    both('words', 'several hundred sequences', pages['words'])
    both('len_512', 'stream fills its last chunk exactly', pages['len_512'])
    both('len_513', 'one byte in the second chunk', pages['len_513'])
    both('len_3584', 'stream exactly at the limit of 7 chunks', pages['len_3584'])
    both('len_3585_limit_3584', 'one byte over the limit: INCOMPRESSIBLE', pages['len_3585'])
    both('len_3585_limit_4096', 'the same page with 8 chunks: stored compressed', pages['len_3585'], eight, PAGE)
    both('len_4095_limit_4096', 'one byte shorter than the page: stored compressed', pages['len_4095'], eight, PAGE)
    both('len_4096_limit_4096', 'not shorter than the page: stored RAW', pages['len_4096'], eight, PAGE)
    both('random_limit_3584', 'INCOMPRESSIBLE', pages['random'])
    both('random_limit_4096', 'stored RAW in 8 chunks', pages['random'], eight, PAGE)
    both('one_chunk', 'count 1, limit 512', pages['len_512'], seven[:1], 512)
    both('one_chunk_over', 'count 1, limit 512, stream 513 B: INCOMPRESSIBLE', pages['len_513'], seven[:1], 512)
    both('limit_odd', 'limit 513 with 2 chunks', pages['len_513'], seven[:2], 513)
    both('chunks_descending', 'chunk numbers in falling order, the last chunk of the pool first',
         pages['words'], (REGS.pool_chunks - 1, 0x30A75, 0x30A71, 0x1C045, 0x1C044, 0x00001, 0x00000))
    add('c_first_frame', 'first frame of the frame area', desc(OP.COMPRESS, REGS.frame_base, seven, limit=3584),
        [(REGS.frame_base, pages['runs'])])
    last = REGS.frame_base + (REGS.frame_count - 1) * PAGE
    add('c_last_frame', 'last frame of the frame area', desc(OP.COMPRESS, last, seven, limit=3584), [(last, pages['runs'])])
    add('c_ignored_fields', 'comp_len, flags, checksum, rsvd and the unused chunk slot are not looked at by COMPRESS',
        desc(OP.COMPRESS, frame, seven + (0xFFFFFF,), count=7, limit=3584, comp_len=0x1234, flags=0xFFFF, checksum=0xFFFFFFFF,
             rsvd=0xFFFFFFFF), [(frame, pages['words'])])

    # DECOMPRESS of streams the hardware did not write, and of damaged ones
    for name, note, other, page in decode_vectors():
        if name.startswith('dec_liblz4') or name in ('dec_offset_4092', 'dec_match_to_end', 'dec_overlap_1_23', 'dec_overlap_15_17'):
            some = eight[:-(-len(other) // CHUNK)]
            add('d_' + name[4:], note, desc(OP.DECOMPRESS, frame, some, comp_len=len(other), checksum=C.crc32(other), tag=0x300),
                chunk_mem(other, some))
    stream = C.encode(pages['words']).stream
    used = seven[:-(-len(stream) // CHUNK)]
    add('d_count_larger', 'count 7 with a stream of fewer chunks: only the chunks the stream needs are read',
        desc(OP.DECOMPRESS, frame, seven, comp_len=len(stream), checksum=C.crc32(stream)), chunk_mem(stream, used))
    add('d_bad_crc', 'correct stream, checksum in the descriptor differs in one bit: BAD_STREAM',
        desc(OP.DECOMPRESS, frame, used, comp_len=len(stream), checksum=C.crc32(stream) ^ 0x00010000), chunk_mem(stream, used))
    flipped = bytearray(stream)
    flipped[len(stream) // 2] ^= 0x04
    add('d_bit_flip', 'one bit of the stored stream flipped, checksum of the original: BAD_STREAM',
        desc(OP.DECOMPRESS, frame, used, comp_len=len(stream), checksum=C.crc32(stream)), chunk_mem(bytes(flipped), used))
    add('d_raw_bad_crc', 'RAW page with a wrong checksum: BAD_STREAM',
        desc(OP.DECOMPRESS, frame, eight, comp_len=PAGE, flags=FL.RAW, checksum=C.crc32(pages['random']) ^ 1),
        chunk_mem(pages['random'], eight))
    for name, note, bad, why in bad_streams():
        some = eight[:-(-len(bad) // CHUNK)]
        add('d_' + name, f'{note}; checksum matches, the decoder check {why} fires',
            desc(OP.DECOMPRESS, frame, some, comp_len=len(bad), checksum=C.crc32(bad)), chunk_mem(bad, some))

    # BAD_DESC: nothing but the descriptor is read
    C_, D_ = OP.COMPRESS, OP.DECOMPRESS
    crc = C.crc32(stream)
    bad_desc = [
        ('opcode_0', 'opcode 0', desc(0, limit=3584)),
        ('opcode_3', 'opcode 3', desc(3, limit=3584)),
        ('opcode_255', 'opcode 255, and everything else wrong too: OPCODE is reported', desc(255, 0x1234, (0xFFFFFF,), count=0)),
        ('count_0', 'count 0', desc(C_, count=0, limit=512)),
        ('count_9', 'count 9', desc(C_, count=9, limit=3584)),
        ('count_before_chunk', 'count 9 and a chunk outside the pool: COUNT is reported', desc(C_, chunks=(REGS.pool_chunks,), count=9, limit=512)),
        ('chunk_first_outside', 'chunk number equal to POOL_CHUNKS', desc(C_, chunks=seven[:6] + (REGS.pool_chunks,), limit=3584)),
        ('chunk_max', 'chunk number 0xFFFFFF in the first slot', desc(C_, chunks=(0xFFFFFF,) + seven[1:], limit=3584)),
        ('chunk_before_frame', 'chunk outside the pool and frame outside the area: CHUNK_RANGE is reported',
         desc(C_, frame=0x1000, chunks=(REGS.pool_chunks,), limit=512)),
        ('frame_unaligned', 'frame_pa not a multiple of 4096', desc(C_, frame=frame + 8, limit=3584)),
        ('frame_below', 'frame_pa one page below FRAME_BASE', desc(C_, frame=REGS.frame_base - PAGE, limit=3584)),
        ('frame_above', 'frame_pa one page behind the frame area', desc(C_, frame=REGS.frame_base + REGS.frame_count * PAGE, limit=3584)),
        ('frame_in_pool', 'frame_pa inside the chunk pool', desc(D_, frame=REGS.pool_base, comp_len=len(stream), checksum=crc)),
        ('frame_before_length', 'frame outside the area and limit 0: FRAME_RANGE is reported', desc(C_, frame=0x1000, limit=0)),
        ('limit_0', 'COMPRESS with limit 0', desc(C_, limit=0)),
        ('limit_over_chunks', 'limit 3585 with 7 chunks', desc(C_, limit=3585)),
        ('limit_4097', 'limit 4097 with 8 chunks', desc(C_, chunks=eight, limit=4097)),
        ('comp_len_0', 'DECOMPRESS with comp_len 0', desc(D_, comp_len=0)),
        ('comp_len_over_chunks', 'comp_len 1025 with 2 chunks', desc(D_, chunks=seven[:2], comp_len=1025, checksum=crc)),
        ('comp_len_4097', 'comp_len 4097 with 8 chunks', desc(D_, chunks=eight, comp_len=4097)),
        ('raw_short', 'RAW flag with comp_len 4095', desc(D_, chunks=eight, comp_len=4095, flags=FL.RAW)),
    ]
    for name, note, d in bad_desc:
        add('bad_desc_' + name, note, d, [(frame, pages['words'])] + chunk_mem(stream, used))

    # BUS_ERROR: the proposal of the design spec, not yet in the interface
    add('bus_c_frame_read', 'error response on the third burst of the frame read', desc(C_, limit=3584), [(frame, pages['words'])],
        bad=[frame + 2 * CHUNK], provisional=True)
    add('bus_c_chunk_write', 'error response on the write of the second chunk', desc(C_, limit=3584), [(frame, pages['words'])],
        bad=[REGS.chunk_pa(seven[1])], provisional=True)
    add('bus_d_chunk_read', 'error response on the read of the first chunk',
        desc(D_, chunks=used, comp_len=len(stream), checksum=crc), chunk_mem(stream, used), bad=[REGS.chunk_pa(used[0])], provisional=True)
    add('bus_d_frame_write', 'error response on the last burst of the frame write',
        desc(D_, chunks=used, comp_len=len(stream), checksum=crc), chunk_mem(stream, used), bad=[frame + 7 * CHUNK], provisional=True)
    return out


# ---- files
def _hex(path, data):
    with open(path, 'w') as f:
        f.write('\n'.join(f'{b:02x}' for b in data) + '\n')


def write(out_dir):
    """Everything as files. Byte files hold one byte per line in hex, lowest address first, ready for $readmemh."""
    core = os.path.join(out_dir, 'core')
    os.makedirs(core, exist_ok=True)
    index = {'interface_version': SPEC.version,
             'parameters': {'HASH_BITS': C.HASH_BITS, 'MINMATCH': C.MINMATCH, 'MFLIMIT': C.MFLIMIT, 'LASTLITERALS': C.LASTLITERALS},
             'encode': [], 'decode_only': [], 'decode_bad': []}
    for name, note, page in encode_vectors():
        e = C.encode(page)
        _hex(os.path.join(core, name + '.page.hex'), page)
        _hex(os.path.join(core, name + '.stream.hex'), e.stream)
        index['encode'].append({'name': name, 'note': note, 'stream_bytes': len(e.stream), 'crc32': f'0x{C.crc32(e.stream):08X}',
                                'sequences': len(e.seqs), 'searched': e.searched,
                                'decodable_by_job': len(e.stream) <= PAGE})
    for name, note, stream, page in decode_vectors():
        _hex(os.path.join(core, name + '.stream.hex'), stream)
        _hex(os.path.join(core, name + '.page.hex'), page)
        index['decode_only'].append({'name': name, 'note': note, 'stream_bytes': len(stream), 'crc32': f'0x{C.crc32(stream):08X}'})
    for name, note, stream, why in bad_streams():
        d = C.decode(stream)
        _hex(os.path.join(core, name + '.stream.hex'), stream)
        index['decode_bad'].append({'name': name, 'note': note, 'stream_bytes': len(stream), 'crc32': f'0x{C.crc32(stream):08X}',
                                    'check': why, 'stream_position': d.at, 'bytes_produced': d.produced})
    with open(os.path.join(out_dir, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump(index, f, indent=1, ensure_ascii=False)
    jobs = job_vectors()
    with open(os.path.join(out_dir, 'jobs.json'), 'w', encoding='utf-8') as f:
        json.dump(jobs, f, indent=1, ensure_ascii=False)
    return {'encode': len(index['encode']), 'decode_only': len(index['decode_only']), 'decode_bad': len(index['decode_bad']),
            'jobs': len(jobs)}
