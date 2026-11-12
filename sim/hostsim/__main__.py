"""Host simulation of the kernel control procedures.

    run      build, boot and run one machine; print the untimed numbers
    walk     print the step log of one real occurrence of each case
    conc     the same kernel run by several threads under many schedules
    gen-doc  write spec/control-procedures-v0.md and its numbers
    gen-deps write spec/kernel-sw-dependency-v0.md, its numbers and the figures in figures/kernel-deps/
    gen-steps write spec/kernel-step-detail-v0.md: every step down to tables, operations and instruction counts
"""
import argparse
import json
import time

from . import deps_doc, doc, report, walk
from .check import audit
from .machine import Machine


def cmd_run(a):
    t = time.time()
    m = Machine(a.cfg, seed=a.seed, codec=a.codec, policy=a.policy, corrupt_every=a.corrupt_every,
                map_accessed=0 if a.no_accessed else 1)
    m.build_image()
    m.boot()
    m.run(a.n or (400_000 if a.cfg == 'full' else 20_000), check_every=a.check_every)
    result = audit(m)
    x = report.metrics(m)
    if a.json:
        print(json.dumps(dict(x, audit=result), ensure_ascii=False, indent=1))
        return
    print(report.text(x))
    if m.st['injected']:
        print(f"  fault injection: {m.st['injected']} streams damaged, {result.get('lost', 0)} pages lost")
    if a.codec == 'cli':
        print(f'  lz4 tool: {m.codec.calls} calls of {m.codec.tool}')
    print(f"  audit passed: {result.get('streams_checked', 0)} stored streams decompressed and compared, "
          f"{result['guard_bytes'] >> 20} MiB outside the compression layer unchanged")
    print(f'  {time.time() - t:.1f} s')


def cmd_walk(a):
    _, log = walk.capture(seed=a.seed)
    sc = walk.scenarios(log)
    sc['lost'] = walk.lost_scenario()
    for name in ([a.case] if a.case else sc):
        print(f'---- {name}')
        print(walk.md_reclaim(sc[name]) if name == 'reclaim' else walk.text(sc[name]))


def cmd_conc(a):
    from . import conc
    t = time.time()
    if a.mutants:
        for r in conc.mutant_table(a.runs):
            end = f"schedule {r['schedule']}: {r['stopped_by']}: {r['text']}" if r['schedule'] else 'NOT STOPPED'
            print(f"  {r['name']:24s} {end}")
    elif a.explore:
        n = conc.explore(a.explore, seed=a.seed, users=a.users, length=a.length)
        print(f'  every schedule with at most {a.explore} interruptions: {n} schedules, all clean')
    else:
        x = conc.survey(a.runs, users=a.users, length=a.length, damage=a.damage)
        print(f"  {x['schedules']} random schedules, {x['steps']} scheduling steps, {x['instructions']} instructions, all clean")
        for key in ('first_touch', 'fault_ro', 'fault_rw', 'spurious', 'lost', 'wait_page_compressing',
                    'wait_page_decompressing', 'wait_frame', 'pin_page', 'jobs', 'jobs_queued_max', 'tlb_flushes',
                    'cache_clean', 'cache_invalidate', 'streams_checked'):
            print(f'    {key:28s}{x.get(key, 0):>9}')
    print(f'  {time.time() - t:.1f} s')


def cmd_doc(a):
    for path in doc.write(reuse=a.reuse):
        print('wrote', path)


def cmd_deps(a):
    for path in deps_doc.write(reuse=a.reuse):
        print('wrote', path)


def cmd_steps(a):
    from . import micro_doc
    for path in micro_doc.write(reuse=a.reuse):
        print('wrote', path)


def main(argv=None):
    p = argparse.ArgumentParser(prog='run_host.py', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    r = sub.add_parser('run')
    r.add_argument('--cfg', choices=('small', 'full'), default='small')
    r.add_argument('--n', type=int, default=0, help='accesses; default 20000 on small, 400000 on full')
    r.add_argument('--seed', type=int, default=1)
    r.add_argument('--policy', choices=('clock', 'lru'), default='clock', help='lru is the ideal that cannot be built')
    r.add_argument('--codec', choices=('lib', 'cli', 'hw'), default='lib',
                   help='cli runs the lz4 tool once per page; hw is the reference model of the LZ4 hardware')
    r.add_argument('--corrupt-every', type=int, default=0, help='damage one stored RW stream every K accesses')
    r.add_argument('--check-every', type=int, default=0, help='audit the whole machine every K accesses')
    r.add_argument('--no-accessed', action='store_true', help='write new PTEs with the accessed bit clear')
    r.add_argument('--json', action='store_true')
    r.set_defaults(fn=cmd_run)
    w = sub.add_parser('walk')
    w.add_argument('case', nargs='?', choices=('first_touch', 'fault_ro', 'fault_rw', 'evict_ro', 'evict_rw_ok',
                                               'evict_rw_incompressible', 'reclaim', 'lost'))
    w.add_argument('--seed', type=int, default=1)
    w.set_defaults(fn=cmd_walk)
    c = sub.add_parser('conc')
    c.add_argument('--runs', type=int, default=300, help='random schedules')
    c.add_argument('--users', type=int, default=3, help='user SW threads')
    c.add_argument('--length', type=int, default=30, help='steps in the script of each thread')
    c.add_argument('--seed', type=int, default=1, help='script used by --explore')
    c.add_argument('--damage', type=float, default=0.0, help='share of script steps that damage a stored stream')
    c.add_argument('--mutants', action='store_true', help='take one thing away at a time and show which check stops it')
    c.add_argument('--explore', type=int, default=0, metavar='K', help='every schedule with at most K interruptions')
    c.set_defaults(fn=cmd_conc)
    d = sub.add_parser('gen-doc')
    d.add_argument('--reuse', action='store_true', help='keep the stored numbers, only render the document again')
    d.set_defaults(fn=cmd_doc)
    g = sub.add_parser('gen-deps')
    g.add_argument('--reuse', action='store_true', help='keep the stored numbers, only render the document and figures again')
    g.set_defaults(fn=cmd_deps)
    s = sub.add_parser('gen-steps')
    s.add_argument('--reuse', action='store_true', help='keep the stored counts, only render the document again')
    s.set_defaults(fn=cmd_steps)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    main()
