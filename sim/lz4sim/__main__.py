"""Command line: python3 -m lz4sim [options]  (run from the sim/ directory, or use run.py)."""
import argparse
import json
import os
import sys
import time

from .config import SystemConfig, SMALL
from .sim import Simulation, VARIANTS, format_report


def _suffixed(path, label):
    root, ext = os.path.splitext(path)
    return f'{root}-{label}{ext or ".jsonl"}'


def main(argv=None):
    p = argparse.ArgumentParser(prog='lz4sim',
                                description='LZ4 DRAM compression system simulator: baseline (hardware-leaning) '
                                            'and software-leaning variants on the same workload.')
    p.add_argument('--variant', choices=VARIANTS + ('both',), default='both')
    p.add_argument('--accesses', type=int, default=200_000, help='page touches to simulate')
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--small', action='store_true', help='1/64-size machine for quick runs')
    p.add_argument('--trace', metavar='PATH', help='JSON Lines trace; with both variants a -<variant> suffix is added')
    p.add_argument('--trace-level', choices=('jobs', 'all'), default='jobs')
    w = p.add_argument_group('workload')
    w.add_argument('--hot-ro', type=int, metavar='PAGES', help='hot RO pages (default 7680 = 30 MiB)')
    w.add_argument('--hot-rw', type=int, metavar='PAGES', help='hot RW pages (default 20480 = 80 MiB)')
    w.add_argument('--p-hot', type=float, default=0.9)
    w.add_argument('--write-frac', type=float, default=0.3)
    w.add_argument('--phase-len', type=int, default=0, help='replace part of the hot set every N accesses')
    w.add_argument('--phase-frac', type=float, default=0.2)
    w.add_argument('--ro-ratio', type=float, default=0.55)
    w.add_argument('--ro-sd', type=float, default=0.18)
    w.add_argument('--rw-ratio', type=float, default=0.45)
    w.add_argument('--rw-sd', type=float, default=0.20)
    w.add_argument('--zero-frac', type=float, default=0.02)
    w.add_argument('--clients', metavar='NAME:SHARE,...', help='user programs that own the pages and their shares '
                   '(default UI:40,MEDIA:27,NET:20,LOG:13; the names are examples)')
    d = p.add_argument_group('design knobs')
    d.add_argument('--raw-store', action='store_true', help='store incompressible RW pages raw in 8 chunks')
    d.add_argument('--limit', type=int, help='COMPRESS give-up threshold in bytes (default 3584)')
    d.add_argument('--fc-low', type=int, help='reclaim starts at this many free frames')
    d.add_argument('--fc-high', type=int, help='reclaim stops at this many free frames')
    d.add_argument('--pool-mib', type=int, help='chunk pool size')
    d.add_argument('--fc-mib', type=int, help='frame cache size')
    o = p.add_argument_group('output')
    o.add_argument('--corrupt-every', type=int, default=0, metavar='N', help='flip a byte in a compressed RW object every N accesses')
    o.add_argument('--sample-every', type=int, default=0, metavar='N')
    o.add_argument('--timeline', metavar='CSV', help='write the samples (needs --sample-every)')
    o.add_argument('--json', metavar='PATH', help='write all statistics as JSON')
    o.add_argument('--dump', metavar='DIR', help='write cot.bin, pool.bin and meta.json at the end')
    o.add_argument('--replay', metavar='HTML', help='write a self-contained 3D replay page of the run(s); '
                   'forces --trace-level all and needs a small machine (use --small)')
    o.add_argument('--replay-start', choices=VARIANTS, metavar='VARIANT',
                   help='with both variants in one replay page: the design it opens in (default baseline)')
    o.add_argument('--replay-fragment', action='store_true',
                   help='write the replay without the html/head/body skeleton, for a host page that adds its own')
    o.add_argument('--lesson', metavar='HTML', help='write a self-contained 3D lesson page that walks through one real job '
                   'of this workload, byte by byte (needs --small); the run itself is separate from the report below')
    o.add_argument('--lesson-scene', default='compress-hw', metavar='SCENE', help='which lesson (default compress-hw)')
    o.add_argument('--lesson-fragment', action='store_true',
                   help='write the lesson without the html/head/body skeleton, for a host page that adds its own')
    o.add_argument('--no-audit', action='store_true')
    args = p.parse_args(argv)

    cfg = SMALL if args.small else SystemConfig()
    over = {}
    if args.raw_store:
        over['rw_raw_store'] = True
    for name, key in (('limit', 'compress_limit'), ('fc_low', 'fc_low'), ('fc_high', 'fc_high'),
                      ('pool_mib', 'pool_mib'), ('fc_mib', 'fc_mib')):
        v = getattr(args, name)
        if v is not None:
            over[key] = v
    if over:
        cfg = cfg.with_(**over)

    hot_ro = args.hot_ro if args.hot_ro is not None else (100 if args.small else 7680)
    hot_rw = args.hot_rw if args.hot_rw is not None else (200 if args.small else 20480)
    wl = dict(hot_ro_pages=hot_ro, hot_rw_pages=hot_rw, p_hot=args.p_hot, write_frac=args.write_frac,
              phase_len=args.phase_len, phase_frac=args.phase_frac, ro_ratio=args.ro_ratio,
              ro_sd=args.ro_sd, rw_ratio=args.rw_ratio, rw_sd=args.rw_sd, zero_frac=args.zero_frac)
    if args.clients:
        from .workload import parse_clients
        wl['clients'] = parse_clients(args.clients)

    variants = VARIANTS if args.variant == 'both' else (args.variant,)
    if args.replay:
        from .replay import check_size
        check_size(cfg, args.accesses)
        args.trace_level = 'all'
    runs = []
    replays = []
    for v in variants:
        tp = None
        if args.trace:
            tp = args.trace if len(variants) == 1 else _suffixed(args.trace, v)
        t0 = time.time()
        sim = Simulation(v, cfg, args.seed, tp, args.trace_level, wl, args.corrupt_every,
                         keep_trace=bool(args.replay))
        sim.build()
        sim.boot()
        sim.run(args.accesses, args.sample_every)
        if not args.no_audit:
            sim.audit()
        s = sim.stats()
        s['#simulator'] = None
        s['wall_seconds'] = round(time.time() - t0, 1)
        s['trace_events'] = sim.trace.n
        sim.close()
        if args.replay:
            from .replay import run_data
            replays.append(run_data(sim, s))
        if args.timeline and args.sample_every:
            sim.write_timeline(args.timeline if len(variants) == 1 else _suffixed(args.timeline, v))
        if args.dump:
            sim.dump(args.dump if len(variants) == 1 else f'{args.dump}-{v}')
        runs.append((v, s))
        print(f'[{v}] {args.accesses:,} accesses in {s["wall_seconds"]}s', file=sys.stderr)

    print(format_report(runs))
    if args.replay:
        from .replay import write_html
        start = args.replay_start if args.replay_start in variants else None
        size = write_html(args.replay, replays, fragment=args.replay_fragment, start=start)
        print(f'[replay] {args.replay} ({size / 1e6:.1f} MB)', file=sys.stderr)
    if args.lesson:
        from . import lesson
        data = lesson.capture(args.lesson_scene, cfg, args.seed, args.accesses, wl)
        size = lesson.write_html(args.lesson, data, fragment=args.lesson_fragment)
        print(f'[lesson] {args.lesson} ({size / 1e3:.0f} kB): {data["scene"]}, page {(data.get("victim") or data["pg"])["h"]:#x}, '
              f'access {data["req"]["access_no"]}', file=sys.stderr)
    if args.json:
        with open(args.json, 'w') as f:
            json.dump({label: {k: v for k, v in s.items() if not k.startswith('#')} for label, s in runs},
                      f, indent=1)


if __name__ == '__main__':
    main()
