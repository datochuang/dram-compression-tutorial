"""3D replay exporter: one self-contained HTML page per simulation.

The page embeds the full trace (level "all") of one or both variants and a
viewer. There is one viewer for both designs: the same scene, characters and
LZ4 HW staging, with the SRAM stack tower drawn for the hardware-leaning design
and the bitmap wall for the software-leaning one. With both runs embedded the
DESIGN switch at the top changes design at the same access; `start` (or
?design=software in the URL) picks the design the page opens in. The viewer that rebuilds the machine state event by event: the frame cache, the
chunk pool, the COT, the free-chunk stack or the bitmap, and two characters,
the kernel and the accelerator, that act out every trace event. The viewer is
plain JavaScript on three.js; its sources are in replay_assets/.

The scene shows every frame and every chunk as an object, so it is meant for
small machines (--small). A full-size machine needs a level-of-detail view
that this exporter does not have yet.
"""
import json
import os

ASSETS = os.path.join(os.path.dirname(__file__), 'replay_assets')
JS_FILES = ('model.js', 'chars.js', 'scene.js', 'stage.js', 'ui.js')
THREE_URL = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js'
MAX_CHUNKS = 40_000
MAX_ACCESSES = 60_000
TITLES = {None: 'LZ4 Replay 3D', 'baseline': 'LZ4 Replay HW-leaning', 'software': 'LZ4 Replay SW-leaning'}


def check_size(cfg, accesses):
    if cfg.pool_chunks > MAX_CHUNKS:
        raise SystemExit(f'--replay draws every chunk and frame as an object; {cfg.pool_chunks:,} chunks is too '
                         f'many (limit {MAX_CHUNKS:,}). Use --small.')
    if accesses > MAX_ACCESSES:
        raise SystemExit(f'--replay embeds the whole trace; use at most {MAX_ACCESSES:,} accesses.')


def run_data(sim, stats):
    """Split the kept trace into the boot part and one scene per page access."""
    cfg = sim.cfg
    boot, scenes, cur = [], [], []
    booted = False
    for rec in sim.trace.records:
        if not booted:
            if rec['ev'] == 'cot' and rec.get('who') == 'build':
                rec = {k: v for k, v in rec.items() if k != 'hex'}
            boot.append(rec)
            booted = rec['ev'] == 'boot'
            continue
        cur.append(rec)
        if rec['ev'] == 'access':
            scenes.append(cur)
            cur = []
    if cur:
        if scenes:
            scenes[-1].extend(cur)
        else:
            scenes.append(cur)
    meta = {
        'variant': sim.variant, 'seed': sim.seed, 'page': cfg.page, 'chunk': cfg.chunk,
        'pages': cfg.pages, 'rw_pages': cfg.rw_pages, 'ro_first': cfg.ro_first,
        'data_pages': cfg.data_pages, 'pool_chunks': cfg.pool_chunks, 'frames': cfg.frames,
        'cot_base': cfg.cot_base, 'pool_base': cfg.pool_base, 'fc_base': cfg.fc_base,
        'compress_limit': cfg.compress_limit_for_rw(), 'fc_low': cfg.fc_low, 'fc_high': cfg.fc_high,
        'sram_cap': cfg.sram_cap, 'refill_below': cfg.refill_below, 'spill_above': cfg.spill_above,
        'list_group': cfg.list_group, 'accesses': sim.accesses, 'clients': sim.wl.clients,
        'stats': {k: stats[k] for k in ('faults', 'faults_ro', 'faults_rw', 'first_touch', 'hits',
                                         'ro_drops', 'rw_compress_ok', 'rw_incompressible', 'jobs',
                                         'lost_pages') if k in stats},
    }
    return {'meta': meta, 'boot': boot, 'scenes': scenes}


def _read(name):
    with open(os.path.join(ASSETS, name), encoding='utf-8') as f:
        return f.read()


def render(runs, fragment=False, start=None):
    """fragment=True leaves out doctype/html/head/body, for hosts that add their own skeleton.

    start names the design the page opens in ('baseline' or 'software'); None opens the first run.
    """
    have = [r['meta']['variant'] for r in runs]
    if start is not None and start not in have:
        raise ValueError(f'start={start!r} is not among the embedded runs {have}')
    doc = {'runs': runs}
    if start is not None:
        doc['start'] = start
    data = json.dumps(doc, separators=(',', ':')).replace('</', '<\\/')
    shell = _read('shell.html')
    title = TITLES[start if start is not None else (have[0] if len(have) == 1 else None)]
    shell = shell.replace('<title>LZ4 Replay 3D</title>', f'<title>{title}</title>', 1)
    js = '\n'.join(_read(n) for n in JS_FILES)
    body = (shell
            + f'\n<script src="{THREE_URL}"></script>\n'
            + f'<script type="application/json" id="replay-data">{data}</script>\n'
            + f'<script>\n{js}\n</script>\n')
    if fragment:
        return body
    return ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
            '</head>\n<body>\n' + body + '</body>\n</html>\n')


def write_html(path, runs, fragment=False, start=None):
    html = render(runs, fragment, start)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    return len(html.encode('utf-8'))
