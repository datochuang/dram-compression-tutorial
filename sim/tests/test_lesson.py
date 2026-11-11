import json
import re
from math import ceil

import pytest

from lz4sim.config import SMALL
from lz4sim.formats import (BaselineDesc, COTEntry, Completion, OP_COMPRESS, OP_DECOMPRESS, OP_INVALIDATE,
                            ST_OK, VariantDesc)
from lz4sim.lesson import SCENES, capture, render

WL = dict(hot_ro_pages=100, hot_rw_pages=200)


@pytest.fixture(scope='module')
def data():
    return capture('compress-hw', SMALL, seed=1, accesses=3000, workload=WL)


def test_capture_is_one_consistent_job(data):
    d, c, s = data['desc'], data['cot'], data['done']
    desc = BaselineDesc.unpack(bytes.fromhex(d['hex']))
    assert desc.opcode == OP_COMPRESS and desc.handle == data['victim']['h'] == desc.tag
    assert desc.frame_pa == data['victim']['frame_pa'] == SMALL.frame_pa(data['victim']['frame'])
    assert not any(bytes.fromhex(c['before']))                      # the entry starts empty
    e = COTEntry.unpack(bytes.fromhex(c['after']))
    assert e.count == c['count'] == ceil(c['comp_len'] / SMALL.chunk) == len(data['chunks'])
    assert list(e.chunks) == c['chunks'] == [x['n'] for x in data['chunks']]
    assert data['stack']['top'][:e.count] == c['chunks']            # chunks come off the top of the stack
    assert data['stack']['size_before'] - data['stack']['size_after'] == e.count
    comp = Completion.unpack(bytes.fromhex(s['hex']))
    assert comp.status == ST_OK and comp.tag == desc.tag
    assert comp.length == e.comp_len == data['stream']['len'] == sum(data['stream']['sizes'])
    assert comp.checksum == e.checksum
    assert s['lat_ns'] == s['dram_accesses'] * SMALL.dram_ns + data['meta']['comp_ns']
    assert data['frames']['free_after'] == data['frames']['free_before'] + 1
    assert data['victim']['entry_pa'] == SMALL.cot_base + 32 * data['victim']['h']


def test_capture_is_deterministic(data):
    again = capture('compress-hw', SMALL, seed=1, accesses=3000, workload=WL)
    assert json.dumps(again, sort_keys=True) == json.dumps(data, sort_keys=True)


def test_unknown_scene():
    with pytest.raises(ValueError):
        capture('no-such-scene', SMALL, 1, 100, WL)


def test_page_embeds_data_and_scripts(data):
    html = render(data)
    assert html.startswith('<!doctype html>')
    m = re.search(r'<script type="application/json" id="lesson-data">(.*?)</script>', html, re.S)
    assert json.loads(m.group(1).replace('<\\/', '</')) == json.loads(json.dumps(data))
    assert f'<title>{SCENES["compress-hw"][2]}</title>' in html
    assert 'R.chars' in html and 'R.Lesson' in html and 'R.lesson = lesson' in html
    frag = render(data, fragment=True)
    assert '<!doctype' not in frag and '<body' not in frag and '<title>' in frag


@pytest.fixture(scope='module')
def dec():
    return capture('decompress-hw', SMALL, seed=1, accesses=3000, workload=WL)


def test_decompress_capture_is_one_fault_with_two_jobs(dec):
    pg, c, m = dec['pg'], dec['cot'], dec['meta']
    d1 = BaselineDesc.unpack(bytes.fromhex(dec['desc']['hex']))
    d2 = BaselineDesc.unpack(bytes.fromhex(dec['desc2']['hex']))
    assert (d1.opcode, d2.opcode) == (OP_DECOMPRESS, OP_INVALIDATE)
    assert d1.handle == d2.handle == d1.tag == d2.tag == pg['h'] == dec['req']['h']
    assert d1.limit == SMALL.page and d1.frame_pa == pg['frame_pa'] == SMALL.frame_pa(pg['frame'])
    assert d2.frame_pa == 0 and d2.limit == 0
    c1 = Completion.unpack(bytes.fromhex(dec['done']['hex']))
    c2 = Completion.unpack(bytes.fromhex(dec['done2']['hex']))
    assert c1.status == c2.status == ST_OK and c1.tag == c2.tag == pg['h']
    assert c1.length == SMALL.page and c1.checksum == c['checksum']  # the checksum of the stream, as in the COT
    assert c2.length == 0 and c2.checksum == 0
    # job 1 misses the CTLB (descriptor, COT, frame, completion); job 2 hits it (descriptor, COT, completion)
    assert dec['ctlb'] == {'hit1': False, 'hit2': True}
    assert dec['done']['lat_ns'] == 4 * SMALL.dram_ns + m['decomp_ns']
    assert dec['done2']['lat_ns'] == 3 * SMALL.dram_ns
    assert dec['req']['kernel_ns'] == SMALL.kernel_fault_ns
    assert dec['req']['lat_ns'] == SMALL.kernel_fault_ns + dec['done']['lat_ns'] + dec['done2']['lat_ns']
    e = COTEntry.unpack(bytes.fromhex(c['before']))
    assert e.count == c['count'] == ceil(c['comp_len'] / SMALL.chunk) == len(dec['chunks'])
    assert list(e.chunks) == c['chunks'] == [x['n'] for x in dec['chunks']]
    assert e.checksum == c['checksum'] and e.comp_len == dec['stream']['len'] == sum(dec['stream']['sizes'])
    assert not any(bytes.fromhex(c['after']))                       # the entry ends empty
    st = dec['stack']
    assert st['size_after'] - st['size_before'] == e.count
    assert st['top'][:e.count] == c['chunks'][::-1]                 # pushed in COT order, so the last is on top
    assert dec['frames']['free_after'] == dec['frames']['free_before'] - 1
    assert pg['entry_pa'] == SMALL.cot_base + 32 * pg['h']
    assert [x['pa'] for x in dec['chunks']] == [SMALL.pool_base + x['n'] * SMALL.chunk for x in dec['chunks']]


def test_decompress_is_the_way_back_of_the_compress_lesson(data, dec):
    assert dec['pg']['h'] == data['victim']['h']
    assert dec['cot']['before'] == data['cot']['after']             # nothing touched the entry in between
    assert dec['cot']['after'] == data['cot']['before']
    assert dec['before']['frame'] == data['victim']['frame'] != dec['pg']['frame']
    assert dec['stream']['len'] == data['stream']['len']
    assert [x['n'] for x in dec['chunks']] == [x['n'] for x in data['chunks']]
    assert dec['req']['access_no'] - dec['before']['access_no'] == dec['before']['accesses_ago'] > 0


def test_decompress_capture_is_deterministic(dec):
    again = capture('decompress-hw', SMALL, seed=1, accesses=3000, workload=WL)
    assert json.dumps(again, sort_keys=True) == json.dumps(dec, sort_keys=True)


def test_decompress_page_renders(dec):
    html = render(dec)
    assert html.startswith('<!doctype html>')
    m = re.search(r'<script type="application/json" id="lesson-data">(.*?)</script>', html, re.S)
    assert json.loads(m.group(1).replace('<\\/', '</')) == json.loads(json.dumps(dec))
    assert f'<title>{SCENES["decompress-hw"][2]}</title>' in html
    assert SCENES['decompress-hw'][2] == 'LZ4 Lesson Decompress HW'
    assert 'R.chars' in html and 'R.Lesson' in html and 'R.lesson = lesson' in html
    frag = render(dec, fragment=True)
    assert '<!doctype' not in frag and '<body' not in frag and '<title>' in frag


# ---- the software-leaning lessons

def _bits(word_hex):
    w = int(word_hex, 16)
    return {i for i in range(64) if (w >> i) & 1}


@pytest.fixture(scope='module')
def csw():
    return capture('compress-sw', SMALL, seed=1, accesses=3000, workload=WL)


@pytest.fixture(scope='module')
def dsw():
    return capture('decompress-sw', SMALL, seed=1, accesses=3000, workload=WL)


def test_sw_compress_capture_is_one_consistent_job(csw):
    v, d, c, s, bm, m = csw['victim'], csw['desc'], csw['cot'], csw['done'], csw['bitmap'], csw['meta']
    raw = bytes.fromhex(d['hex'])
    assert len(raw) == VariantDesc.SIZE == 48
    desc = VariantDesc.unpack(raw)
    assert desc.opcode == OP_COMPRESS and desc.tag == v['h']
    assert desc.frame_pa == v['frame_pa'] == SMALL.frame_pa(v['frame'])
    assert desc.limit == m['limit'] and (desc.comp_len, desc.flags, desc.checksum) == (0, 0, 0)
    # the kernel reserves for the worst page still worth storing and names those chunks on the descriptor
    assert bm['need'] == ceil(m['limit'] / SMALL.chunk) == desc.count == len(csw['tiles'])
    assert list(desc.chunks) == bm['reserved_chunks'] == [t['n'] for t in csw['tiles']]
    assert not any(raw[20 + 3 * desc.count:])                       # unused slots and the pad are zero
    comp = Completion.unpack(bytes.fromhex(s['hex']))
    assert comp.status == ST_OK and comp.tag == desc.tag
    assert comp.length == csw['stream']['len'] == sum(csw['stream']['sizes'])
    # the job never touches the COT: descriptor, frame, completion
    assert s['dram_accesses'] == 3 and s['lat_ns'] == 3 * SMALL.dram_ns + m['comp_ns']
    # the entry is the kernel's: completion values plus the first `used` chunks it offered
    assert not any(bytes.fromhex(c['before']))
    e = COTEntry.unpack(bytes.fromhex(c['after']))
    used = ceil(comp.length / SMALL.chunk)
    assert e.count == c['count'] == used == len(csw['chunks']) < bm['need']
    assert (e.comp_len, e.checksum) == (comp.length, comp.checksum)
    assert list(e.chunks) == c['chunks'] == bm['reserved_chunks'][:used] == [x['n'] for x in csw['chunks']]
    assert bm['trimmed'] == bm['reserved_chunks'][used:]
    assert [t['pa'] for t in csw['tiles']] == [SMALL.pool_base + t['n'] * SMALL.chunk for t in csw['tiles']]
    assert [t['bytes'] for t in csw['tiles']] == csw['stream']['sizes'] + [0] * len(bm['trimmed'])
    assert csw['frames']['free_after'] == csw['frames']['free_before'] + 1
    assert v['entry_pa'] == SMALL.cot_base + 32 * v['h']


def test_sw_compress_bitmap_word(csw):
    bm = csw['bitmap']
    base = bm['first_chunk']
    assert base == bm['word'] * 64 and bm['nwords'] * 64 == SMALL.pool_chunks
    assert all(n >> 6 == bm['word'] for n in bm['reserved_chunks'])  # the lesson shows one word
    before, held, after = _bits(bm['before']), _bits(bm['reserved']), _bits(bm['after'])
    assert held - before == {n - base for n in bm['reserved_chunks']} and before <= held
    assert held - after == {n - base for n in bm['trimmed']} and after <= held
    assert after - before == {n - base for n in csw['cot']['chunks']}
    assert bm['free_before'] - bm['free_reserved'] == bm['need']
    assert bm['free_after'] - bm['free_reserved'] == len(bm['trimmed'])
    assert bm['cursor_before'] == bm['word'] and bm['scanned'] == 1


def test_sw_lessons_follow_the_hw_lessons(data, dec, csw, dsw):
    # same access, same page: the two designs can be compared number by number
    assert csw['hw']['same'] and dsw['hw']['same']
    assert (csw['victim']['h'], csw['req']['access_no']) == (data['victim']['h'], data['req']['access_no'])
    assert (dsw['pg']['h'], dsw['req']['access_no']) == (dec['pg']['h'], dec['req']['access_no'])
    assert csw['stream']['len'] == data['stream']['len'] and csw['page'] == data['page']
    assert csw['hw']['chunks'] == data['cot']['chunks'] and csw['hw']['desc_bytes'] == 16
    assert csw['hw']['lat_ns'] == data['done']['lat_ns'] and csw['hw']['dram_accesses'] == data['done']['dram_accesses'] == 4
    assert dsw['hw']['jobs'] == 2 and dsw['hw']['access_ns'] == dec['req']['lat_ns']
    assert dsw['hw']['lat_ns'] == dec['done']['lat_ns'] and dsw['hw']['lat2_ns'] == dec['done2']['lat_ns']


def test_sw_decompress_capture_is_one_fault_with_one_job(dsw):
    pg, d, c, s, bm, m = dsw['pg'], dsw['desc'], dsw['cot'], dsw['done'], dsw['bitmap'], dsw['meta']
    e = COTEntry.unpack(bytes.fromhex(c['before']))
    desc = VariantDesc.unpack(bytes.fromhex(d['hex']))
    assert desc.opcode == OP_DECOMPRESS and desc.tag == pg['h'] == dsw['req']['h']
    assert desc.limit == SMALL.page and desc.frame_pa == pg['frame_pa'] == SMALL.frame_pa(pg['frame'])
    # everything LZ4 HW needs comes from the entry the kernel read
    assert list(desc.chunks) == list(e.chunks) == c['chunks'] == [x['n'] for x in dsw['chunks']]
    assert (desc.comp_len, desc.checksum, desc.flags) == (e.comp_len, e.checksum, 0)
    assert e.count == ceil(e.comp_len / SMALL.chunk) and e.comp_len == dsw['stream']['len'] == sum(dsw['stream']['sizes'])
    comp = Completion.unpack(bytes.fromhex(s['hex']))
    assert comp.status == ST_OK and comp.tag == pg['h'] and comp.length == SMALL.page and comp.checksum == e.checksum
    assert s['dram_accesses'] == 3 and s['lat_ns'] == 3 * SMALL.dram_ns + m['decomp_ns']
    assert dsw['req']['lat_ns'] == SMALL.kernel_fault_ns + s['lat_ns'] + SMALL.kernel_job_ns
    assert not any(bytes.fromhex(c['after']))                       # the kernel empties the entry itself
    base = bm['first_chunk']
    assert _bits(bm['before']) - _bits(bm['after']) == {n - base for n in bm['released']}
    assert _bits(bm['after']) <= _bits(bm['before']) and bm['released'] == c['chunks']
    assert bm['free_after'] - bm['free_before'] == e.count
    assert dsw['frames']['free_after'] == dsw['frames']['free_before'] - 1


def test_sw_decompress_is_the_way_back_of_the_sw_compress_lesson(csw, dsw):
    assert dsw['pg']['h'] == csw['victim']['h']
    assert dsw['cot']['before'] == csw['cot']['after'] and dsw['cot']['after'] == csw['cot']['before']
    assert dsw['before']['frame'] == csw['victim']['frame'] != dsw['pg']['frame']
    assert dsw['before']['access_no'] == csw['req']['access_no']
    assert dsw['stream'] == csw['stream'] and dsw['page'] == csw['page']
    assert dsw['req']['access_no'] - dsw['before']['access_no'] == dsw['before']['accesses_ago'] > 0


def test_sw_captures_are_deterministic(csw, dsw):
    for scene, d in (('compress-sw', csw), ('decompress-sw', dsw)):
        again = capture(scene, SMALL, seed=1, accesses=3000, workload=WL)
        assert json.dumps(again, sort_keys=True) == json.dumps(d, sort_keys=True)


def test_scenes_share_the_stage_files():
    for scene, (variant, files, title) in SCENES.items():
        assert files[:2] == ('kit.js', 'stage_base.js')              # common parts exist once
        assert files[2] == ('stage_sw.js' if variant == 'software' else 'stage_hw.js')
        assert files[3] == scene.replace('-', '_') + '_steps.js' and len(files) == 4
        assert len(title.split()) == 4


def _renders(scene, d):
    html = render(d)
    assert html.startswith('<!doctype html>')
    m = re.search(r'<script type="application/json" id="lesson-data">(.*?)</script>', html, re.S)
    assert json.loads(m.group(1).replace('<\\/', '</')) == json.loads(json.dumps(d))
    assert f'<title>{SCENES[scene][2]}</title>' in html
    assert 'R.stage = function' in html and 'FREE-CHUNK BITMAP' in html and 'SW-LEANING DESIGN' in html
    assert 'FREE-CHUNK STACK' not in html                           # the stack belongs to the other design
    assert 'R.chars' in html and 'R.Lesson' in html and 'R.lesson = lesson' in html
    frag = render(d, fragment=True)
    assert '<!doctype' not in frag and '<body' not in frag and '<title>' in frag


def test_sw_compress_page_renders(csw):
    _renders('compress-sw', csw)


def test_sw_decompress_page_renders(dsw):
    _renders('decompress-sw', dsw)
