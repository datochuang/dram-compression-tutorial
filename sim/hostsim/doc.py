"""Generate spec/control-procedures-v0.md: the procedures as they are in kernel.py, one real
walk-through of each, the untimed numbers of the full-size machine, and what happened when
several threads ran the same procedures under many schedules.

The numbers take about a minute to produce, so they are kept beside the document in a
JSON file; the source listings and the walk-throughs are produced again on every render.
"""
import inspect
import json
import os
import textwrap

from ifsim.gen import fill
from ifsim.report import table

from . import conc
from . import report as R
from . import walk
from .check import audit
from .kernel import Kernel
from .kernel import OutOfMemory
from .machine import Machine, NoProgress, make

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'spec'))
TEMPLATE = os.path.join(HERE, 'templates', 'control_procedures.tmpl.md')
DOC, NUMBERS = 'control-procedures-v0.md', 'control-procedures-v0.json'
SHOWN = ('boot', 'boot_load', 'page_fault', 'first_touch', 'fault_in', 'reclaim', 'pick_victim', 'evict_ro', 'evict_rw',
         'pin_page', 'unpin_page', 'lz4_job', 'put_frame', 'note_fresh', 'thread_gone',
         'sw_decode', 'decode_stored', 'stored_right', 'note_hw')
RUNS = (('clock', dict(policy='clock')),
        ('clock，新 PTE 不設 accessed bit', dict(policy='clock', map_accessed=0)),
        ('理想 LRU，做不出來', dict(policy='lru')))


HOT = dict(hot_ro_pages=100, hot_rw_pages=200)
ALL = dict(hot_ro_pages=100, hot_rw_pages=1280)            # user SW ends up touching every RW page
STRESS = (  # label, workload, RAW store, pages protected after a fault
    ('45%，基準', dict(HOT), False, 1),
    ('45%，基準', dict(HOT), True, 1),
    ('80%', dict(HOT, rw_ratio=0.8, rw_sd=0.05), False, 1),
    ('80%', dict(HOT, rw_ratio=0.8, rw_sd=0.05), True, 1),
    ('90%', dict(HOT, rw_ratio=0.9, rw_sd=0.05), False, 1),
    ('90%', dict(HOT, rw_ratio=0.9, rw_sd=0.05), False, 0),
    ('90%', dict(HOT, rw_ratio=0.9, rw_sd=0.05), True, 1),
    ('100%，而且碰遍所有 RW page', dict(ALL, rw_ratio=1.0, rw_sd=0.05), True, 1),
    ('100%，而且碰遍所有 RW page', dict(ALL, rw_ratio=1.0, rw_sd=0.05), True, 0),
)


def stress(n=20000):
    """Small machine, RW data that compresses badly: what the control procedure does at its limits."""
    from lz4sim.config import SMALL
    rows = []
    for label, wl, raw, protect in STRESS:
        m = Machine(SMALL.with_(rw_raw_store=raw), workload=wl, protect=protect)
        m.build_image()
        m.boot()
        try:
            m.run(n)
            audit(m)
            end = 'ok'
        except (OutOfMemory, NoProgress) as e:
            end = type(e).__name__
        rows.append({'label': label, 'raw': raw, 'protect': protect, 'end': end, 'accesses': m.accesses,
                     'jobs': m.hw.st['jobs'], 'kept': len(m.kernel.incompressible), 'frames': m.cfg.frames,
                     'chunks_free_min': m.min_free_chunks, 'pool_chunks': m.cfg.pool_chunks})
    return rows


END_ZH = {'ok': '跑完', 'OutOfMemory': '停在 `OutOfMemory`：沒有 frame 可以釋放',
          'NoProgress': '停在 `NoProgress`：同一道指令一直 fault'}


def md_stress(rows):
    out = [(r['label'], 'RAW 存進 8 個 chunk' if r['raw'] else '留在 frame', '有' if r['protect'] else '沒有', END_ZH[r['end']],
            r['accesses'], r['jobs'], r['kept'], r['chunks_free_min']) for r in rows]
    return table(('RW 資料壓縮後占原本的比例', '壓不到 7 個 chunk 的 page', '保護剛 fault 進來的 page', '結果', '完成的 access',
                  'LZ4 job', '占住 frame 的 incompressible page', 'free chunk 最低點'), out)


def numbers(cfg='full', n=None):
    """Run every configuration of RUNS on one machine size, audit each at the end."""
    out = []
    for name, kw in RUNS:
        m = make(cfg, n, **kw)
        x = R.metrics(m, name)
        x['audit'] = audit(m)
        out.append(x)
    small = {key: make('small', map_accessed=a).hw.st['jobs'] for key, a in (('set', 1), ('clear', 0))}
    return {'cfg': cfg, 'runs': out, 'stress': stress(), 'small_accessed': small, 'conc': conc_numbers()}


# ------------------------------------------------------------------ several threads
CONC_RUNS, CONC_DAMAGED, CONC_FAULTY, CONC_DOWN = 300, 100, 200, 100


def conc_numbers():
    return {'survey': conc.survey(CONC_RUNS), 'damaged': conc.survey(CONC_DAMAGED, damage=0.05),
            'faulty': conc.survey(CONC_FAULTY, faults=2, kill=True),
            'down': conc.survey(CONC_DOWN, hw_down=True, cfg=conc.ROOMY),
            'explore': conc.explore_table(), 'mutants': conc.mutant_table(CONC_RUNS)}


SURVEY_ROWS = (
    ('schedule 數', 'schedules'), ('scheduler 做了幾次選擇', 'steps'), ('跑完的指令', 'instructions'),
    ('第一次碰 RW page', 'first_touch'), ('RO page 的 fault', 'fault_ro'), ('RW page 的 fault', 'fault_rw'),
    ('fault 進來發現別的 thread 已經取回：`spurious`', 'spurious'),
    ('fault 碰到正在 DECOMPRESS 的 page：`wait_page`', 'wait_page_decompressing'),
    ('fault 碰到正在 COMPRESS 的 page：`wait_page`', 'wait_page_compressing'),
    ('fault 沒有 free frame：`wait_frame`', 'wait_frame'),
    ('`pin_page`', 'pin_page'), ('LZ4 job', 'jobs'), ('同時交給 LZ4 HW 的 job，最多', 'jobs_queued_max'),
    ('`cache_clean`', 'cache_clean'), ('`cache_invalidate`', 'cache_invalidate'),
    ('被弄壞的 stream', 'injected'), ('DECOMPRESS 回 BAD_STREAM', 'DECOMPRESS_BAD_STREAM'),
    ('`sw_decode` 也解不開，page 變成 LOST', 'lost_pages'), ('`page_fault` 回 `lost`', 'lost'),
    ('碰到 LOST 的 page 而被結束的 thread', 'threads_ended_lost'),
    ('結束時解開核對過的 stream', 'streams_checked'),
)


def md_survey(c):
    a, b = c['survey'], c['damaged']
    return table(('發生了幾次', f"{a['schedules']} 個隨機 schedule", f"{b['schedules']} 個隨機 schedule，另外弄壞存放中的 stream"),
                 [(name, a.get(key, 0), b.get(key, 0)) for name, key in SURVEY_ROWS])


FAULT_ROWS = (
    ('schedule 數', 'schedules'), ('跑完的指令', 'instructions'), ('LZ4 HW 回了 completion 的 job', 'jobs'),
    ('COMPRESS 回 BUS_ERROR', 'COMPRESS_BUS_ERROR'), ('DECOMPRESS 回 BUS_ERROR', 'DECOMPRESS_BUS_ERROR'),
    ('DECOMPRESS 回 BAD_STREAM，stream 其實沒壞', 'DECOMPRESS_BAD_STREAM'),
    ('交出去之後沒有 completion 的 job', 'no_answer'),
    ('kernel 自己解：`sw_decode`', 'sw_decode'), ('其中解回正確內容的', 'sw_decode_ok'),
    ('COMPRESS 失敗，page 留在 frame，chunk 還回去', 'compress_failed'),
    ('決定不再使用 LZ4 HW 的 schedule', 'lz4_off'),
    ('`evict_ro`', 'evict_ro'), ('`evict_rw`', 'evict_rw'),
    ('執行到一半被終止的 thread', 'threads_ended_killed'),
    ('變成 LOST 的 page', 'lost_pages'), ('結束時解開核對過的 stream', 'streams_checked'),
)


def md_survey_faults(c):
    a, b = c['faulty'], c['down']
    return table(('發生了幾次', f"{a['schedules']} 個隨機 schedule：兩個 job 失敗，一個 thread 被終止",
                  f"{b['schedules']} 個隨機 schedule：LZ4 HW 中途不再回答，{conc.ROOMY.frames} 個 frame"),
                 [(name, a.get(key, 0), b.get(key, 0)) for name, key in FAULT_ROWS])


def md_explore(rows):
    return table(('user SW thread', '每個 thread 的步數', '最多打斷幾次', '列舉出的 schedule', '結果'),
                 [(r['users'], r['length'], r['bound'], r['schedules'], '全部通過') for r in rows])


MUTANT_ZH = {
    'shared_tag': 'completion 的 tag 跟最新送出的 tag 比，不是跟這個 job 自己的比。這是改之前的寫法',
    'no_wake_frame': '`put_frame` 不叫醒等 frame 的 thread。這是改之前的寫法',
    'no_wake_page': 'job 結束後不呼叫 `wake_page`',
    'wait_not_atomic': '`wait_page` 與 `wait_frame` 放開 lock 之後，隔一步才睡著',
    'unlatched_reclaimer': 'reclaimer 正在跑的時候，`wake_reclaimer` 的要求被丟掉',
    'no_decompressing': '不把 state 改成 DECOMPRESSING',
    'no_compressing': '不把 state 改成 COMPRESSING',
    'local_tlb_flush': '`pte_unmap` 只清自己這個 core 的 TLB',
    'no_cache_clean': 'COMPRESS 之前不做 `cache_clean`',
    'no_cache_invalidate': 'DECOMPRESS 之後不做 `cache_invalidate`',
    'invalidate_dcache_only': '`cache_invalidate` 只清 data cache，不清 instruction cache',
    'forget_pin': 'driver 沒有 `pin_page` 就從 ISR 與 kernel 的 mapping 碰 page',
    'protect_1': '`protect` 設成 1。一個 user SW thread，3 個 frame，reclaimer 的優先權比 user SW 高',
    'too_few_frames': '什麼都沒拿掉，但只有 3 個 frame 卻有兩個 user SW thread，`protect` 是 2',
    'no_sw_decode': 'LZ4 HW 沒把 page 交回來時，不用 kernel 自己的 decoder 再解一次，直接標成 LOST。另外讓兩個 DECOMPRESS 失敗',
    'sw_decode_no_clean': '`sw_decode` 寫完 frame 之後不做 `cache_clean`。另外讓兩個 DECOMPRESS 失敗',
    'leak_on_job_failure': 'COMPRESS 失敗時不把保留的 chunk 還給 bitmap。另外讓兩個 COMPRESS 回 BUS_ERROR',
    'kill_in_kernel': 'thread 可以在 `page_fault` 與 `pin_page` 裡面的任何一步被終止，不等它回來',
    'no_boot_flush': '`boot` 不做 `cache_flush_layer`',
    'chunk_read_cached': '`chunk_read` 經過 cache 裡留著的舊 line 讀 chunk。開著 `verify`',
}
STOP_ZH = {'KernelBug': 'kernel 自己的檢查', 'Deadlock': '結束：有 thread 永遠在等', 'JobRace': 'job',
           'FaultNotAllowed': 'context', 'StaleTlb': 'TLB', 'CacheError': 'cache', 'NoProgress': '前進',
           'OutOfMemory': '結束：真的沒有 frame', 'DataMismatch': '資料', 'AuditError': 'audit', 'AliasError': 'kernel mapping'}


def md_mutants(rows):
    out = []
    for r in rows:
        if r['schedule'] is None:
            out.append((f"`{r['name']}`", MUTANT_ZH[r['name']], '沒被擋下', '', ''))
        else:
            out.append((f"`{r['name']}`", MUTANT_ZH[r['name']], f"第 {r['schedule']} 個", STOP_ZH[r['stopped_by']],
                        f"`{r['stopped_by']}: {r['text']}`"))
    return table(('名稱', '拿掉或改掉什麼', '第幾個 schedule 被擋下', '哪一項檢查', '訊息'), out)


def source(name):
    fn = inspect.unwrap(getattr(Kernel, name))
    lines = textwrap.dedent(inspect.getsource(fn)).splitlines()
    return '```python\n' + '\n'.join(x for x in lines if x.strip() != '@procedure') + '\n```'


def transitions(*logs):
    """Every state change that happened in the given step logs, with the procedure that made it."""
    seen = {}
    for log in logs:
        stack = []
        for who, what, v in log:
            if what.startswith('enter '):
                stack.append(what[6:])
            elif what.startswith('leave '):
                stack.pop()
            elif what == 'state' and stack:
                seen.setdefault((v['old'].upper(), v['new'].upper(), stack[-1]), 0)
    order = ['UNTOUCHED', 'COMPRESSED', 'DECOMPRESSING', 'PRESENT', 'COMPRESSING', 'LOST']
    rows = sorted(seen, key=lambda t: (order.index(t[0]), order.index(t[1])))
    return table(('原本的 state', '新的 state', '由哪個程序改'), [(a, b, f'`{p}`') for a, b, p in rows])


def md_audit(runs):
    rows = [(x['name'], x['accesses'], x['audit'].get('present', 0), x['audit'].get('compressed', 0),
             x['audit'].get('streams_checked', 0), x['audit']['chunks_listed'], x['audit']['chunks_free'],
             f"{x['audit']['guard_bytes'] / (1 << 20):.0f} MiB") for x in runs]
    return table(('執行', 'access', 'present page', 'compressed page', '解開核對過的 stream',
                  'COT 列出的 chunk', 'free chunk', '核對沒被動過的記憶體'), rows)


def md_capacity(x):
    """How many RW pages fit: frames plus what the free part of the pool can hold."""
    free, frames, rw = x['build']['free_chunks_at_boot'], x['frames'], x['rw_pages']
    mean = x['stored']['rw_chunks'] / x['stored']['rw_pages']

    def row(name, per_page):
        pages = frames + int(free / per_page)
        return (name, f'{per_page:.2f}', pages, f'{pages * 4096 / (1 << 20):.0f} MiB', '夠' if pages >= rw else '不夠')
    rows = [row('每個 RW page 都壓不動，RAW 存 8 個 chunk', 8), row('這次執行的平均', mean),
            ('user SW 看到的 RW 空間', '', rw, f'{rw * 4096 / (1 << 20):.0f} MiB', '')]
    return table(('情況', '每個存放的 RW page 用幾個 chunk', '放得下的 RW page', '相當於', '放得下全部 RW 空間嗎'), rows)


def render(nums):
    runs = nums['runs']
    main = runs[0]
    m, log = walk.capture()
    sc = walk.scenarios(log)
    lost = walk.lost_scenario()
    rescued = walk.rescued_scenario()
    c = nums['conc']
    every = [c[k] for k in ('survey', 'damaged', 'faulty', 'down')]
    extra = {'src:' + n: source(n) for n in SHOWN}
    extra.update({
        'conc_survey': md_survey(c), 'conc_explore': md_explore(c['explore']), 'conc_mutants': md_mutants(c['mutants']),
        'conc_survey_faults': md_survey_faults(c),
        'conc_schedules': sum(x['schedules'] for x in every),
        'conc_explored': sum(r['schedules'] for r in c['explore']),
        'conc_instructions': sum(x['instructions'] for x in every),
        'roomy_frames': conc.ROOMY.frames, 'strikes': Kernel.STRIKES,
        'f_sw': c['faulty']['sw_decode'], 'f_cfail': c['faulty']['compress_failed'],
        'f_killed': c['faulty']['threads_ended_killed'], 'f_n': c['faulty']['schedules'],
        'd_sw': c['down']['sw_decode'], 'd_off': c['down'].get('lz4_off', 0), 'd_n': c['down']['schedules'],
        'd_ro': c['down']['evict_ro'], 'd_rw': c['down']['evict_rw'],
        'dmg_sw': c['damaged'].get('sw_decode', 0), 'dmg_sw_ok': c['damaged'].get('sw_decode_ok', 0),
        'dmg_lost': c['damaged'].get('lost_pages', 0),
        'conc_mutants_stopped': sum(1 for r in c['mutants'] if r['schedule'] is not None),
        'conc_mutants_all': len(c['mutants']),
        'tiny_frames': conc.TINY.frames, 'tiny_rw': conc.TINY.rw_pages, 'tiny_ro': conc.TINY.ro_pages,
        'conc_w_dec': c['survey']['wait_page_decompressing'], 'conc_w_comp': c['survey']['wait_page_compressing'],
        'conc_spurious': c['survey']['spurious'], 'conc_w_frame': c['survey']['wait_frame'],
    })
    extra.update({'walk:' + k: walk.md(ev) for k, ev in sc.items() if k != 'reclaim'})
    extra.update({
        'walk:reclaim': walk.md_reclaim(sc['reclaim']), 'walk:lost': walk.md(lost), 'walk:rescued': walk.md(rescued),
        'transitions': transitions(log, lost, rescued),
        'results': R.md_results(runs), 'reclaim': R.md_reclaim(main), 'pool': R.md_pool(main),
        'hist': R.md_hist(main), 'clients': R.md_clients(main), 'audit': md_audit(runs),
        'accesses': main['accesses'], 'frames': main['frames'], 'pages': main['pages'],
        'pool_chunks': main['pool_chunks'], 'fc_low': main['fc_low'], 'fc_high': main['fc_high'],
        'small_fc_high': m.cfg.fc_high,
        'clock_longest': main['kernel'].get('clock_longest', 0),
        'unwritten': main['rw_unmaps_unwritten'], 'rw_unmaps': main['rw_unmaps'],
        'unwritten_pct': f"{100 * main['rw_unmaps_unwritten'] / max(1, main['rw_unmaps']):.1f}",
        'jobs_clock': main['hw']['jobs'], 'jobs_lru': runs[2]['hw']['jobs'],
        'jobs_gap_pct': f"{100 * (main['hw']['jobs'] / runs[2]['hw']['jobs'] - 1):.0f}",
        'incompressible': main['incompressible_pages'],
        'stress': md_stress(nums['stress']), 'capacity': md_capacity(main),
        'scan_max': main['bitmap_scan_max'], 'ro_words': main['build']['ro_chunks'] // 64 + 1,
        'streams_checked': main['audit']['streams_checked'], 'guard_mib': main['audit']['guard_bytes'] >> 20,
        'jobs_without': runs[1]['hw']['jobs'],
        'small_without_pct': f"{100 * (1 - nums['small_accessed']['clear'] / nums['small_accessed']['set']):.1f}",
        'jobs_without_pct': f"{100 * (runs[1]['hw']['jobs'] / main['hw']['jobs'] - 1):.1f}",
    })
    with open(TEMPLATE, encoding='utf-8') as f:
        return fill(f.read(), extra)


def write(reuse=False):
    path = os.path.join(SPEC_DIR, NUMBERS)
    if reuse and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            nums = json.load(f)
    else:
        nums = numbers()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(nums, f, ensure_ascii=False, indent=1, sort_keys=True)
            f.write('\n')
    with open(os.path.join(SPEC_DIR, DOC), 'w', encoding='utf-8') as f:
        f.write(render(nums))
    return os.path.join(SPEC_DIR, DOC), path
