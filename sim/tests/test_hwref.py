"""Reference models of the LZ4 hardware: the core, one job, the vectors and the generated design spec."""
import json
import os
import random
from math import ceil
from types import SimpleNamespace

import lz4.block
import pytest

from hostsim import codec
from hostsim.hw import Lz4Hw
from hwref import doc, study, vectors
from hwref import job as J
from hwref import lz4core as C
from ifsim import gen
from ifsim.spec import SPEC

PAGE = C.PAGE
ST, FL, OP = SPEC.enum['status'], SPEC.enum['flag'], SPEC.enum['opcode']
LOOSE = {'dec_offset_4092', 'dec_match_to_end'}                # blocks that end closer to the page end than an encoder may


def some_pages(n=40, seed=7):
    """A mix: random, constant, short alphabets, repeats of every period, and the vector pages."""
    r = random.Random(seed)
    out = [p for _, _, p in vectors.encode_vectors()]
    for i in range(n):
        kind = i % 4
        if kind == 0:
            out.append(r.randbytes(PAGE))
        elif kind == 1:
            out.append(bytes(r.choice(b'abcd') for _ in range(PAGE)))
        elif kind == 2:
            unit = r.randbytes(r.randint(1, 300))
            out.append((unit * (PAGE // len(unit) + 1))[:PAGE])
        else:
            out.append(b''.join(r.choice((b'alpha', b'beta ', b'\0\0\0\0', r.randbytes(3))) for _ in range(1400))[:PAGE])
    return out


# ---------------------------------------------------------------- the core
def test_encoder_output_is_a_plain_lz4_block():
    for p in some_pages():
        e = C.encode(p)
        assert lz4.block.decompress(e.stream, uncompressed_size=PAGE) == p
        d = C.decode(e.stream)
        assert d.status == C.OK and d.page == p and d.seqs == e.seqs
        assert sum(ll + ml for ll, ml, _ in e.seqs) == PAGE


def test_encoder_keeps_the_rules_of_the_format():
    for p in some_pages():
        e = C.encode(p)
        pos = 0
        for ll, ml, off in e.seqs[:-1]:
            pos += ll
            assert ml >= C.MINMATCH and 1 <= off <= pos
            assert pos <= PAGE - C.MFLIMIT and pos + ml <= PAGE - C.LASTLITERALS
            pos += ml
        assert e.seqs[-1][1] == 0 and e.seqs[-1][0] >= C.LASTLITERALS


def test_decoder_opens_what_liblz4_writes():
    for p in some_pages(20):
        for kw in (dict(), dict(mode='high_compression', compression=9)):
            s = lz4.block.compress(p, store_size=False, **kw)
            d = C.decode(s)
            assert d.status == C.OK and d.page == p


def test_decoder_never_raises_and_never_overruns():
    r = random.Random(3)
    good = C.encode(vectors.words_page()).stream
    streams = [r.randbytes(r.randint(1, PAGE)) for _ in range(200)]
    for _ in range(400):
        s = bytearray(good)
        how = r.randrange(3)
        if how == 0:
            s[r.randrange(len(s))] ^= 1 << r.randrange(8)
        elif how == 1:
            del s[r.randrange(1, len(s)):]
        else:
            s += r.randbytes(r.randint(1, 9))
        streams.append(bytes(s))
    for s in streams:
        d = C.decode(s)
        assert d.produced <= PAGE and d.at <= len(s)
        if d.status == C.OK:
            assert len(d.page) == PAGE and d.at == len(s)
        else:
            assert d.page is None and d.status in C.DECODE_ERRORS


def test_crc_is_the_zlib_one():
    assert C.crc32(b'123456789') == 0xCBF43926


def test_hash_folds_the_word():
    v = 0xDEADBEEF
    assert C.hash4(v, 10) == (v & 0x3FF) ^ ((v >> 10) & 0x3FF) ^ ((v >> 20) & 0x3FF) ^ (v >> 30)
    assert all(C.hash4(random.Random(i).getrandbits(32), b) < (1 << b) for i in range(50) for b in (10, 11, 12))


def test_study_variant_with_defaults_is_the_hardware_encoder():
    for p in some_pages(12):
        v, e = study.encode_variant(p), C.encode(p)
        assert v.stream == e.stream and v.seqs == e.seqs and v.searched == e.searched


def test_cycle_estimates_add_up():
    x = doc.example()
    c_rows, d_rows, after = doc.phases(x)
    comp, behind, store_after = study.job_cycles(x['e'])[:3]
    assert sum(r[2] for r in c_rows) == comp and sum(r[2] for r in d_rows) == behind and after == store_after


# ---------------------------------------------------------------- the vectors
def test_encode_vectors_keep_their_property():
    v = {n: C.encode(p) for n, _, p in vectors.encode_vectors()}
    assert len(v) == len(vectors.encode_vectors())
    for ll in vectors.LIT:
        if ll:
            assert v[f'lit_{ll}'].seqs[0][0] == ll and v[f'lit_{ll}'].seqs[0][1]
        else:                                                  # a match with no literal in front of it
            assert any(l == 0 and m for l, m, _ in v['lit_0'].seqs[1:])
    for ml in vectors.MATCH:
        assert any(m == ml for _, m, _ in v[f'match_{ml}'].seqs)
    for off in vectors.OFFSET:
        assert any(o == off for _, m, o in v[f'offset_{off}'].seqs if m)
    for n in vectors.LENGTH:
        assert len(v[f'len_{n}'].stream) == n
    z = v['zeros']
    assert z.seqs[0][1] == PAGE - C.LASTLITERALS - z.seqs[0][0] and len(z.stream) == 26
    assert len(v['random'].stream) > PAGE and len(v['random'].seqs) == 1


def test_decode_and_bad_stream_vectors():
    for name, _, stream, page in vectors.decode_vectors():
        assert C.decode(stream).page == page, name
        if name in LOOSE:                                      # liblz4 holds the decoder to the end rules of the encoder
            with pytest.raises(lz4.block.LZ4BlockError):
                lz4.block.decompress(stream, uncompressed_size=PAGE)
        else:
            assert lz4.block.decompress(stream, uncompressed_size=PAGE) == page, name
    seen = set()
    for name, _, stream, why in vectors.bad_streams():
        assert C.decode(stream).status == why, name
        seen.add(why)
    assert seen == set(C.DECODE_ERRORS)


def replay(v):
    mem = J.Mem()
    for b in v['mem_before']:
        mem.poke(b['pa'], bytes.fromhex(b['hex']))
    mem.bad = set(v['bus_error_at'])
    r = v['regs']
    regs = J.Regs(r['POOL_BASE'], r['POOL_CHUNKS'], r['FRAME_BASE'], r['FRAME_COUNT'])
    return mem, regs, J.run(bytes.fromhex(v['desc']), regs, mem)


def test_job_vectors_replay_and_stay_inside_what_is_allowed():
    names = set()
    for v in vectors.job_vectors():
        names.add(v['name'])
        mem, regs, res = replay(v)
        assert res.raw.hex() == v['completion'], v['name']
        for m in v['mem_after']:
            assert mem.peek(m['pa'], len(m['hex']) // 2).hex() == m['hex'], v['name']
        ok = [(a['kind'], a['pa'], a['pa'] + a['bytes']) for a in v['allowed']]
        for kind, pa, n in mem.log:
            assert any(k == kind and lo <= pa and pa + n <= hi for k, lo, hi in ok), (v['name'], kind, hex(pa))
        if v['status'] == 'BAD_DESC':
            assert not mem.log and not v['allowed']
        c = v['completion_fields']
        assert c['tag'] == v['desc_fields']['tag']
        if v['status'] != 'OK':
            assert c['length'] == c['checksum'] == c['flags'] == 0
    assert len(names) == len(vectors.job_vectors())
    status = {v['status'] for v in vectors.job_vectors()}
    assert status == {'OK', 'INCOMPRESSIBLE', 'BAD_STREAM', 'BUS_ERROR', 'BAD_DESC'}
    aux = {v['completion_fields']['aux'] for v in vectors.job_vectors() if v['status'] == 'BAD_DESC'}
    assert aux == set(SPEC.enum_name['bad_desc'])


def test_compress_then_decompress_through_jobs():
    regs = vectors.REGS
    for i, p in enumerate(some_pages(16)):
        mem = J.Mem()
        mem.poke(0x97A1C000, p)
        chunks = tuple(0x100 + 3 * k for k in range(8))
        res = J.run(SPEC.pack('job_desc', vectors.desc(OP.COMPRESS, chunks=chunks, limit=PAGE, tag=i)), regs, mem)
        c = res.completion
        assert c['status'] == ST.OK and (c['flags'] == FL.RAW) == (len(C.encode(p).stream) >= PAGE)
        used = chunks[:ceil(c['length'] / 512)]
        d = vectors.desc(OP.DECOMPRESS, frame=0x97A1D000, chunks=used, comp_len=c['length'], checksum=c['checksum'],
                         flags=c['flags'], tag=i)
        res2 = J.run(SPEC.pack('job_desc', d), regs, mem)
        assert res2.completion['status'] == ST.OK and mem.peek(0x97A1D000, PAGE) == p
        assert mem.peek(0x97A1C000, PAGE) == p


class _Dram:
    """The memory of hwref.job behind the read and write calls of the host simulation's hardware."""

    def __init__(self, mem):
        self.mem = mem

    def read(self, pa, n):
        return self.mem.peek(pa, n)

    def write(self, pa, data):
        self.mem.poke(pa, data)


def test_job_model_agrees_with_the_host_simulation_hardware():
    """Two models written separately give the same completion and the same defined memory."""
    for v in vectors.job_vectors():
        if v['status'] == 'BUS_ERROR':
            continue                                           # the host simulation has no bus errors
        mem, regs, res = replay(v)
        other = J.Mem()
        for b in v['mem_before']:
            other.poke(b['pa'], bytes.fromhex(b['hex']))
        cfg = SimpleNamespace(page=PAGE, chunk=512, pool_chunks=regs.pool_chunks, fc_base=regs.frame_base,
                              frames=regs.frame_count, chunk_pa=regs.chunk_pa)
        hw = Lz4Hw(SPEC, cfg, _Dram(other), codec.make('hw'))
        assert hw.run(bytes.fromhex(v['desc'])).hex() == res.raw.hex(), v['name']
        for pa, n in res.defined:
            assert other.peek(pa, n) == mem.peek(pa, n), v['name']


# ---------------------------------------------------------------- the example and the document
def test_interface_example_is_the_real_job():
    e = C.encode(vectors.records_page())
    assert len(e.stream) == 1837 and C.crc32(e.stream) == 0xF7AD14BD
    assert e.seqs[0] == (24, 4, 12) and e.seqs[-1] == (5, 0, 0) and len(e.seqs) == 351 and e.searched == 1115
    name, vals = gen.EX['compress_cpl']
    assert vals['length'] == len(e.stream) and vals['checksum'] == C.crc32(e.stream)
    x = doc.example()
    assert x['res'].completion['length'] == 1837 and x['res2'].completion['status'] == ST.OK
    assert x['mem2'].peek(x['d2']['frame_pa'], PAGE) == vectors.records_page()


def test_document_is_up_to_date():
    """spec/lz4-hw-design-spec-v0.md is generated from the stored numbers and today's models."""
    with open(os.path.join(doc.SPEC_DIR, doc.NUMBERS), encoding='utf-8') as f:
        nums = json.load(f)
    text = doc.render(nums)
    assert '{{' not in text
    with open(os.path.join(doc.SPEC_DIR, doc.DOC), encoding='utf-8') as f:
        assert f.read() == text, 'run: python3 sim/run_hwref.py gen-doc --reuse'
    for name in doc.SHOWN:
        assert f'def {name}(' in text
    for rule in SPEC.rules:
        if rule.startswith('HW-'):
            assert rule in doc.HW_RULES and f'`{rule}`' in text


def test_stored_numbers_hold_together():
    with open(os.path.join(doc.SPEC_DIR, doc.NUMBERS), encoding='utf-8') as f:
        nums = json.load(f)
    assert set(nums['sets']) == {'heap', 'text', 'binaries', 'synthetic'}
    for s in nums['sets'].values():
        assert len(s['rows']) == len(study.VARIANTS) + 2
        for row in s['rows']:
            assert 0 < row['mean_len'] <= PAGE + 32 and 1 <= row['mean_chunks'] <= 8
        cy = s['cycles']
        assert cy['decompress_job']['mean'] < cy['decompress_job_store_after']['mean']


def test_vector_files(tmp_path):
    n = vectors.write(str(tmp_path))
    assert n == {'encode': len(vectors.encode_vectors()), 'decode_only': len(vectors.decode_vectors()),
                 'decode_bad': len(vectors.bad_streams()), 'jobs': len(vectors.job_vectors())}
    with open(tmp_path / 'core' / 'example.stream.hex') as f:
        assert bytes(int(x, 16) for x in f.read().split()) == C.encode(vectors.records_page()).stream
    with open(tmp_path / 'index.json') as f:
        assert json.load(f)['interface_version'] == SPEC.version
