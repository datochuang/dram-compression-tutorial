"""Reference models of the LZ4 hardware: what the RTL has to reproduce.

    study    measure what the encoder parameters cost and buy, on four sets of pages
    vectors  write the test vectors for the RTL test bench as files
    gen-doc  write spec/lz4-hw-design-spec-v0.md and the numbers beside it
"""
import argparse
import json
import time

from . import doc, study, vectors


def cmd_study(a):
    t = time.time()
    out = study.run(a.n, a.seed)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
        return
    for name, s in out['sets'].items():
        print(f'\n{study.SET_ZH[name]}，{a.n} 個 page\n')
        print(doc.md_study(s['rows']))
    print('\n估計的 cycle 數，平均 / p50 / p99 / 最大\n')
    print(doc.md_cycles(out['sets']))
    print(f'\n{time.time() - t:.1f} s')


def cmd_vectors(a):
    n = vectors.write(a.out)
    print(f"wrote {n['encode']} encoder, {n['decode_only']} decoder-only, {n['decode_bad']} bad-stream and {n['jobs']} job vectors to {a.out}")


def cmd_doc(a):
    for path in doc.write(reuse=a.reuse, n=a.n, seed=a.seed):
        print('wrote', path)


def main(argv=None):
    p = argparse.ArgumentParser(prog='run_hwref.py', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('study')
    s.add_argument('--n', type=int, default=300, help='pages per set')
    s.add_argument('--seed', type=int, default=1)
    s.add_argument('--json', action='store_true')
    s.set_defaults(fn=cmd_study)
    v = sub.add_parser('vectors')
    v.add_argument('--out', required=True, help='directory to write into')
    v.set_defaults(fn=cmd_vectors)
    g = sub.add_parser('gen-doc')
    g.add_argument('--reuse', action='store_true', help='keep the stored study numbers, rebuild the text only')
    g.add_argument('--n', type=int, default=300, help='pages per set of the study')
    g.add_argument('--seed', type=int, default=1)
    g.set_defaults(fn=cmd_doc)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == '__main__':
    main()
