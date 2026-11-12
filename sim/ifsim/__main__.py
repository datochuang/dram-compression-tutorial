"""Command line of the interface simulator.

    python3 sim/run_if.py run --cfg small --set wait_mode=poll
    python3 sim/run_if.py sweep --axis think_ns=20000,2000,500 --axis wait_mode=irq,poll
    python3 sim/run_if.py gen-spec
    python3 sim/run_if.py results
"""
import argparse
import json
import os
import sys
from dataclasses import fields

from . import experiments as E
from . import gen
from . import report as R
from .params import Params
from .spec import SPEC

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SPEC_DIR = os.path.join(ROOT, 'spec')
TYPES = {f.name: f.type for f in fields(Params)}


def value(name, text):
    """Turn the text of one --set or --axis value into the type the parameter has."""
    if name not in TYPES:
        sys.exit(f'unknown parameter {name}; see PARAM_DOC in sim/ifsim/params.py')
    t = TYPES[name]
    if t is int:
        return int(text, 0)
    if t is float:
        return float(text)
    if t is tuple:
        return tuple(int(x, 0) for x in text.split('+') if x)
    return text


def pairs(items):
    out = {}
    for it in items or ():
        k, _, v = it.partition('=')
        out[k] = v
    return out


def cmd_run(a):
    params = {k: value(k, v) for k, v in pairs(a.set).items()}
    m = E.run_one(a.cfg, a.n, a.seed, trace=a.trace, **params)
    if 'stalled' in m:
        sys.exit('stalled: ' + m['stalled'])
    if a.json:
        json.dump(m, sys.stdout, ensure_ascii=False, indent=1)
        return
    print(f'# {a.cfg}，seed {a.seed}，{m["accesses"]} 次 access，{m["wall_s"]} s\n')
    for f in (R.md_run, R.md_budgets, R.md_latency, R.md_parts, R.md_worst, R.md_resources, R.md_clients):
        print(f(m) + '\n')
    if a.rules:
        print(R.md_rules(m, SPEC))


def cmd_sweep(a):
    axes = {k: [value(k, x) for x in v.split(',')] for k, v in pairs(a.axis).items()}
    fixed = {k: value(k, v) for k, v in pairs(a.set).items()}
    rows = E.sweep(axes, fixed, a.cfg, a.n, a.seed, log=lambda s: print(s, file=sys.stderr))
    if a.json:
        json.dump([(kv, E.slim(m)) for kv, m in rows], sys.stdout, ensure_ascii=False, indent=1)
        return
    print(R.md_sweep([(kv, E.slim(m)) for kv, m in rows], list(axes)))


def cmd_gen_spec(a):
    for path in gen.write_spec(a.out):
        print(os.path.relpath(path))


def cmd_results(a):
    data_path = os.path.join(a.out, 'sim-results-v0.json')
    if a.reuse:
        with open(data_path, encoding='utf-8') as f:
            data = json.load(f)
    else:
        data = E.run_all(log=lambda s: print(s, file=sys.stderr), seed=a.seed)
        os.makedirs(a.out, exist_ok=True)
        with open(data_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        with open(data_path, encoding='utf-8') as f:      # read back, so both paths see the same types
            data = json.load(f)
    text = gen.render('sim_results.tmpl.md', R.results_extra(data, SPEC))
    path = os.path.join(a.out, 'sim-results-v0.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print(os.path.relpath(data_path))
    print(os.path.relpath(path))


def main(argv=None):
    ap = argparse.ArgumentParser(prog='run_if.py', description='LZ4 HW/FW interface simulator, SW-leaning design')
    sub = ap.add_subparsers(dest='cmd', required=True)

    def common(p):
        p.add_argument('--cfg', choices=sorted(E.CONFIGS), default='small', help='memory map and workload')
        p.add_argument('--n', type=int, help=f'page accesses; default {E.N_SMALL} for small, {E.N_FULL} for full')
        p.add_argument('--seed', type=int, default=1)
        p.add_argument('--set', action='append', metavar='K=V', help='override one parameter, may repeat')
        p.add_argument('--json', action='store_true', help='print the raw numbers as JSON')

    p = sub.add_parser('run', help='one run, report as Markdown tables')
    common(p)
    p.add_argument('--trace', metavar='FILE', help='write every boundary event as JSON Lines')
    p.add_argument('--rules', action='store_true', help='also print how often each rule was checked')
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser('sweep', help='run the product of the given axes, one table row per run')
    common(p)
    p.add_argument('--axis', action='append', required=True, metavar='K=V1,V2', help='values of one parameter, may repeat')
    p.set_defaults(fn=cmd_sweep)

    p = sub.add_parser('gen-spec', help='write the interface spec and the C header from interface.json')
    p.add_argument('--out', default=SPEC_DIR)
    p.set_defaults(fn=cmd_gen_spec)

    p = sub.add_parser('results', help='run the fixed experiment set and write the results document')
    p.add_argument('--out', default=SPEC_DIR)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--reuse', action='store_true', help='rebuild the document from the stored JSON without running')
    p.set_defaults(fn=cmd_results)

    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    main()
