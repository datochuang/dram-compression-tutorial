"""Model experiment: conc.py with the TLB refill and the TLB clearing split into steps (conc.SplitTlb).

The clearing is ONE EXAMPLE SCHEME (a request to each core or hardware thread, each clears its own TLB,
the initiator waits holding mm_lock). The platform's mechanism for clearing another core's TLB is not
known; this shows where the current kernel design has holes under each assumption, it does not pick one.

    cd sim && python3 -m hostsim.tlbsplit            # the whole table, about four minutes
    cd sim && python3 -m hostsim.tlbsplit --quick    # fewer schedules

For every combination: random schedules with 2 and with 3 user threads, then every schedule with at most
one interruption (conc.explore). The first failure of each is kept, with the TLB events that led to it.
"""
import argparse
import itertools
import time

from . import conc

BASE = [conc.SplitTlb(delivery=d, lock_wait_irq=a, refill_irq=c)
        for d, a, c in itertools.product(('core', 'thread'), (True, False), (True, False))]
FIXES = ([conc.SplitTlb(delivery=d, refill_irq=c, recheck=True) for d, c in itertools.product(('core', 'thread'), (True, False))]
         + [conc.SplitTlb(delivery=d, lock_wait_irq=a, refill_locked=True, isr_irq=i)
            for d, a, i in itertools.product(('core', 'thread'), (True, False), (False, True))])
RANDOM = (('users=2', dict(users=2)), ('users=3', dict(users=3)),
          ('wide users=3', dict(users=3, wide=True)), ('wide users=4', dict(users=4, wide=True)))
EXPLORE = (('explore users=2', dict(bound=1, seed=1, users=2, length=8)),
           ('explore users=3', dict(bound=1, seed=3, users=3, length=30)))


class WideWindows(conc.RandomChooser):
    """Random schedules in which a hardware thread inside a refill is usually overtaken by the others:
    the gaps between refill steps A, B and C get wide, so races in them show up in fewer schedules."""

    def __init__(self, seed, overtake=0.9):
        super().__init__(seed)
        self.overtake = overtake

    def pick(self, step, ready, current):
        others = [t for t in ready if not t.refilling]
        if others and len(others) < len(ready) and self.rng.random() < self.overtake:
            return self.rng.choice(others)
        return super().pick(step, ready, current)


def outcome(e):
    return 'ok' if e is None else type(e).__name__


def story(e):
    """The TLB events behind a failure, for the page it is about: [(step, task, text)]."""
    ev = getattr(e, 'tlb_events', [])
    h = getattr(e, 'page', None)
    if h is None:
        return []
    mine = [(s, who, text) for s, who, page, text in ev if page == h]
    start = 0
    if isinstance(e, conc.Deadlock):
        start = max((i for i, x in enumerate(mine) if 'invalid' in x[2]), default=0)
    else:                                                 # from step A of the refill that wrote the stale entry
        mark = f'core {e.core} TLB {h:#x} -> {e.pa:#x}'
        bs = [i for i, x in enumerate(mine) if 'refill B' in x[2] and mark in x[2]]
        if bs:
            who = mine[bs[-1]][1]
            start = max((i for i, x in enumerate(mine[:bs[-1]]) if 'refill A' in x[2] and x[1] == who), default=0)
    return mine[start:]


def interleaving(e, keep=10):
    """story(e) in a few lines, and what stopped the run."""
    lines = [f'step {s:5d}  {who:11s} {text}' for s, who, text in story(e)][-keep:]
    return lines + [f'-> {type(e).__name__}: {str(e).splitlines()[0][:240]}']


def first_random(o, runs, wide=False, **kw):
    for seed in range(1, runs + 1):
        try:
            conc.one(seed, tlb=o, chooser=WideWindows(seed) if wide else None, **kw)
        except Exception as e:
            return seed, e
    return None


def first_explore(o, **kw):
    try:
        n = conc.explore(tlb=o, **kw)
        return None, n
    except Exception as e:
        plan = next((x for x in getattr(e, '__notes__', []) if x.startswith('schedule')), '')
        return (plan, e), None


def run(o, runs=100, explore=True):
    row = {'combo': o.label(), 'option': o, 'cases': {}}
    for name, kw in RANDOM:
        hit = first_random(o, runs, **kw)
        row['cases'][name] = (outcome(hit[1]) if hit else 'ok', f'seed {hit[0]}' if hit else f'{runs} seeds',
                              hit[1] if hit else None)
    if explore:
        for name, kw in EXPLORE:
            hit, n = first_explore(o, **kw)
            row['cases'][name] = (outcome(hit[1]) if hit else 'ok', hit[0] if hit else f'{n} schedules',
                                  hit[1] if hit else None)
    return row


def table(options=BASE + FIXES, runs=100, explore=True):
    return [run(o, runs, explore) for o in options]


def text(rows):
    out = []
    for r in rows:
        out.append(r['combo'])
        shown = []
        for name, (what, where, e) in r['cases'].items():
            out.append(f'    {name:18s} {what:10s} {where}')
            if e is not None:
                lines = interleaving(e)
                key = [x[1:] for x in story(e)] or lines             # the same story at other step numbers
                if key not in shown:
                    shown.append(key)
                    out += ['        ' + line for line in lines]
    return '\n'.join(out)


def main(argv=None):
    p = argparse.ArgumentParser(prog='python3 -m hostsim.tlbsplit', description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--quick', action='store_true', help='30 random seeds per case and no exploration')
    p.add_argument('--fixes-only', action='store_true')
    a = p.parse_args(argv)
    t = time.time()
    print(text(table(FIXES if a.fixes_only else BASE + FIXES, runs=30 if a.quick else 100, explore=not a.quick)))
    print(f'{time.time() - t:.0f} s')


if __name__ == '__main__':
    main()
