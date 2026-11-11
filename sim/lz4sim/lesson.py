"""Lesson exporter: one self-contained HTML page that teaches a single scene.

The replay (replay.py) shows a whole run from far away. A lesson is the opposite:
one job, close up, with every structure the job touches shown byte by byte and
every byte marked with who wrote it and who read it. The numbers are not made up
for the page: the exporter runs the simulator, stops at one real job and records
the bytes before and after.

Scenes so far:

  compress-hw     hardware-leaning design, COMPRESS of one RW page during reclaim
  decompress-hw   hardware-leaning design, the same page later: its owner touches it, the
                  PTE is invalid, DECOMPRESS into a free frame and INVALIDATE of the old copy
  compress-sw     software-leaning design, the same COMPRESS: the kernel reserves chunks in its
                  bitmap, names them in a 48 B descriptor and writes the COT entry itself
  decompress-sw   software-leaning design, the same page later: the kernel reads the COT entry,
                  one DECOMPRESS job, then the kernel clears the entry and the bitmap bits

The software-leaning scenes follow the page the hardware-leaning scenes picked whenever the
software run evicts it at the same access, so the four pages can be read side by side.

The page is plain JavaScript on three.js; its sources are in lesson_assets/. The
characters are the ones the replay uses (replay_assets/chars.js), so KERNEL SW,
LZ4 HW and the user programs look the same in both.
"""
import json
import os
from math import ceil

from .codec import compress, decompress, checksum
from .formats import (COTEntry, BaselineDesc, VariantDesc, Completion, OP_NAME, ST_NAME, OP_COMPRESS,
                      OP_DECOMPRESS, OP_INVALIDATE, ST_OK, EMPTY_ENTRY)
from .kernel import S_UNTOUCHED
from .sim import Simulation

HERE = os.path.dirname(__file__)
ASSETS = os.path.join(HERE, 'lesson_assets')
CHARS = os.path.join(HERE, 'replay_assets', 'chars.js')
THREE_URL = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js'
SCENES = {
    'compress-hw': ('baseline', ('kit.js', 'stage_base.js', 'stage_hw.js', 'compress_hw_steps.js'),
                    'LZ4 Lesson Compress HW'),
    'decompress-hw': ('baseline', ('kit.js', 'stage_base.js', 'stage_hw.js', 'decompress_hw_steps.js'),
                      'LZ4 Lesson Decompress HW'),
    'compress-sw': ('software', ('kit.js', 'stage_base.js', 'stage_sw.js', 'compress_sw_steps.js'),
                    'LZ4 Lesson Compress SW'),
    'decompress-sw': ('software', ('kit.js', 'stage_base.js', 'stage_sw.js', 'decompress_sw_steps.js'),
                      'LZ4 Lesson Decompress SW'),
}
STACK_SHOWN = 8
# decompress-hw follows the page of the compress lesson to its next access, which may come
# long after --accesses; the run goes on for this many more accesses to find it
FOLLOW_MIN, FOLLOW_FACTOR = 20000, 8


def _run_to_candidates(cfg, seed, accesses, workload, extra=0):
    """Run the baseline simulation and snapshot the machine around every RW eviction.

    With extra > 0 the run goes on for that many more accesses and also snapshots every
    fault on a compressed RW page. The access stream does not depend on its length, so
    the first `accesses` accesses are the same run either way.
    """
    sim = Simulation('baseline', cfg, seed, None, 'all', workload, keep_trace=True)
    sim.build()
    sim.boot()
    k, stack, dram = sim.kernel, sim.stack, sim.dram
    cur = {'no': 0, 'req': None}
    cands, faults = [], []
    orig_access, orig_evict, orig_fault = k.access, k._evict_rw, k._fault_in

    def access(h, w):
        cur['req'] = (h, bool(w), k.state[h])
        cur['free0'], cur['n0'] = len(k.free_frames), len(sim.trace.records)
        r = orig_access(h, w)
        cur['no'] += 1
        return r

    def evict(h):
        f = k.frame_of[h]
        snap = {
            'h': h, 'frame': f, 'access_no': cur['no'], 'req': cur['req'],
            'page': bytes(dram.view(cfg.frame_pa(f), cfg.page)),
            'cot_before': bytes(dram.view(cfg.entry_pa(h), 32)),
            'sram_before': list(stack.sram), 'list_chunks': stack.list_chunks, 'list_head': stack.list_head,
            'free_before': len(k.free_frames), 'n0': len(sim.trace.records), 'refills0': stack.st['refills'],
            'jobs_before': sim.accel.st['jobs'], 'lru_len': len(k.lru),
        }
        ok = orig_evict(h)
        snap.update(ok=ok, recs=list(sim.trace.records[snap['n0']:]),
                    cot_after=bytes(dram.view(cfg.entry_pa(h), 32)),
                    sram_after=list(stack.sram), free_after=len(k.free_frames),
                    refilled=stack.st['refills'] != snap['refills0'])
        cands.append(snap)
        return ok

    def fault(h, f):
        if cfg.is_ro(h):
            return orig_fault(h, f)
        entry = COTEntry.unpack(bytes(dram.view(cfg.entry_pa(h), 32)))
        snap = {
            'h': h, 'frame': f, 'access_no': cur['no'], 'w': cur['req'][1], 'free_start': cur['free0'], 'n0': cur['n0'],
            'cot_before': bytes(dram.view(cfg.entry_pa(h), 32)),
            'chunk_bytes': [bytes(dram.view(cfg.chunk_pa(n), cfg.chunk)) for n in entry.chunks],
            'sram_before': list(stack.sram), 'list_chunks': stack.list_chunks,
            'ctlb_hit': sim.accel.ctlb_handle == h, 'events0': stack.dram_events(),
        }
        ok = orig_fault(h, f)
        snap.update(ok=ok, n1=len(sim.trace.records), free_after=len(k.free_frames),
                    cot_after=bytes(dram.view(cfg.entry_pa(h), 32)), sram_after=list(stack.sram),
                    page=bytes(dram.view(cfg.frame_pa(f), cfg.page)),
                    stack_dram=stack.dram_events() != snap['events0'])
        faults.append(snap)
        return ok

    k.access, k._evict_rw = access, evict
    if extra:
        k._fault_in = fault
    sim.run(accesses + extra)
    sim.audit()
    sim.close()
    return sim, cands, faults


def _score(sim, c):
    """Higher is a better teaching example; None means unusable.

    A good example has uneven numbers, a stream scattered over chunks that are not
    neighbours (the reason the COT entry lists every chunk), a visibly partial last
    chunk, a handle that differs from the frame number, and a cause that is easy to
    tell: one program needs a frame, another program's page gets compressed.
    """
    cfg = sim.cfg
    if not c['ok'] or c['refilled'] or any(c['cot_before']):
        return None
    e = COTEntry.unpack(c['cot_after'])
    rh, _, rstate = c['req']
    ch = e.chunks
    run = all(a - b == 1 for a, b in zip(ch, ch[1:])) or all(b - a == 1 for a, b in zip(ch, ch[1:]))
    s = 0
    s += 4 if 3 <= e.count <= 5 else 0
    s += 1 if e.count == 4 else 0
    s += 3 if 40 <= e.comp_len % cfg.chunk <= cfg.chunk - 40 else 0
    s += 5 if not run else 0
    s += 2 if c['h'] >= 0x40 else 0
    s += 2 if sim.wl.owner[c['h']] != sim.wl.owner[rh] else 0
    s += 2 if rstate == S_UNTOUCHED else 0
    s += 3 if c['frame'] != c['h'] else 0                 # a handle is not a frame number
    s += 1 if c['free_before'] == cfg.fc_low else 0
    return s


def capture(scene='compress-hw', cfg=None, seed=1, accesses=3000, workload=None):
    if scene not in SCENES:
        raise ValueError(f'scene must be one of {sorted(SCENES)}')
    if scene == 'decompress-hw':
        return _capture_decompress(cfg, seed, accesses, workload)
    if scene == 'compress-sw':
        return _capture_compress_sw(cfg, seed, accesses, workload)
    if scene == 'decompress-sw':
        return _capture_decompress_sw(cfg, seed, accesses, workload)
    sim, cands, _ = _run_to_candidates(cfg, seed, accesses, workload)
    cfg = sim.cfg
    best = None
    for c in cands:
        sc = _score(sim, c)
        if sc is not None and (best is None or sc > best[0]):
            best = (sc, c)
    if best is None:
        raise SystemExit('--lesson: this run has no COMPRESS job that starts a reclaim and succeeds; '
                         'use more --accesses or another --seed')
    c = best[1]
    h, f = c['h'], c['frame']
    recs = c['recs']
    job = next(r for r in recs if r['ev'] == 'job')
    done = next(r for r in recs if r['ev'] == 'done')
    pop = next(r for r in recs if r['ev'] == 'chunk' and r['op'] == 'pop')
    entry = COTEntry.unpack(c['cot_after'])
    desc = BaselineDesc.unpack(bytes.fromhex(job['hex']))
    comp = Completion.unpack(bytes.fromhex(done['hex']))
    stream = b''.join(bytes(sim.dram.view(cfg.chunk_pa(n), cfg.chunk)) for n in entry.chunks)[:entry.comp_len]
    # the chunks may have been reused by the end of the run; rebuild the stream from the page to be sure
    blob = compress(c['page'])
    if checksum(blob) != entry.checksum or len(blob) != entry.comp_len:
        raise RuntimeError('lesson capture: the stream does not match the COT entry')
    stream = blob
    rh, rw, rstate = c['req']
    names = [cl['name'] for cl in sim.wl.clients]
    # the next time the page's owner touches it, for the closing line of the lesson
    later = None
    no = -1
    for r in sim.trace.records:
        if r['ev'] != 'access':
            continue
        no += 1
        if no > c['access_no'] and r['h'] == h:
            later = {'access_no': no + 1, 'res': r['res'], 'w': r['w']}
            break
    cs = cfg.chunk
    sizes = [min(cs, entry.comp_len - i * cs) for i in range(entry.count)]
    top = c['sram_before'][-STACK_SHOWN:][::-1]          # top of stack first
    data = {
        'scene': scene, 'variant': 'baseline',
        'meta': _meta(sim, sim.accesses),
        'req': {'h': rh, 'w': int(rw), 'client': sim.wl.owner[rh], 'name': names[sim.wl.owner[rh]],
                'kind': 'first' if rstate == S_UNTOUCHED else 'fault', 'access_no': c['access_no'] + 1,
                'ro': cfg.is_ro(rh)},
        'victim': {'h': h, 'client': sim.wl.owner[h], 'name': names[sim.wl.owner[h]], 'frame': f,
                   'frame_pa': cfg.frame_pa(f), 'entry_pa': cfg.entry_pa(h), 'lru_len': c['lru_len']},
        'frames': {'free_before': c['free_before'], 'free_after': c['free_after'], 'total': cfg.frames,
                   'reclaim_ord': c['free_before'] - cfg.fc_low + 1},
        'desc': {'hex': job['hex'], 'opcode': desc.opcode, 'op_name': OP_NAME[desc.opcode], 'flags': desc.flags,
                 'limit': desc.limit, 'handle': desc.handle, 'frame_pa': desc.frame_pa, 'tag': desc.tag},
        'page': {'head': c['page'][:16].hex(), 'crc': checksum(c['page'])},
        'stream': {'len': len(stream), 'head': stream[:16].hex(), 'count': entry.count, 'sizes': sizes},
        'stack': {'top': top, 'size_before': len(c['sram_before']), 'size_after': len(c['sram_after']),
                  'list_chunks': c['list_chunks'], 'free_before': len(c['sram_before']) + c['list_chunks'] * cfg.list_group},
        'chunks': [{'n': n, 'pa': cfg.chunk_pa(n), 'bytes': sizes[i], 'head': stream[i * cs:i * cs + 8].hex()}
                   for i, n in enumerate(entry.chunks)],
        'cot': {'before': c['cot_before'].hex(), 'after': c['cot_after'].hex(), 'flags': entry.flags,
                'count': entry.count, 'comp_len': entry.comp_len, 'checksum': entry.checksum,
                'chunks': list(entry.chunks)},
        'done': {'hex': done['hex'], 'status': comp.status, 'status_name': ST_NAME[comp.status], 'flags': comp.flags,
                 'length': comp.length, 'checksum': comp.checksum, 'tag': comp.tag, 'aux': comp.aux,
                 'lat_ns': done['lat_ns'], 'dram_accesses': round((done['lat_ns'] - sim.accel.eng.comp_ns()) / cfg.dram_ns)},
        'later': later,
    }
    if pop['chunks'] != data['cot']['chunks'] or top[:entry.count] != data['cot']['chunks']:
        raise RuntimeError('lesson capture: popped chunks do not match the stack top or the COT entry')
    if ceil(entry.comp_len / cs) != entry.count:
        raise RuntimeError('lesson capture: chunk count does not match the stream length')
    return data


def _meta(sim, accesses):
    cfg = sim.cfg
    return {
        'seed': sim.seed, 'accesses': accesses, 'page': cfg.page, 'chunk': cfg.chunk, 'pages': cfg.pages,
        'rw_pages': cfg.rw_pages, 'frames': cfg.frames, 'pool_chunks': cfg.pool_chunks,
        'cot_base': cfg.cot_base, 'pool_base': cfg.pool_base, 'fc_base': cfg.fc_base,
        'fc_low': cfg.fc_low, 'fc_high': cfg.fc_high, 'limit': cfg.compress_limit_for_rw(),
        'sram_cap': cfg.sram_cap, 'dram_ns': cfg.dram_ns, 'comp_ns': sim.accel.eng.comp_ns(),
        'clients': [cl['name'] for cl in sim.wl.clients],
    }


def _job(sim, job, done, fixed_ns=0.0):
    d = BaselineDesc.unpack(bytes.fromhex(job['hex']))
    c = Completion.unpack(bytes.fromhex(done['hex']))
    return ({'hex': job['hex'], 'opcode': d.opcode, 'op_name': OP_NAME[d.opcode], 'flags': d.flags, 'limit': d.limit,
             'handle': d.handle, 'frame_pa': d.frame_pa, 'tag': d.tag},
            {'hex': done['hex'], 'status': c.status, 'status_name': ST_NAME[c.status], 'flags': c.flags,
             'length': c.length, 'checksum': c.checksum, 'tag': c.tag, 'aux': c.aux, 'lat_ns': done['lat_ns'],
             'dram_accesses': round((done['lat_ns'] - fixed_ns) / sim.cfg.dram_ns)})


def _capture_decompress(cfg, seed, accesses, workload):
    """The page of the compress lesson, the next time its owner touches it.

    Candidates are ranked exactly as for compress-hw, so with the same arguments both
    lessons are about the same page whenever that page comes back in a plain way: no
    reclaim inside the same access, the COT entry read from DRAM, no stack spill.
    """
    extra = max(FOLLOW_MIN, FOLLOW_FACTOR * accesses)
    sim, cands, faults = _run_to_candidates(cfg, seed, accesses, workload, extra)
    cfg = sim.cfg
    ranked = []
    for c in cands:
        sc = _score(sim, c) if c['access_no'] < accesses else None
        if sc is not None:
            ranked.append((sc, c))
    ranked.sort(key=lambda x: -x[0])                     # stable: the first of equal scores stays first
    pick = None
    for _, c in ranked:
        f = next((x for x in faults if x['h'] == c['h'] and x['access_no'] > c['access_no']), None)
        if (f and f['ok'] and f['cot_before'] == c['cot_after'] and f['free_start'] > cfg.fc_low
                and not f['ctlb_hit'] and not f['stack_dram'] and f['frame'] != c['frame']):
            pick = (c, f)
            break
    if pick is None:
        raise SystemExit('--lesson: no compressed page of this run comes back through a plain page fault; '
                         'use more --accesses or another --seed')
    c, f = pick
    h, fr = f['h'], f['frame']
    recs = sim.trace.records[f['n0']:f['n1']]
    jobs = [r for r in recs if r['ev'] == 'job']
    dones = [r for r in recs if r['ev'] == 'done']
    push = [r for r in recs if r['ev'] == 'chunk' and r['op'] == 'push']
    acc = next(r for r in sim.trace.records[f['n1']:] if r['ev'] == 'access')
    if len(jobs) != 2 or len(dones) != 2 or len(push) != 1 or acc['h'] != h or acc['res'] != 'fault':
        raise RuntimeError('lesson capture: the fault is not one DECOMPRESS job and one INVALIDATE job')
    dns = sim.accel.eng.decomp_ns()
    desc1, done1 = _job(sim, jobs[0], dones[0], dns)
    desc2, done2 = _job(sim, jobs[1], dones[1])
    entry = COTEntry.unpack(f['cot_before'])
    cs = cfg.chunk
    stream = b''.join(f['chunk_bytes'])[:entry.comp_len]
    sizes = [min(cs, entry.comp_len - i * cs) for i in range(entry.count)]
    names = [cl['name'] for cl in sim.wl.clients]
    owner = sim.wl.owner[h]
    if (desc1['opcode'] != OP_DECOMPRESS or desc2['opcode'] != OP_INVALIDATE
            or done1['status'] != ST_OK or done2['status'] != ST_OK):
        raise RuntimeError('lesson capture: unexpected jobs in the fault')
    if checksum(stream) != entry.checksum or decompress(stream, cfg.page) != f['page'] or f['page'] != c['page']:
        raise RuntimeError('lesson capture: the restored page does not match the page that was compressed')
    if push[0]['chunks'] != list(entry.chunks) or f['sram_after'] != f['sram_before'] + list(entry.chunks):
        raise RuntimeError('lesson capture: the chunks did not go back on the stack in COT order')
    if f['cot_after'] != EMPTY_ENTRY or f['free_after'] != f['free_start'] - 1:
        raise RuntimeError('lesson capture: COT entry or free-frame count is not as expected after the fault')
    if done1['dram_accesses'] != 4 or done2['dram_accesses'] != 3:
        # the lesson text counts descriptor, COT, frame, completion for job 1 and says job 2 finds the entry in the CTLB
        raise RuntimeError('lesson capture: DRAM access counts are not those of a CTLB miss followed by a CTLB hit')
    kernel_ns = acc['lat_ns'] - done1['lat_ns'] - done2['lat_ns']
    meta = _meta(sim, accesses)
    meta.update(decomp_ns=dns, kernel_fault_ns=cfg.kernel_fault_ns, spill_above=cfg.spill_above,
                run_accesses=sim.accesses, decomp_bytes_per_cycle=cfg.decomp_bytes_per_cycle)
    top = f['sram_after'][-STACK_SHOWN:][::-1]            # top of stack first, after the pushes
    return {
        'scene': 'decompress-hw', 'variant': 'baseline', 'meta': meta,
        'req': {'h': h, 'w': int(f['w']), 'client': owner, 'name': names[owner], 'kind': 'fault',
                'access_no': f['access_no'] + 1, 'ro': False, 'lat_ns': acc['lat_ns'], 'kernel_ns': kernel_ns},
        'pg': {'h': h, 'client': owner, 'name': names[owner], 'frame': fr, 'frame_pa': cfg.frame_pa(fr),
               'entry_pa': cfg.entry_pa(h)},
        'before': {'frame': c['frame'], 'frame_pa': cfg.frame_pa(c['frame']), 'access_no': c['access_no'] + 1,
                   'accesses_ago': f['access_no'] - c['access_no']},
        'frames': {'free_before': f['free_start'], 'free_after': f['free_after'], 'total': cfg.frames},
        'desc': desc1, 'done': done1, 'desc2': desc2, 'done2': done2,
        'ctlb': {'hit1': f['ctlb_hit'], 'hit2': done2['dram_accesses'] == 3},
        'page': {'head': f['page'][:16].hex(), 'crc': checksum(f['page'])},
        'stream': {'len': len(stream), 'head': stream[:16].hex(), 'count': entry.count, 'sizes': sizes},
        'stack': {'top': top, 'size_before': len(f['sram_before']), 'size_after': len(f['sram_after']),
                  'list_chunks': f['list_chunks']},
        'chunks': [{'n': n, 'pa': cfg.chunk_pa(n), 'bytes': sizes[i], 'head': stream[i * cs:i * cs + 8].hex()}
                   for i, n in enumerate(entry.chunks)],
        'cot': {'before': f['cot_before'].hex(), 'after': f['cot_after'].hex(), 'flags': entry.flags,
                'count': entry.count, 'comp_len': entry.comp_len, 'checksum': entry.checksum,
                'chunks': list(entry.chunks)},
    }


# ---------------------------------------------------------------- software-leaning scenes

def _run_software(cfg, seed, accesses, workload, extra=0):
    """Run the software variant and snapshot the machine around every RW eviction and,
    with extra > 0, around every fault on a compressed RW page. The kernel's bitmap is
    snapshotted whole, since in this design it is the only record of which chunks are free."""
    sim = Simulation('software', cfg, seed, None, 'all', workload, keep_trace=True)
    sim.build()
    sim.boot()
    k, bm, dram = sim.kernel, sim.bitmap, sim.dram
    cur = {'no': 0, 'req': None}
    cands, faults = [], []
    orig_access, orig_evict, orig_fault = k.access, k._evict_rw, k._fault_in

    def access(h, w):
        cur['req'] = (h, bool(w), k.state[h])
        cur['free0'], cur['n0'] = len(k.free_frames), len(sim.trace.records)
        r = orig_access(h, w)
        cur['no'] += 1
        return r

    def evict(h):
        f = k.frame_of[h]
        snap = {
            'h': h, 'frame': f, 'access_no': cur['no'], 'req': cur['req'],
            'page': bytes(dram.view(cfg.frame_pa(f), cfg.page)),
            'cot_before': bytes(dram.view(cfg.entry_pa(h), 32)),
            'free_before': len(k.free_frames), 'n0': len(sim.trace.records), 'lru_len': len(k.lru),
            'words0': list(bm.words), 'bm_free0': bm.free, 'cursor0': bm.cursor,
        }
        ok = orig_evict(h)
        snap.update(ok=ok, recs=list(sim.trace.records[snap['n0']:]),
                    cot_after=bytes(dram.view(cfg.entry_pa(h), 32)), free_after=len(k.free_frames),
                    words1=list(bm.words), bm_free1=bm.free, cursor1=bm.cursor)
        cands.append(snap)
        return ok

    def fault(h, f):
        if cfg.is_ro(h):
            return orig_fault(h, f)
        entry = COTEntry.unpack(bytes(dram.view(cfg.entry_pa(h), 32)))
        snap = {
            'h': h, 'frame': f, 'access_no': cur['no'], 'w': cur['req'][1], 'free_start': cur['free0'], 'n0': cur['n0'],
            'cot_before': bytes(dram.view(cfg.entry_pa(h), 32)),
            'chunk_bytes': [bytes(dram.view(cfg.chunk_pa(n), cfg.chunk)) for n in entry.chunks],
            'words0': list(bm.words), 'bm_free0': bm.free, 'cursor0': bm.cursor,
        }
        ok = orig_fault(h, f)
        snap.update(ok=ok, n1=len(sim.trace.records), free_after=len(k.free_frames),
                    cot_after=bytes(dram.view(cfg.entry_pa(h), 32)),
                    page=bytes(dram.view(cfg.frame_pa(f), cfg.page)),
                    words1=list(bm.words), bm_free1=bm.free, cursor1=bm.cursor)
        faults.append(snap)
        return ok

    k.access, k._evict_rw = access, evict
    if extra:
        k._fault_in = fault
    sim.run(accesses + extra)
    sim.audit()
    sim.close()
    return sim, cands, faults


def _one_word(chunks):
    return len({n >> 6 for n in chunks}) == 1


def _score_sw(sim, c, twin):
    """As _score, for the software run. The bitmap hands out neighbouring chunks, so scattered
    chunks are not asked for; instead every chunk reserved for the job must sit in one 64-bit
    word, because the page draws exactly one word of the bitmap. The page the hardware-leaning
    lesson is about wins outright when this run evicts it at the same access."""
    cfg = sim.cfg
    if not c['ok'] or any(c['cot_before']):
        return None
    res = next((r for r in c['recs'] if r['ev'] == 'chunk' and r['op'] == 'reserve'), None)
    if res is None or not _one_word(res['chunks']) or res['words'] != 1:
        return None
    e = COTEntry.unpack(c['cot_after'])
    if e.count >= len(res['chunks']):                    # the lesson shows a trim
        return None
    rh, _, rstate = c['req']
    s = 0
    s += 4 if 3 <= e.count <= 5 else 0
    s += 1 if e.count == 4 else 0
    s += 3 if 40 <= e.comp_len % cfg.chunk <= cfg.chunk - 40 else 0
    s += 2 if c['h'] >= 0x40 else 0
    s += 2 if sim.wl.owner[c['h']] != sim.wl.owner[rh] else 0
    s += 2 if rstate == S_UNTOUCHED else 0
    s += 3 if c['frame'] != c['h'] else 0
    s += 1 if c['free_before'] == cfg.fc_low else 0
    s += 100 if twin and (c['h'], c['access_no'] + 1) == twin else 0
    return s


def _hw_twin(scene, cfg, seed, accesses, workload):
    """What the hardware-leaning lesson of the same arguments shows, for the closing comparison."""
    try:
        d = capture(scene, cfg, seed, accesses, workload)
    except (SystemExit, RuntimeError):
        return None
    pg = d.get('victim') or d['pg']
    hw = {'h': pg['h'], 'access_no': d['req']['access_no'], 'chunks': d['cot']['chunks'],
          'desc_bytes': len(d['desc']['hex']) // 2, 'lat_ns': d['done']['lat_ns'],
          'dram_accesses': d['done']['dram_accesses'], 'jobs': 1}
    if 'done2' in d:
        hw.update(jobs=2, lat2_ns=d['done2']['lat_ns'], dram2_accesses=d['done2']['dram_accesses'],
                  access_ns=d['req']['lat_ns'], compress_access_no=d['before']['access_no'])
    return hw


def _word_hex(w):
    return f'{w:016x}'                                   # a 64-bit word does not fit a JS number


def _bits(chunks):
    out = {}
    for n in chunks:
        out[n >> 6] = out.get(n >> 6, 0) | 1 << (n & 63)
    return out


def _sw_meta(sim, accesses):
    cfg, bm = sim.cfg, sim.bitmap
    meta = _meta(sim, accesses)
    meta.update(kernel_job_ns=cfg.kernel_job_ns, kernel_fault_ns=cfg.kernel_fault_ns,
                decomp_ns=sim.accel.eng.decomp_ns(), decomp_bytes_per_cycle=cfg.decomp_bytes_per_cycle,
                bitmap_words=bm.nwords, bitmap_bytes=bm.bytes, run_accesses=sim.accesses)
    return meta


def _sw_job(sim, job, done, fixed_ns):
    d = VariantDesc.unpack(bytes.fromhex(job['hex']))
    c = Completion.unpack(bytes.fromhex(done['hex']))
    return (d, c,
            {'hex': job['hex'], 'opcode': d.opcode, 'op_name': OP_NAME[d.opcode], 'count': d.count, 'limit': d.limit,
             'frame_pa': d.frame_pa, 'comp_len': d.comp_len, 'flags': d.flags, 'checksum': d.checksum, 'tag': d.tag,
             'chunks': list(d.chunks)},
            {'hex': done['hex'], 'status': c.status, 'status_name': ST_NAME[c.status], 'flags': c.flags,
             'length': c.length, 'checksum': c.checksum, 'tag': c.tag, 'aux': c.aux, 'lat_ns': done['lat_ns'],
             'dram_accesses': round((done['lat_ns'] - fixed_ns) / sim.cfg.dram_ns)})


def _rank_sw(sim, cands, twin, accesses=None):
    ranked = []
    for c in cands:
        sc = _score_sw(sim, c, twin) if accesses is None or c['access_no'] < accesses else None
        if sc is not None:
            ranked.append((sc, c))
    ranked.sort(key=lambda x: -x[0])                     # stable: the first of equal scores stays first
    return [c for _, c in ranked]


def _compress_sw_data(sim, c, hw):
    cfg = sim.cfg
    h, f, recs = c['h'], c['frame'], c['recs']
    job = [r for r in recs if r['ev'] == 'job']
    done = [r for r in recs if r['ev'] == 'done']
    res = [r for r in recs if r['ev'] == 'chunk' and r['op'] == 'reserve']
    trim = [r for r in recs if r['ev'] == 'chunk' and r['op'] == 'trim']
    wrote = [r for r in recs if r['ev'] == 'cot']
    if not (len(job) == len(done) == len(res) == len(trim) == len(wrote) == 1) or wrote[0]['who'] != 'kernel':
        raise RuntimeError('lesson capture: the eviction is not reserve, one COMPRESS job, COT write by the kernel, trim')
    desc, comp, ddesc, ddone = _sw_job(sim, job[0], done[0], sim.accel.eng.comp_ns())
    entry = COTEntry.unpack(c['cot_after'])
    reserved, cs = res[0]['chunks'], cfg.chunk
    need = ceil(cfg.compress_limit_for_rw() / cs)
    blob = compress(c['page'])
    if checksum(blob) != entry.checksum or len(blob) != entry.comp_len:
        raise RuntimeError('lesson capture: the stream does not match the COT entry')
    if desc.opcode != OP_COMPRESS or list(desc.chunks) != reserved or len(reserved) != need or desc.tag != h:
        raise RuntimeError('lesson capture: the descriptor does not carry the chunks the kernel reserved')
    if (desc.frame_pa != cfg.frame_pa(f) or desc.limit != cfg.compress_limit_for_rw()
            or desc.comp_len or desc.flags or desc.checksum):
        raise RuntimeError('lesson capture: unexpected descriptor fields for COMPRESS')
    if (comp.status != ST_OK or comp.length != entry.comp_len or comp.checksum != entry.checksum
            or comp.tag != h or comp.aux or comp.flags):
        raise RuntimeError('lesson capture: the completion does not match the COT entry the kernel wrote')
    if ceil(entry.comp_len / cs) != entry.count or list(entry.chunks) != reserved[:entry.count]:
        raise RuntimeError('lesson capture: the COT entry does not list the first chunks of the descriptor')
    if trim[0]['chunks'] != reserved[entry.count:]:
        raise RuntimeError('lesson capture: the kernel did not give back exactly the chunks the stream left unused')
    if ddone['dram_accesses'] != 3:
        # the lesson text counts descriptor, frame, completion: the hardware never reads the COT
        raise RuntimeError('lesson capture: the job is not charged three DRAM accesses')
    word = reserved[0] >> 6
    w0, w1 = c['words0'][word], c['words1'][word]
    rbits, kbits = _bits(reserved)[word], _bits(entry.chunks)[word]
    others = [i for i in range(len(c['words0'])) if i != word and c['words0'][i] != c['words1'][i]]
    if (not _one_word(reserved) or w0 & rbits or w1 != w0 | kbits or others
            or c['bm_free1'] != c['bm_free0'] - entry.count or c['cursor0'] != word):
        raise RuntimeError('lesson capture: the bitmap did not change in the one word the lesson draws')
    stream = blob
    sizes = [min(cs, entry.comp_len - i * cs) for i in range(entry.count)]
    rh, rw, rstate = c['req']
    names = [cl['name'] for cl in sim.wl.clients]
    later, no = None, -1
    for r in sim.trace.records:
        if r['ev'] != 'access':
            continue
        no += 1
        if no > c['access_no'] and r['h'] == h:
            later = {'access_no': no + 1, 'res': r['res'], 'w': r['w']}
            break
    chunks = [{'n': n, 'pa': cfg.chunk_pa(n), 'bytes': sizes[i], 'head': stream[i * cs:i * cs + 8].hex()}
              for i, n in enumerate(entry.chunks)]
    tiles = chunks + [{'n': n, 'pa': cfg.chunk_pa(n), 'bytes': 0, 'head': ''} for n in reserved[entry.count:]]
    if hw:
        hw = dict(hw, same=(hw['h'], hw['access_no']) == (h, c['access_no'] + 1))
    return {
        'scene': 'compress-sw', 'variant': 'software', 'meta': _sw_meta(sim, sim.accesses),
        'req': {'h': rh, 'w': int(rw), 'client': sim.wl.owner[rh], 'name': names[sim.wl.owner[rh]],
                'kind': 'first' if rstate == S_UNTOUCHED else 'fault', 'access_no': c['access_no'] + 1,
                'ro': cfg.is_ro(rh)},
        'victim': {'h': h, 'client': sim.wl.owner[h], 'name': names[sim.wl.owner[h]], 'frame': f,
                   'frame_pa': cfg.frame_pa(f), 'entry_pa': cfg.entry_pa(h), 'lru_len': c['lru_len']},
        'frames': {'free_before': c['free_before'], 'free_after': c['free_after'], 'total': cfg.frames,
                   'reclaim_ord': c['free_before'] - cfg.fc_low + 1},
        'desc': ddesc, 'done': ddone,
        'page': {'head': c['page'][:16].hex(), 'crc': checksum(c['page'])},
        'stream': {'len': len(stream), 'head': stream[:16].hex(), 'count': entry.count, 'sizes': sizes},
        'chunks': chunks, 'tiles': tiles,
        'cot': {'before': c['cot_before'].hex(), 'after': c['cot_after'].hex(), 'flags': entry.flags,
                'count': entry.count, 'comp_len': entry.comp_len, 'checksum': entry.checksum,
                'chunks': list(entry.chunks)},
        'bitmap': {'word': word, 'first_chunk': word * 64, 'nwords': sim.bitmap.nwords,
                   'before': _word_hex(w0), 'reserved': _word_hex(w0 | rbits), 'after': _word_hex(w1),
                   'free_before': c['bm_free0'], 'free_reserved': c['bm_free0'] - need, 'free_after': c['bm_free1'],
                   'cursor_before': c['cursor0'], 'cursor_after': c['cursor1'], 'scanned': res[0]['words'],
                   'need': need, 'reserved_chunks': reserved, 'trimmed': trim[0]['chunks']},
        'later': later, 'hw': hw,
    }


def _capture_compress_sw(cfg, seed, accesses, workload):
    hw = _hw_twin('compress-hw', cfg, seed, accesses, workload)
    sim, cands, _ = _run_software(cfg, seed, accesses, workload)
    ranked = _rank_sw(sim, cands, hw and (hw['h'], hw['access_no']))
    if not ranked:
        raise SystemExit('--lesson: this run has no COMPRESS job that fits the software-leaning lesson '
                         '(reclaim, success, chunks of one bitmap word, a trim); use more --accesses or another --seed')
    return _compress_sw_data(sim, ranked[0], hw)


def _capture_decompress_sw(cfg, seed, accesses, workload):
    """The page of compress-sw, the next time its owner touches it: one DECOMPRESS job.

    Ranked as compress-sw, and as in decompress-hw the fault must be a plain one: no reclaim
    inside the same access, a frame other than the one the page left, and here also all of
    the page's chunks in one bitmap word.
    """
    extra = max(FOLLOW_MIN, FOLLOW_FACTOR * accesses)
    hw = _hw_twin('decompress-hw', cfg, seed, accesses, workload)
    sim, cands, faults = _run_software(cfg, seed, accesses, workload, extra)
    cfg = sim.cfg
    pick = None
    for c in _rank_sw(sim, cands, hw and (hw['h'], hw['compress_access_no']), accesses):
        f = next((x for x in faults if x['h'] == c['h'] and x['access_no'] > c['access_no']), None)
        if (f and f['ok'] and f['cot_before'] == c['cot_after'] and f['free_start'] > cfg.fc_low
                and f['frame'] != c['frame']):
            pick = (c, f)
            break
    if pick is None:
        raise SystemExit('--lesson: no compressed page of this run comes back through a plain page fault; '
                         'use more --accesses or another --seed')
    c, f = pick
    h, fr = f['h'], f['frame']
    recs = sim.trace.records[f['n0']:f['n1']]
    jobs = [r for r in recs if r['ev'] == 'job']
    dones = [r for r in recs if r['ev'] == 'done']
    rel = [r for r in recs if r['ev'] == 'chunk' and r['op'] == 'release']
    reads = [r for r in recs if r['ev'] == 'cot_read']
    wrote = [r for r in recs if r['ev'] == 'cot']
    acc = next(r for r in sim.trace.records[f['n1']:] if r['ev'] == 'access')
    if (len(jobs) != 1 or len(dones) != 1 or len(rel) != 1 or len(reads) != 1 or len(wrote) != 1
            or reads[0]['who'] != 'kernel' or wrote[0]['who'] != 'kernel' or acc['h'] != h or acc['res'] != 'fault'):
        raise RuntimeError('lesson capture: the fault is not COT read by the kernel, one DECOMPRESS job, '
                           'COT clear by the kernel, release')
    dns = sim.accel.eng.decomp_ns()
    desc, comp, ddesc, ddone = _sw_job(sim, jobs[0], dones[0], dns)
    entry = COTEntry.unpack(f['cot_before'])
    cs = cfg.chunk
    stream = b''.join(f['chunk_bytes'])[:entry.comp_len]
    sizes = [min(cs, entry.comp_len - i * cs) for i in range(entry.count)]
    names = [cl['name'] for cl in sim.wl.clients]
    owner = sim.wl.owner[h]
    if (desc.opcode != OP_DECOMPRESS or desc.chunks != entry.chunks or desc.comp_len != entry.comp_len
            or desc.checksum != entry.checksum or desc.flags or desc.limit != cfg.page
            or desc.frame_pa != cfg.frame_pa(fr) or desc.tag != h):
        raise RuntimeError('lesson capture: the descriptor does not carry what the kernel read from the COT entry')
    if comp.status != ST_OK or comp.length != cfg.page or comp.checksum != entry.checksum or comp.tag != h or comp.aux:
        raise RuntimeError('lesson capture: unexpected completion of the DECOMPRESS job')
    if checksum(stream) != entry.checksum or decompress(stream, cfg.page) != f['page'] or f['page'] != c['page']:
        raise RuntimeError('lesson capture: the restored page does not match the page that was compressed')
    if f['cot_after'] != EMPTY_ENTRY or f['free_after'] != f['free_start'] - 1:
        raise RuntimeError('lesson capture: COT entry or free-frame count is not as expected after the fault')
    if ddone['dram_accesses'] != 3:
        raise RuntimeError('lesson capture: the job is not charged three DRAM accesses')
    if acc['lat_ns'] != cfg.kernel_fault_ns + ddone['lat_ns'] + cfg.kernel_job_ns:
        raise RuntimeError('lesson capture: the access latency is not fault handling + one job + bookkeeping')
    word = entry.chunks[0] >> 6
    w0, w1 = f['words0'][word], f['words1'][word]
    bits = _bits(entry.chunks)[word]
    others = [i for i in range(len(f['words0'])) if i != word and f['words0'][i] != f['words1'][i]]
    if (not _one_word(entry.chunks) or rel[0]['chunks'] != list(entry.chunks) or w0 & bits != bits
            or w1 != w0 & ~bits or others or f['bm_free1'] != f['bm_free0'] + entry.count):
        raise RuntimeError('lesson capture: the bitmap did not change in the one word the lesson draws')
    if hw:
        hw = dict(hw, same=(hw['h'], hw['access_no']) == (h, f['access_no'] + 1))
    return {
        'scene': 'decompress-sw', 'variant': 'software', 'meta': _sw_meta(sim, accesses),
        'req': {'h': h, 'w': int(f['w']), 'client': owner, 'name': names[owner], 'kind': 'fault',
                'access_no': f['access_no'] + 1, 'ro': False, 'lat_ns': acc['lat_ns'],
                'kernel_ns': cfg.kernel_fault_ns},
        'pg': {'h': h, 'client': owner, 'name': names[owner], 'frame': fr, 'frame_pa': cfg.frame_pa(fr),
               'entry_pa': cfg.entry_pa(h)},
        'before': {'frame': c['frame'], 'frame_pa': cfg.frame_pa(c['frame']), 'access_no': c['access_no'] + 1,
                   'accesses_ago': f['access_no'] - c['access_no']},
        'frames': {'free_before': f['free_start'], 'free_after': f['free_after'], 'total': cfg.frames},
        'desc': ddesc, 'done': ddone,
        'page': {'head': f['page'][:16].hex(), 'crc': checksum(f['page'])},
        'stream': {'len': len(stream), 'head': stream[:16].hex(), 'count': entry.count, 'sizes': sizes},
        'chunks': [{'n': n, 'pa': cfg.chunk_pa(n), 'bytes': sizes[i], 'head': stream[i * cs:i * cs + 8].hex()}
                   for i, n in enumerate(entry.chunks)],
        'cot': {'before': f['cot_before'].hex(), 'after': f['cot_after'].hex(), 'flags': entry.flags,
                'count': entry.count, 'comp_len': entry.comp_len, 'checksum': entry.checksum,
                'chunks': list(entry.chunks)},
        'bitmap': {'word': word, 'first_chunk': word * 64, 'nwords': sim.bitmap.nwords,
                   'before': _word_hex(w0), 'after': _word_hex(w1),
                   'free_before': f['bm_free0'], 'free_after': f['bm_free1'], 'released': rel[0]['chunks']},
        'hw': hw,
    }


def _read(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def render(data, fragment=False):
    variant, files, title = SCENES[data['scene']]
    blob = json.dumps(data, separators=(',', ':')).replace('</', '<\\/')
    shell = _read(os.path.join(ASSETS, 'shell.html')).replace('<title>LZ4 Lesson</title>', f'<title>{title}</title>', 1)
    js = '\n'.join([_read(CHARS)] + [_read(os.path.join(ASSETS, n)) for n in files])
    body = (shell
            + f'\n<script src="{THREE_URL}"></script>\n'
            + f'<script type="application/json" id="lesson-data">{blob}</script>\n'
            + f'<script>\n{js}\n</script>\n')
    if fragment:
        return body
    return ('<!doctype html>\n<html lang="zh-Hant">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '</head>\n<body>\n' + body + '</body>\n</html>\n')


def write_html(path, data, fragment=False):
    html = render(data, fragment)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return len(html.encode('utf-8'))
