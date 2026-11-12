"""Host simulation: the control procedures of hostsim/kernel.py, run in one thread without time."""
import hashlib
import inspect
import json
import os
import shutil

import pytest

from hostsim import codec, conc, doc, walk
from hostsim import kernel as kernel_mod
from hostsim import report as R
from hostsim.check import AuditError, audit
from hostsim.cache import CacheError
from hostsim.kernel import COMPRESSED, LOST, PRESENT, UNTOUCHED, FaultNotAllowed, KernelBug, OutOfMemory
from hostsim.machine import DataMismatch, Machine, NoProgress, make
from ifsim.spec import SPEC
from lz4sim.config import SMALL

HOT = dict(hot_ro_pages=100, hot_rw_pages=200)
HARD = dict(HOT, rw_ratio=0.9, rw_sd=0.05)                 # RW data that barely compresses


def booted(**kw):
    m = Machine('small', **kw)
    m.build_image()
    m.boot()
    return m


@pytest.fixture(scope='module')
def ran():
    """One finished small run. Tests that damage a machine build their own."""
    return make('small')


def stored_rw(m):
    return next(h for h in range(m.cfg.rw_pages) if m.kernel.state[h] == COMPRESSED)


def entry(m, h):
    return SPEC.unpack('cot_entry', m.dram.view(m.cfg.entry_pa(h), 32))


# ---------------------------------------------------------------- the run as a whole
def test_small_run_is_correct_at_every_audit():
    m = booted()
    m.run(6000, check_every=500)
    a = audit(m)
    assert sum(m.st[k] for k in R.KINDS) == m.accesses == 6000
    assert a['frames_held'] + a['frames_free'] == m.cfg.frames
    assert a['chunks_listed'] + a['chunks_free'] == m.cfg.pool_chunks
    assert a['streams_checked'] > m.cfg.ro_pages // 2


def test_every_kind_of_event_happens(ran):
    for kind in ('hit', 'first_touch', 'fault_ro', 'fault_rw'):
        assert ran.st[kind] > 0, kind
    k = ran.kernel.st
    assert k['reclaim'] and k['evict_ro'] and k['evict_rw']
    assert ran.hw.st['COMPRESS_INCOMPRESSIBLE'] == len(ran.kernel.incompressible) > 0
    assert ran.st['refaults'] == 0


def test_jobs_add_up(ran):
    """Every fault on a stored page is one DECOMPRESS, every RW eviction one COMPRESS."""
    hw, k = ran.hw.st, ran.kernel.st
    assert hw['DECOMPRESS_OK'] == ran.st['fault_ro'] + ran.st['fault_rw']
    assert hw['COMPRESS_OK'] + hw['COMPRESS_INCOMPRESSIBLE'] == k['evict_rw'] - k['pool_full']
    assert ran.port.st['tlb_flushes'] == k['evict_ro'] + k['evict_rw'] - k['pool_full']


def test_same_seed_same_machine():
    a, b = make('small', n=3000), make('small', n=3000)
    assert R.metrics(a) == R.metrics(b)
    assert bytes(a.dram.view(a.cfg.cot_base, 32 * a.cfg.pages)) == bytes(b.dram.view(b.cfg.cot_base, 32 * b.cfg.pages))


def test_ideal_lru_needs_fewer_jobs_than_clock(ran):
    lru = make('small', policy='lru')
    audit(lru)
    assert lru.hw.st['jobs'] < ran.hw.st['jobs']


# ------------------------------------------------------------------------ the codec
def test_lz4_tool_gives_the_same_blocks_as_the_library():
    if not shutil.which('lz4'):
        pytest.skip('the lz4 command-line tool is not installed')
    lib, cli = codec.LibCodec(), codec.CliCodec()
    m = Machine('small')
    pages = [m.wl.ro_page() for _ in range(6)] + [m.wl.rw_page() for _ in range(6)] + [bytes(4096), os.urandom(4096)]
    for page in pages:
        a, b = lib.compress(page), cli.compress(page)
        assert a == b
        if a is not None:
            assert cli.decompress(a) == lib.decompress(a) == bytes(page)
            bad = bytes([a[0] ^ 0xFF]) + a[1:]
            assert (cli.decompress(bad) == bytes(page)) == (lib.decompress(bad) == bytes(page))
    assert lib.compress(os.urandom(4096)) is None


def test_machine_is_the_same_with_either_codec():
    if not shutil.which('lz4'):
        pytest.skip('the lz4 command-line tool is not installed')
    a, b = make('small', n=600), make('small', n=600, codec='cli')
    assert b.codec.calls > b.cfg.ro_pages
    xa, xb = R.metrics(a), R.metrics(b)
    assert xa.pop('codec') == 'lib' and xb.pop('codec') == 'cli'
    assert xa == xb
    assert bytes(a.dram.view(a.cfg.cot_base, 32 * a.cfg.pages)) == bytes(b.dram.view(b.cfg.cot_base, 32 * b.cfg.pages))
    audit(b)


# ------------------------------------------------------------------ damaged streams
def test_damaged_stream_ends_as_a_lost_page_and_nothing_else():
    m = booted(seed=3, corrupt_every=200)
    m.run(8000)
    assert m.st['injected'] > 0 and m.st['lost'] > 0
    assert m.hw.st['DECOMPRESS_BAD_STREAM'] > 0
    lost = [h for h in range(m.cfg.pages) if m.kernel.state[h] == LOST]
    assert lost and set(lost) <= m.corrupted
    for h in lost:
        assert m.kernel.frame_of[h] < 0 and not m.port.pte[h]
    audit(m)                                               # every other page is still right
    k = m.kernel.st
    assert k['sw_decode'] == m.hw.st['DECOMPRESS_BAD_STREAM'] and k['sw_decode_ok'] == 0   # asked twice, lost once
    assert not m.kernel.lz4_off and m.kernel.strikes == 0  # the LZ4 HW was right: nothing is held against it


# ------------------------------------------------- the LZ4 HW answers wrongly, or not at all
@pytest.mark.parametrize('mode', ['bus_error', 'bad_stream'])
def test_one_failed_decompress_loses_nothing(mode):
    """The stored stream is intact, so the kernel's own decoder brings the page back."""
    m = booted()
    m.run(3000)
    m.hw.inject('DECOMPRESS', mode)
    m.run(3000)                                            # every page that comes back is compared with what was written
    k = m.kernel.st
    assert m.hw.st['DECOMPRESS_' + mode.upper()] == 1
    assert k['sw_decode'] == k['sw_decode_ok'] == 1
    assert not m.st['lost'] and not any(s == LOST for s in m.kernel.state)
    assert m.kernel.strikes == 0 and not m.kernel.lz4_off  # one wrong answer, then right ones again
    audit(m)


def test_failed_compress_keeps_the_page_and_gives_the_chunks_back():
    m = booted()
    m.run(3000)
    m.hw.inject('COMPRESS', 'bus_error')
    m.run(3000)
    assert m.hw.st['COMPRESS_BUS_ERROR'] == m.kernel.st['compress_failed'] == 1
    assert not m.st['lost']
    audit(m)                                               # A2: no chunk is left reserved, A4: the page is still right


def test_three_wrong_answers_in_a_row_turn_the_lz4_hw_off():
    m = booted()
    m.run(3000)
    for _ in range(kernel_mod.Kernel.STRIKES):
        m.hw.inject('DECOMPRESS', 'bus_error')
    jobs = m.hw.st['jobs']
    with pytest.raises(OutOfMemory):                       # RW pages cannot be stored any more: frames run out
        m.run(6000)
    k = m.kernel
    assert k.lz4_off and k.st['lz4_off'] == 1
    assert m.hw.st['jobs'] == jobs + kernel_mod.Kernel.STRIKES    # not one job more after the third
    assert k.st['sw_decode'] == k.st['sw_decode_ok'] > 100 and not m.st['lost']


def test_lz4_hw_that_stops_answering_is_given_up_at_once():
    m = booted()
    m.run(3000)
    m.hw.down = True
    with pytest.raises(OutOfMemory):
        m.run(6000)
    k = m.kernel
    assert m.hw.st['no_answer'] == 1 and k.lz4_off
    assert k.st['sw_decode'] == k.st['sw_decode_ok'] > 100 and not m.st['lost']


def test_verify_catches_a_stream_of_the_wrong_page_before_the_page_is_given_up():
    m = booted(verify=True)
    m.run(3000)
    m.hw.inject('COMPRESS', 'bad_data')                    # status OK, CRC-32 right, but of a page with one byte flipped
    m.run(3000)
    k = m.kernel.st
    assert k['verify_failed'] == k['compress_failed'] == 1 and k['verified'] == m.hw.st['COMPRESS_OK']
    audit(m)


def test_without_verify_the_same_fault_is_silent_until_the_data_is_compared():
    m = booted()
    m.run(3000)
    m.hw.inject('COMPRESS', 'bad_data')
    with pytest.raises((DataMismatch, AuditError)):
        m.run(6000)
        audit(m)


def test_boot_must_empty_the_caches_of_the_layer():
    m = Machine('small')
    m.build_image()
    m.port.cache_flush_layer = lambda: None
    m.boot()
    with pytest.raises(CacheError, match='C2'):
        m.run(3000)


def test_kernel_must_not_read_a_chunk_through_an_old_cache_line():
    m = booted(verify=True)
    real = m.port.chunk_read
    m.port.chunk_read = lambda c: real(c, fresh=False)
    with pytest.raises(CacheError, match='C3: the CPU reads chunk'):
        m.run(8000)


# -------------------------------------------------------- the audit finds what it should
def test_audit_finds_a_damaged_stored_stream(ran):
    m = make('small', n=4000)
    e = entry(m, stored_rw(m))
    m.dram.view(m.cfg.chunk_pa(e['chunk'][0]), 1)[0] ^= 0x01
    with pytest.raises(AuditError, match='A4'):
        audit(m)


def test_audit_finds_a_listed_chunk_that_was_freed():
    m = make('small', n=4000)
    m.bitmap.release([entry(m, stored_rw(m))['chunk'][0]])
    with pytest.raises(AuditError, match='A2'):
        audit(m)


def test_audit_finds_a_changed_byte_outside_the_compression_layer():
    m = make('small', n=1000)
    m.dram.view(m.cfg.hrt_base + 12345, 1)[0] ^= 0x80
    with pytest.raises(AuditError, match='A5'):
        audit(m)


def test_audit_finds_a_wrong_pte_and_a_wrong_frame():
    m = make('small', n=1000)
    h = next(h for h in range(m.cfg.pages) if m.kernel.state[h] == PRESENT)
    pa, m.port.pte[h] = m.port.pte[h], 0
    with pytest.raises(AuditError, match='A1'):
        audit(m)
    m.port.pte[h] = pa
    audit(m)
    m.dram.view(pa + 100, 1)[0] ^= 0x01                    # a frame that changed behind user SW's back
    with pytest.raises(AuditError, match='A4'):
        audit(m)


def test_audit_finds_a_stale_cot_entry():
    m = make('small', n=4000)
    h = next(h for h in range(m.cfg.rw_pages) if m.kernel.state[h] == PRESENT)
    m.dram.view(m.cfg.entry_pa(h), 1)[0] |= SPEC.enum['flag'].VALID
    with pytest.raises(AuditError, match='A3'):
        audit(m)


# -------------------------------------------------------------------- lock discipline
def test_tables_need_the_lock_and_jobs_must_not_hold_it():
    m = booted()
    with pytest.raises(KernelBug, match='without the lock'):
        m.port.cot_read(0)
    with pytest.raises(KernelBug, match='without the lock'):
        m.port.pte_map(0, m.cfg.frame_pa(0))
    m.port.lock()
    with pytest.raises(KernelBug, match='lock held'):
        m.port.lz4_job(bytes(48))
    with pytest.raises(KernelBug, match='twice'):
        m.port.lock()
    m.port.unlock()
    with pytest.raises(KernelBug):
        m.port.unlock()


def test_kernel_reaches_the_outside_only_through_the_port():
    src = inspect.getsource(kernel_mod)
    for word in ('.dram', 'self.hw', 'import lz4', 'codec', 'machine'):
        assert word not in src, word


def test_kernel_never_leaves_a_procedure_with_the_lock(ran):
    assert not ran.port.locked
    m = booted()
    m.log.sink = []
    m.run(3000)
    depth = 0
    for who, what, v in m.log.sink:
        if what == 'lock':
            depth += 1
        elif what == 'unlock':
            depth -= 1
        elif what == 'job':
            assert depth == 0, 'job handed over with the lock held'
        elif what in ('cot_read', 'cot_write', 'pte_map', 'pte_unmap', 'take_frame', 'put_frame', 'state'):
            assert depth == 1, what
        assert depth in (0, 1)


# ------------------------------------------------------------------------- the LZ4 HW
def test_hw_refuses_descriptors_that_point_outside():
    m = make('small', n=2000)
    cfg, OP, ST, BD = m.cfg, SPEC.enum['opcode'], SPEC.enum['status'], SPEC.enum['bad_desc']
    good = dict(opcode=OP.COMPRESS, count=7, limit=3584, frame_pa=cfg.frame_pa(3), chunk=range(7), tag=0x51)
    cases = [
        (dict(good, opcode=0x7F), BD.OPCODE),
        (dict(good, count=0), BD.COUNT),
        (dict(good, count=9), BD.COUNT),
        (dict(good, chunk=[0, 1, 2, 3, 4, 5, cfg.pool_chunks]), BD.CHUNK_RANGE),
        (dict(good, frame_pa=cfg.frame_pa(3) + 512), BD.FRAME_RANGE),
        (dict(good, frame_pa=cfg.hrt_base), BD.FRAME_RANGE),
        (dict(good, frame_pa=cfg.cot_base), BD.FRAME_RANGE),
        (dict(good, limit=0), BD.LENGTH),
        (dict(good, limit=3585), BD.LENGTH),
        (dict(good, opcode=OP.DECOMPRESS, comp_len=0), BD.LENGTH),
        (dict(good, opcode=OP.DECOMPRESS, comp_len=3585), BD.LENGTH),
        (dict(good, opcode=OP.DECOMPRESS, count=8, chunk=range(8), comp_len=4000, flags=SPEC.enum['flag'].RAW), BD.LENGTH),
    ]
    before = hashlib.blake2b(m.dram.view(cfg.dram_base, cfg.cot_base - cfg.dram_base)).digest()
    for fields, aux in cases:
        cpl = SPEC.unpack('completion', m.hw.run(SPEC.pack('job_desc', fields)))
        assert (cpl['status'], cpl['aux'], cpl['tag']) == (ST.BAD_DESC, aux, 0x51), fields
    assert hashlib.blake2b(m.dram.view(cfg.dram_base, cfg.cot_base - cfg.dram_base)).digest() == before
    audit(m)                                               # a refused job wrote nothing anywhere


def test_hw_leaves_the_frame_alone_when_the_stream_is_bad():
    m = make('small', n=4000)
    cfg, OP, ST = m.cfg, SPEC.enum['opcode'], SPEC.enum['status']
    e = entry(m, stored_rw(m))
    f = m.kernel.free_frames[-1]
    frame = bytes(m.dram.view(cfg.frame_pa(f), cfg.page))
    job = dict(opcode=OP.DECOMPRESS, count=e['count'], limit=cfg.page, frame_pa=cfg.frame_pa(f),
               comp_len=e['comp_len'], checksum=e['checksum'] ^ 1, chunk=e['chunk'][:e['count']], tag=7)
    cpl = SPEC.unpack('completion', m.hw.run(SPEC.pack('job_desc', job)))
    assert cpl['status'] == ST.BAD_STREAM
    assert bytes(m.dram.view(cfg.frame_pa(f), cfg.page)) == frame


# --------------------------------------------------------- at the limits of the memory
def run_hard(n=20000, **kw):
    cfg = SMALL.with_(rw_raw_store=kw.pop('raw', False))
    m = Machine(cfg, workload=kw.pop('workload', HARD), **kw)
    m.build_image()
    m.boot()
    m.run(n)
    return m


def test_without_protection_a_full_machine_spins_on_one_instruction():
    with pytest.raises(NoProgress):
        run_hard(protect=0)


def test_with_protection_a_full_machine_reports_out_of_memory():
    m = Machine(SMALL, workload=HARD)
    m.build_image()
    m.boot()
    with pytest.raises(OutOfMemory):
        m.run(20000)
    assert not m.kernel.free_frames
    assert m.st['refaults'] == 0
    assert m.bitmap.free > m.cfg.pool_chunks // 2          # the chunk pool was more than half empty
    pinned = len(m.kernel.incompressible)
    assert pinned >= m.cfg.frames - 2                      # frames went to pages that cannot leave


def test_raw_store_gets_through_the_same_data():
    m = run_hard(raw=True)
    a = audit(m)
    assert m.accesses == 20000 and not m.kernel.incompressible
    assert m.hw.st['COMPRESS_INCOMPRESSIBLE'] == 0
    FL = SPEC.enum['flag']
    raw = [h for h in range(m.cfg.rw_pages) if m.kernel.state[h] == COMPRESSED and entry(m, h)['flags'] & FL.RAW]
    assert raw and all(entry(m, h)['count'] == 8 for h in raw)
    assert a['streams_checked'] > 0


def test_fresh_page_is_never_the_victim():
    """Between a finished fault and the instruction that caused it, the reclaimer never picks that page."""
    m = booted()
    m.log.sink = []
    m.run(8000)
    entered, fresh, picks = None, None, 0
    for who, what, v in m.log.sink:
        if what == 'enter page_fault':
            entered = v['h']
        elif what == 'leave page_fault':
            fresh = entered
        elif what == 'instruction_runs':
            fresh = None
        elif what == 'pick_victim' and fresh is not None:
            picks += 1
            assert v['h'] != fresh
    assert picks > 100
    assert m.st['refaults'] == 0


def test_refault_without_protection_is_still_correct():
    m = booted(map_accessed=0, protect=0)
    m.run(20000, check_every=5000)
    assert m.st['refaults'] > 0
    audit(m)


# ---------------------------------------------------------------- CPU cache, contexts, pins
def test_compress_without_cache_clean_is_caught():
    """The LZ4 HW would compress what DRAM holds while the CPU's last writes are still in its cache."""
    m = booted()
    m.port.cache_clean = lambda pa: None
    with pytest.raises(CacheError, match='C1'):
        m.run(6000)


def test_decompress_without_cache_invalidate_is_caught():
    """The CPU would read or run a line of the page that had the frame before."""
    m = booted()
    m.port.cache_invalidate = lambda pa: None
    with pytest.raises(CacheError, match='C3'):
        m.run(6000)


def test_cache_calls_come_once_per_job(ran):
    hw, c = ran.hw.st, ran.cache.st
    assert c['clean'] == hw['COMPRESS_OK'] + hw['COMPRESS_INCOMPRESSIBLE'] > 0
    assert c['invalidate'] == hw['DECOMPRESS_OK'] + hw['DECOMPRESS_BAD_STREAM'] > 0


def test_cache_calls_are_made_without_the_lock():
    m = booted()
    held = []
    for name in ('cache_clean', 'cache_invalidate'):
        real = getattr(m.port, name)
        setattr(m.port, name, lambda pa, real=real: (held.append(m.port.locked), real(pa)))
    m.run(4000)
    assert len(held) > 100 and not any(held)


@pytest.mark.parametrize('context', ('isr', 'hrt'))
def test_page_fault_where_nobody_can_wait(context):
    m = booted()
    m.run(3000)
    h = stored_rw(m)
    m.context = context
    with pytest.raises(FaultNotAllowed):
        m.access(h, False)
    assert m.kernel.state[h] == COMPRESSED and not m.port.locked
    m.context = 'thread'
    assert m.access(h, False) == 'fault_rw'
    audit(m)


def test_pinned_pages_are_never_taken():
    m = booted()
    m.run(3000)
    k = m.kernel
    pinned = [h for h in range(m.cfg.pages) if k.state[h] == PRESENT][:40]
    absent = stored_rw(m)
    for h in pinned + [absent]:
        assert k.pin_page(h) == 'pinned'
    assert k.pin_page(absent) == 'pinned'                   # counted: two holders
    frames = {h: k.frame_of[h] for h in pinned + [absent]}
    m.run(6000, check_every=2000)
    assert all(k.state[h] == PRESENT and k.frame_of[h] == f for h, f in frames.items())
    assert audit(m)['pinned'] == len(frames)
    k.unpin_page(absent)
    for h in pinned + [absent]:
        k.unpin_page(h)
    with pytest.raises(KernelBug):
        k.unpin_page(absent)


def test_pin_of_a_lost_page_says_so():
    m = booted()
    m.run(3000)
    h = stored_rw(m)
    m.dram.view(m.cfg.chunk_pa(entry(m, h)['chunk'][0]), 1)[0] ^= 0xFF
    assert m.kernel.pin_page(h) == 'lost'
    assert m.kernel.state[h] == LOST and not m.kernel.pins[h]


# ------------------------------------------------------------------------------- boot
def test_boot_rebuilds_the_bitmap_from_the_cot():
    m = Machine('small')
    used = m.build_image()
    assert m.bitmap.free == m.cfg.pool_chunks              # nothing known before boot
    m.boot()
    k = m.kernel
    assert m.bitmap.free == m.cfg.pool_chunks - used
    assert m.bitmap.cursor == used // 64                   # the search starts behind the RO image
    assert all(k.state[h] == COMPRESSED for h in range(m.cfg.ro_first, m.cfg.pages))
    assert all(k.state[h] == PRESENT for h in range(m.cfg.data_pages))
    assert all(k.state[h] == UNTOUCHED for h in range(m.cfg.data_pages, m.cfg.rw_pages))
    assert len(k.free_frames) == m.cfg.frames - m.cfg.data_pages
    audit(m)
    first = m.bitmap.reserve(7)
    assert min(first) >= used and m.bitmap.scan_max <= 2


def test_ro_image_is_contiguous_and_never_changes(ran):
    m = Machine('small')
    used = m.build_image()
    c = 0
    for h in range(m.cfg.ro_first, m.cfg.pages):
        e = entry(m, h)
        assert e['chunk'][:e['count']] == list(range(c, c + e['count']))
        c += e['count']
    assert c == used
    ro = slice(32 * m.cfg.ro_first, 32 * m.cfg.pages)
    cot = lambda x: bytes(x.dram.view(x.cfg.cot_base, 32 * x.cfg.pages))[ro]
    pool = lambda x: bytes(x.dram.view(x.cfg.chunk_pa(0), used * x.cfg.chunk))
    assert cot(m) == cot(ran) and pool(m) == pool(ran)     # after 20000 accesses the RO part is untouched


# ---------------------------------------------------------- walk-throughs and the document
def test_every_case_has_a_walk_through():
    m, log = walk.capture()
    sc = walk.scenarios(log)
    assert set(sc) == {'first_touch', 'fault_ro', 'fault_rw', 'evict_ro', 'evict_rw_ok',
                       'evict_rw_incompressible', 'reclaim'}
    for name, ev in sc.items():
        text = walk.md_reclaim(ev) if name == 'reclaim' else walk.md(ev)
        assert ('`evict_rw`' if name == 'reclaim' else '| kernel |') in text
    for who, what, v in log:                              # every step that can be logged has a description
        assert (who, what) in walk.STEP or what[:6] in ('enter ', 'leave '), what
    lost = walk.lost_scenario()
    assert lost and 'BAD_STREAM' in walk.md(lost)
    rescued = walk.md(walk.rescued_scenario())
    assert 'BUS_ERROR' in rescued and 'result = decoded' in rescued and 'new = PRESENT' in rescued
    assert rescued.index('result = decoded') < rescued.index('寫回 DRAM') < rescued.index('new = PRESENT')


def test_walk_through_order_follows_the_rules():
    """fault_rw: COT entry cleared, then chunks released, then the PTE. evict_rw: unmap, job, COT, frame."""
    _, log = walk.capture()
    sc = walk.scenarios(log)

    def order(ev, *names):
        seen = [w for _, w, _ in ev if w in names]
        assert seen == list(names), seen

    order(sc['fault_rw'], 'take_frame', 'cot_read', 'job', 'completion', 'cot_write', 'bitmap_release', 'pte_map')
    order(sc['fault_ro'], 'take_frame', 'cot_read', 'job', 'completion', 'pte_map')
    order(sc['first_touch'], 'take_frame', 'zero_frame', 'pte_map')
    order(sc['evict_ro'], 'pick_victim', 'pte_unmap', 'put_frame')
    order(sc['evict_rw_ok'], 'pick_victim', 'bitmap_reserve', 'pte_unmap', 'job', 'completion', 'cot_write',
          'bitmap_trim', 'put_frame')
    order(sc['evict_rw_incompressible'], 'pick_victim', 'bitmap_reserve', 'pte_unmap', 'job', 'completion',
          'bitmap_release', 'pte_map')


def test_document_is_up_to_date():
    """spec/control-procedures-v0.md is generated from the stored numbers and today's kernel source."""
    with open(os.path.join(doc.SPEC_DIR, doc.NUMBERS), encoding='utf-8') as f:
        nums = json.load(f)
    text = doc.render(nums)
    assert '{{' not in text
    with open(os.path.join(doc.SPEC_DIR, doc.DOC), encoding='utf-8') as f:
        assert f.read() == text, 'run: python3 sim/run_host.py gen-doc --reuse'
    for name in doc.SHOWN:
        assert f'def {name}(self' in text


def test_stored_numbers_hold_together():
    with open(os.path.join(doc.SPEC_DIR, doc.NUMBERS), encoding='utf-8') as f:
        nums = json.load(f)
    assert nums['cfg'] == 'full' and len(nums['runs']) == len(doc.RUNS)
    for x in nums['runs']:
        assert sum(x['results'].values()) == x['accesses'] == 400000
        assert x['refaults'] == 0
        assert x['audit']['frames_held'] + x['audit']['frames_free'] == x['frames']
    clock, _, lru = nums['runs']
    assert lru['hw']['jobs'] < clock['hw']['jobs']
    ends = {(r['label'][:3], r['raw'], r['protect']): r['end'] for r in nums['stress']}
    assert ends[('90%', False, 1)] == 'OutOfMemory' and ends[('90%', False, 0)] == 'NoProgress'
    assert ends[('90%', True, 1)] == 'ok'


def test_stored_numbers_of_the_threaded_runs_hold_together():
    with open(os.path.join(doc.SPEC_DIR, doc.NUMBERS), encoding='utf-8') as f:
        c = json.load(f)['conc']
    assert c['survey']['schedules'] == doc.CONC_RUNS and c['damaged']['schedules'] == doc.CONC_DAMAGED
    for path in ('spurious', 'wait_page_compressing', 'wait_page_decompressing', 'wait_frame', 'pin_page'):
        assert c['survey'][path] > 0, path
    assert not c['survey'].get('lost') and c['damaged']['lost'] > 0
    d = c['damaged']                                      # a stream that is really bad: the second opinion agrees
    assert d['DECOMPRESS_BAD_STREAM'] == d['sw_decode'] == d['lost_pages'] > 0 and d.get('sw_decode_ok', 0) == 0
    f, down = c['faulty'], c['down']
    assert f['schedules'] == doc.CONC_FAULTY and down['schedules'] == doc.CONC_DOWN
    for x in (f, down):                                   # a HW that fails on good streams loses no page
        assert x['sw_decode'] == x['sw_decode_ok'] > 0 and not x.get('lost_pages') and not x.get('lost')
    assert f['compress_failed'] == f['COMPRESS_BUS_ERROR'] > 0 and f['threads_ended_killed'] > 0
    assert not f.get('lz4_off') and 0 < down['lz4_off'] <= down['schedules'] and down['no_answer'] >= down['lz4_off']
    assert down['evict_rw'] == down.get('COMPRESS_OK', 0) + down['compress_failed']
    assert [r['name'] for r in c['mutants']] == list(conc.MUTANTS)
    assert all(r['schedule'] is not None for r in c['mutants'])
    assert all(r['schedules'] > 0 for r in c['explore']) and len(c['explore']) == len(conc.EXPLORE)
