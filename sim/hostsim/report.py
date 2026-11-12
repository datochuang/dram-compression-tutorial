"""Numbers out of a finished host run. None of them is a time: they are counts and sizes that
depend only on the algorithm (which page goes, how chunks are handed out), not on how fast anything is.

metrics() turns a Machine into a plain dict (JSON friendly); the md_* functions turn such dicts
into Markdown tables. The prose around the tables lives in the document template.
"""
from collections import Counter

from ifsim.report import table

from .kernel import COMPRESSED, PRESENT, S_NAME

KINDS = ('hit', 'first_touch', 'fault_ro', 'fault_rw', 'lost')
KIND_ZH = {'hit': 'PTE 有效，直接完成', 'first_touch': '第一次碰的 RW page，補零', 'fault_ro': 'RO page，DECOMPRESS',
           'fault_rw': 'RW page，DECOMPRESS', 'lost': '存放的資料損毀，page 遺失'}


def metrics(m, name=''):
    cfg, k, st, hw, bm = m.cfg, m.kernel, m.st, m.hw.st, m.bitmap
    FL = m.spec.enum['flag']
    rw_hist, waste = Counter(), Counter()
    stored = Counter()
    for h in range(cfg.pages):
        if k.state[h] != COMPRESSED:
            continue
        e = m.spec.unpack('cot_entry', m.dram.view(cfg.entry_pa(h), 32))
        kind = 'ro' if cfg.is_ro(h) else 'rw'
        stored[kind + '_pages'] += 1
        stored[kind + '_chunks'] += e['count']
        stored[kind + '_bytes'] += e['comp_len']
        if kind == 'rw':
            rw_hist[e['count']] += 1
    states = Counter(S_NAME[s] for s in k.state)
    present_rw = sum(1 for h in range(cfg.rw_pages) if k.state[h] == PRESENT)
    return {
        'name': name, 'cfg': 'small' if cfg.pages < 10000 else 'full', 'seed': m.seed, 'policy': m.policy,
        'codec': m.codec.name, 'map_accessed': m.port.map_accessed, 'accesses': m.accesses,
        'pages': cfg.pages, 'rw_pages': cfg.rw_pages, 'ro_pages': cfg.ro_pages, 'frames': cfg.frames,
        'pool_chunks': cfg.pool_chunks, 'fc_low': cfg.fc_low, 'fc_high': cfg.fc_high,
        'results': {x: st[x] for x in KINDS}, 'refaults': st['refaults'], 'writes': st['writes'],
        'clients': [{'name': c['name'], 'accesses': sum(cs.values()), 'faults': sum(cs.values()) - cs['hit']}
                    for c, cs in zip(m.wl.clients, m.cst)],
        'hw': dict(hw), 'kernel': dict(k.st), 'tlb_flushes': m.port.st['tlb_flushes'],
        'rw_unmaps': st['rw_unmaps'], 'rw_unmaps_unwritten': st['rw_unmaps_unwritten'],
        'incompressible_pages': len(k.incompressible), 'injected': st['injected'],
        'build': dict(m.build), 'states': dict(states), 'present_rw': present_rw,
        'stored': dict(stored), 'rw_hist': {str(n): rw_hist[n] for n in sorted(rw_hist)},
        'chunks_free': bm.free, 'chunks_free_min': m.min_free_chunks,
        'bitmap': dict(bm.st), 'bitmap_scan_max': bm.scan_max, 'bitmap_words': bm.nwords,
    }


def _per(a, b, digits=2):
    return f'{a / b:.{digits}f}' if b else '0'


def md_results(ms):
    """One column per run."""
    head = ('', *[x['name'] for x in ms])
    rows = [('access 次數', *[x['accesses'] for x in ms])]
    rows += [(KIND_ZH[kd], *[x['results'][kd] for x in ms]) for kd in KINDS if any(x['results'][kd] for x in ms)]
    if any(x['refaults'] for x in ms):
        rows.append(('fault 完成後 CPU 重試前又被搬走', *[x['refaults'] for x in ms]))
    rows += [
        ('LZ4 HW job 總數', *[x['hw'].get('jobs', 0) for x in ms]),
        ('DECOMPRESS', *[x['hw'].get('DECOMPRESS_OK', 0) for x in ms]),
        ('COMPRESS 成功', *[x['hw'].get('COMPRESS_OK', 0) for x in ms]),
        ('COMPRESS 回 INCOMPRESSIBLE', *[x['hw'].get('COMPRESS_INCOMPRESSIBLE', 0) for x in ms]),
        ('每 1000 次 access 的 job 數', *[_per(1000 * x['hw'].get('jobs', 0), x['accesses'], 1) for x in ms]),
    ]
    return table(head, rows)


def md_reclaim(x):
    k = x['kernel']
    rows = [
        ('`reclaim` 被叫醒的次數', k.get('reclaim', 0)),
        ('`evict_ro`：丟掉 frame，不需要 job', k.get('evict_ro', 0)),
        ('`evict_rw`：一個 COMPRESS job', k.get('evict_rw', 0)),
        ('`pte_unmap` 次數，每次要 flush TLB', x['tlb_flushes']),
        ('clock 每選一個 page 平均看幾個 frame', _per(k.get('clock_steps', 0), k.get('clock_picks', 0))),
        ('被記為 incompressible 而留在 frame 的 RW page', x['incompressible_pages']),
        ('RW page 被搬走時，從取回後沒被寫過', f"{x['rw_unmaps_unwritten']}，占 RW 搬走次數的 "
                                              f"{_per(100 * x['rw_unmaps_unwritten'], x['rw_unmaps'], 1)}%"),
        ('chunk pool 不夠 7 個 chunk 的次數', k.get('pool_full', 0)),
        ('找不到任何可搬走的 page 的次數', k.get('reclaim_stuck', 0)),
    ]
    return table(('項目', '數值'), rows)


def md_pool(x):
    b, s, bm = x['build'], x['stored'], x['bitmap']
    ro_pages = x['ro_pages']
    rows = [
        ('chunk pool 大小', f"{x['pool_chunks']} 個 chunk"),
        ('RO image：page 數', ro_pages),
        ('RO image：占用 chunk', f"{b['ro_chunks']}，平均每 page {_per(b['ro_chunks'], ro_pages)} 個"),
        ('RO image：以 RAW 存放的 page', b.get('ro_raw', 0)),
        ('RO image：最後一個 chunk 沒用到的 byte', f"{b['ro_chunks'] * 512 - b['ro_bytes']}，平均每 page "
                                                  f"{_per(b['ro_chunks'] * 512 - b['ro_bytes'], ro_pages, 0)}"),
        ('開機後的 free chunk', b['free_chunks_at_boot']),
        ('執行中 free chunk 的最低點', x['chunks_free_min']),
        ('結束時存放中的 RW page', s.get('rw_pages', 0)),
        ('結束時 RW 占用 chunk', f"{s.get('rw_chunks', 0)}，平均每 page {_per(s.get('rw_chunks', 0), s.get('rw_pages', 0))} 個"),
        ('結束時 RW 最後一個 chunk 沒用到的 byte', f"平均每 page {_per(s.get('rw_chunks', 0) * 512 - s.get('rw_bytes', 0), s.get('rw_pages', 0), 0)}"),
        ('bitmap `reserve` 次數', bm.get('reserves', 0)),
        ('每次 `reserve` 平均掃過的 64-bit word', _per(bm.get('words_scanned', 0), bm.get('reserves', 0))),
        ('單次 `reserve` 最多掃過的 word', f"{x['bitmap_scan_max']}，bitmap 共 {x['bitmap_words']} 個 word"),
    ]
    return table(('項目', '數值'), rows)


def md_hist(x):
    b = x['build']
    ns = range(1, 9)
    rows = [('RO image', *[b.get(f'ro_hist_{n}', 0) for n in ns]),
            ('結束時存放中的 RW page', *[x['rw_hist'].get(str(n), 0) for n in ns])]
    return table(('每個 page 占用的 chunk 數', *[str(n) for n in ns]), rows)


def md_clients(x):
    rows = [(c['name'], c['accesses'], c['faults'], _per(100 * c['faults'], c['accesses'], 1) + '%') for c in x['clients']]
    return table(('user SW', 'access', '其中發生 page fault', '比例'), rows)


def text(x):
    """Plain summary for the terminal."""
    r, k = x['results'], x['kernel']
    L = [f"{x['cfg']} machine, seed {x['seed']}, policy {x['policy']}, codec {x['codec']}: {x['accesses']} accesses",
         '  ' + ', '.join(f'{kd} {r[kd]}' for kd in KINDS if r[kd]) + (f", refaults {x['refaults']}" if x['refaults'] else ''),
         '  LZ4 HW: ' + ', '.join(f'{a} {b}' for a, b in sorted(x['hw'].items())),
         f"  reclaim {k.get('reclaim', 0)} runs, evict_ro {k.get('evict_ro', 0)}, evict_rw {k.get('evict_rw', 0)}, "
         f"clock {_per(k.get('clock_steps', 0), k.get('clock_picks', 0))} frames per pick, "
         f"RW evictions unwritten since refetch {x['rw_unmaps_unwritten']} of {x['rw_unmaps']}",
         f"  chunks: {x['pool_chunks']} in the pool, {x['build']['ro_chunks']} RO, free now {x['chunks_free']}, "
         f"lowest {x['chunks_free_min']}; bitmap {_per(x['bitmap'].get('words_scanned', 0), x['bitmap'].get('reserves', 0))} words per reserve"]
    return '\n'.join(L)
