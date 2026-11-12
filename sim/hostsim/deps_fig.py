"""Figures of the dependency analysis, as SVG text, all drawn from deps.py.

    graph(case, w)     the dependency graph of one case: columns say who runs a step and whether the lock is
                       held, rows follow the order of kernel.py, arrows are the edges left after reduction
    timeline(w)        the main cases on one time axis, every stretch coloured by what it keeps busy
    together(w)        three operations at once and where they stand still for each other

Text in the figures is English. Times are the assumed step costs of ifsim.params, never measurements of a chip.
"""
import os
from collections import defaultdict
from html import escape

from . import deps

HERE = os.path.dirname(os.path.abspath(__file__))
FIG_DIR = os.path.normpath(os.path.join(HERE, '..', '..', 'figures', 'kernel-deps'))

INK, MUTED, FAINT, SURFACE = '#0b0b0b', '#52514e', '#c9c8c2', '#fcfcfb'
COLOR = {'cpu': '#2a78d6', 'lock': '#eb6834', 'kernel': '#1baf7a', 'hw': '#eda100', 'notify': '#e87ba4'}
KIND_EN = {'cpu': 'CPU: exception entry and return', 'lock': 'kernel, mm_lock held', 'kernel': 'kernel, lock not held',
           'hw': 'LZ4 HW job', 'notify': 'interrupt, handler, wake-up of the thread'}
LANES = (('cpu', 'CPU'), ('lock', 'Kernel, mm_lock held'), ('kernel', 'Kernel, lock not held'), ('hw', 'LZ4 HW'))
CASE_EN = {
    'first_touch': 'first touch of an RW page (no LZ4 job)',
    'fault_ro': 'page fault on a compressed RO page',
    'fault_rw': 'page fault on a compressed RW page',
    'fault_rescue': 'page fault, LZ4 HW fails, the kernel decodes the page itself',
    'fault_lost': 'page fault, the stored stream is damaged',
    'evict_ro': 'reclaimer pushes out an RO page (no LZ4 job)',
    'evict_rw': 'reclaimer pushes out an RW page',
    'evict_rw_incompressible': 'reclaimer meets an RW page that does not fit 7 chunks',
}
FONT = 'font-family="Helvetica Neue, Helvetica, Arial, sans-serif"'


def tint(hex_, k=0.80):
    """The colour mixed with the surface: k of surface, the rest of the colour."""
    c = [int(hex_[i:i + 2], 16) for i in (1, 3, 5)]
    s = [int(SURFACE[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{round(a * (1 - k) + b * k):02x}' for a, b in zip(c, s))


def text(x, y, s, size=13, fill=INK, anchor='start', weight='normal', extra=''):
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}" '
            f'font-weight="{weight}" {extra}>{escape(str(s))}</text>')


def tw(s, size, bold=False):
    """Width of a string in px, estimated: capitals and digits are wider than the rest."""
    return sum(0.70 if ch.isupper() or ch in 'mw_' else 0.30 if ch in ' il.,:[]' else 0.56 for ch in s) \
        * size * (1.06 if bold else 1.0)


HALO = f'stroke="{SURFACE}" stroke-width="4" paint-order="stroke" stroke-linejoin="round"'


def wrap(label, width, size=12.5):
    """Break a label into lines no wider than width px, at spaces."""
    lines, cur = [], ''
    for word in label.split():
        if cur and tw(cur + ' ' + word, size) > width:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + ' ' + word).strip()
    return lines + [cur]


def svg(w, h, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}" '
            f'role="img" aria-label="{escape(label)}" {FONT}>\n'
            '<defs>\n'
            f'<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
            f'<path d="M0,1 L10,5 L0,9 z" fill="{MUTED}"/></marker>\n'
            f'<marker id="arrow-bold" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto">'
            f'<path d="M0,1 L10,5 L0,9 z" fill="{INK}"/></marker>\n'
            f'<pattern id="standstill" width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            f'<rect width="7" height="7" fill="#eeede8"/><line x1="0" y1="0" x2="0" y2="7" stroke="#8a8983" '
            f'stroke-width="2"/></pattern>\n'
            '</defs>\n'
            f'<rect width="{w:.0f}" height="{h:.0f}" fill="{SURFACE}"/>\n' + '\n'.join(body) + '\n</svg>\n')


# ---------------------------------------------------------------- one case as a graph
NW, NH, HGAP, PAD, GUT, ROWH, TOP = 156, 54, 20, 12, 40, 100, 156


def graph(case, w):
    ns, sec, row = deps.nodes(case), deps.sections(case), deps.layers(case)
    E, sch = deps.reduced(case), deps.schedule(case, w)
    kind = {n: deps.kind(case, n) for n in ns}
    lane = {n: 'kernel' if kind[n] == 'notify' else kind[n] for n in ns}
    lanes = [(k, name) for k, name in LANES if any(lane[n] == k for n in ns)]

    # how many steps stand side by side in each lane decides its width
    cell = defaultdict(list)
    for n in ns:
        cell[lane[n], row[n]].append(n)
    wide = {k: max(len(v) for (lk, _), v in cell.items() if lk == k) for k, _ in lanes}
    x0, left, gutters = {}, GUT, [GUT / 2]
    for k, _ in lanes:
        x0[k] = left
        left += wide[k] * NW + (wide[k] - 1) * HGAP + 2 * PAD
        gutters.append(left + GUT / 2)
        left += GUT
    W = left
    lane_w = {k: wide[k] * NW + (wide[k] - 1) * HGAP + 2 * PAD for k, _ in lanes}
    pos = {}
    for (k, r), members in cell.items():
        used = len(members) * NW + (len(members) - 1) * HGAP
        start = x0[k] + (lane_w[k] - used) / 2
        for i, n in enumerate(members):
            pos[n] = (start + i * (NW + HGAP), TOP + r * ROWH)
    rows = max(row.values()) + 1
    bottom = TOP + rows * ROWH - (ROWH - NH)
    H = bottom + 150

    out = []
    title = f'{case}: {CASE_EN[case]}'
    out.append(text(GUT, 34, title, 21, weight='bold'))
    out.append(text(GUT, 58, f'{len(ns)} steps. One after the other: {sch["serial"]} ns. Longest path through the '
                             f'graph: {sch["span"]} ns. Assumed step costs, not measurements.', 13.5, MUTED))
    # lanes
    for k, name in lanes:
        out.append(f'<rect x="{x0[k]:.1f}" y="{TOP - 68}" width="{lane_w[k]:.1f}" height="{bottom - TOP + 86:.1f}" '
                   f'rx="8" fill="{tint(COLOR[k], 0.93)}"/>')
        out.append(f'<rect x="{x0[k]:.1f}" y="{TOP - 68}" width="{lane_w[k]:.1f}" height="5" rx="2" fill="{COLOR[k]}"/>')
        out.append(text(x0[k] + lane_w[k] / 2, TOP - 44, name, 14, anchor='middle', weight='bold'))
    # critical sections as bands in the lock lane
    band, band_labels = {}, []
    for letter in sorted({s for s in sec.values() if s}):
        rs = [row[n] for n in ns if sec[n] == letter]
        y1, y2 = TOP + min(rs) * ROWH - 22, TOP + max(rs) * ROWH + NH + 10
        band[letter] = (x0['lock'] + 4, y1, lane_w['lock'] - 8, y2 - y1)
        out.append(f'<rect x="{x0["lock"] + 4:.1f}" y="{y1:.1f}" width="{lane_w["lock"] - 8:.1f}" height="{y2 - y1:.1f}" '
                   f'rx="6" fill="{tint(COLOR["lock"], 0.80)}" stroke="{COLOR["lock"]}" stroke-width="1"/>')
        band_labels.append(text(x0['lock'] + 12, y1 + 14, f'critical section {letter}', 11.5, MUTED, weight='bold',
                                extra=HALO.replace(SURFACE, tint(COLOR['lock'], 0.80))))

    # ---- edges: straight down where they can, through the space between rows and between lanes where they cannot
    drawn = {e: v for e, v in E.items() if v['kind'] != 'return'}
    outs, ins = defaultdict(list), defaultdict(list)
    for a, b in drawn:
        outs[a].append(b)
        ins[b].append(a)

    def ports(n, others):
        """x of the port of n for each node of others, spread over the middle of the node."""
        order = sorted(others, key=lambda m: (pos[m][0], row[m]))
        step = min(26, (NW - 40) / max(1, len(order)))
        first = pos[n][0] + NW / 2 - step * (len(order) - 1) / 2
        return {m: first + i * step for i, m in enumerate(order)}
    px_out = {n: ports(n, outs[n]) for n in ns}
    px_in = {n: ports(n, ins[n]) for n in ns}
    gap_used, gut_used = Counter_(), Counter_()

    def gap_y(r, key):
        """A height of its own in the space under row r."""
        i = gap_used.next(r)
        return TOP + r * ROWH + NH + 12 + (i % 6) * 5

    def on_critical(a, b):
        return (sch['slack'][a] == 0 and sch['slack'][b] == 0
                and sch['est'][a] + deps.cost(a, w) == sch['est'][b])

    paths = []
    for (a, b), v in sorted(drawn.items(), key=lambda kv: (row[kv[0][0]], pos[kv[0][0]][0], row[kv[0][1]])):
        xa, ya = px_out[a][b], pos[a][1] + NH
        xb, yb = px_in[b][a], pos[b][1]
        if row[b] == row[a] + 1:
            if abs(xa - xb) < 0.5:
                pts = [(xa, ya), (xb, yb - 1)]
            else:
                y = gap_y(row[a], (a, b))
                pts = [(xa, ya), (xa, y), (xb, y), (xb, yb - 1)]
        else:
            between = [pos[m][0] for m in ns if row[a] < row[m] < row[b]]

            def clear(x):
                return all(not (nx - 7 <= x <= nx + NW + 7) for nx in between)
            # a way down that meets no step: the port itself, the space between two steps of a row, or a lane boundary
            slots = [(xa, 0), (xb, 0)] + [(nx - HGAP / 2, 4) for nx in between] + \
                    [(nx + NW + HGAP / 2, 4) for nx in between] + [(gx, 6) for gx in gutters]
            g, spread = min((s for s in slots if clear(s[0])), key=lambda s: abs(s[0] - xa) + abs(s[0] - xb))
            i = gut_used.next(round(g))
            gx = g + (0, 1, -1, 2, -2)[i % 5] * spread
            y1, y2 = gap_y(row[a], (a, b)), gap_y(row[b] - 1, (a, b))
            pts = [(xa, ya), (xa, y1), (gx, y1), (gx, y2), (xb, y2), (xb, yb - 1)]
            pts = [p for i, p in enumerate(pts) if i == 0 or p != pts[i - 1]]
        d = 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x, y in pts)
        bold = on_critical(a, b)
        why = v['rule'].why if v['rule'] else 'needs ' + ', '.join(v['via'])
        style = (f'stroke="{INK}" stroke-width="2.6" marker-end="url(#arrow-bold)"' if bold else
                 f'stroke="{MUTED}" stroke-width="1.3" marker-end="url(#arrow)"')
        dash = ' stroke-dasharray="6 4"' if v['kind'] == 'rule' else ''
        paths.append((bold, f'<path d="{d}" fill="none" {style}{dash}><title>{escape(a)} before {escape(b)}: '
                            f'{escape(why)}</title></path>'))
    out += [p for bold, p in sorted(paths, key=lambda p: p[0])]

    # the way back out of the kernel: one arrow for all the steps that only have to be finished by then
    last = next((n for n in ('eret', 'kill') if n in ns), None)
    if last and any(v['kind'] == 'return' for v in E.values()):
        letter = max(band)
        bx, by, bw, bh = band[letter]
        xe, ye = pos[last][0] + NW / 2, pos[last][1]
        y = by + bh + 14
        bold = any(v['kind'] == 'return' and on_critical(a, b) for (a, b), v in E.items())
        style = (f'stroke="{INK}" stroke-width="2.6" marker-end="url(#arrow-bold)"' if bold else
                 f'stroke="{MUTED}" stroke-width="1.3" marker-end="url(#arrow)"')
        out.append(f'<path d="M{bx + 40:.1f},{by + bh:.1f} L{bx + 40:.1f},{y:.1f} L{xe:.1f},{y:.1f} L{xe:.1f},{ye - 1:.1f}" '
                   f'fill="none" {style}/>')
        out.append(text(bx + 48, y + 14, f'every step of section {letter} is done', 11.5, MUTED, extra=HALO))
    out += band_labels

    # nodes
    for n in ns:
        x, y = pos[n]
        c, crit = COLOR[kind[n]], sch['slack'][n] == 0
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{NW}" height="{NH}" rx="7" fill="{tint(c, 0.62)}" '
                   f'stroke="{INK if crit else c}" stroke-width="{2.6 if crit else 1.2}"><title>{escape(n)}</title></rect>')
        lines = wrap(deps.STEPS[n].label, NW - 14)
        cst = deps.cost(n, w)
        tag = '? ns' if deps.STEPS[n].unknown else f'{cst} ns' if cst else ''
        ty = y + (20 if len(lines) == 1 else 17)
        for i, ln in enumerate(lines[:2]):
            out.append(text(x + NW / 2, ty + i * 15, ln, 12.5, anchor='middle'))
        if tag:
            out.append(text(x + NW - 7, y + NH - 6, tag, 11.5, MUTED, anchor='end', weight='bold'))
        if case == 'fault_rw' and n in deps.ONLY_RW:
            out.append(text(x + 7, y + NH - 6, 'RW page only', 10.5, MUTED))

    # legend
    ly = bottom + 46
    out.append(f'<line x1="{GUT}" y1="{ly}" x2="{GUT + 46}" y2="{ly}" stroke="{MUTED}" stroke-width="1.3" marker-end="url(#arrow)"/>')
    out.append(text(GUT + 56, ly + 4, 'needs what the step above produced', 12.5))
    out.append(f'<line x1="{GUT}" y1="{ly + 24}" x2="{GUT + 46}" y2="{ly + 24}" stroke="{MUTED}" stroke-width="1.3" '
               f'stroke-dasharray="6 4" marker-end="url(#arrow)"/>')
    out.append(text(GUT + 56, ly + 28, 'ordering rule (reasons in the document)', 12.5))
    out.append(f'<line x1="{GUT}" y1="{ly + 48}" x2="{GUT + 46}" y2="{ly + 48}" stroke="{INK}" stroke-width="2.6" '
               f'marker-end="url(#arrow-bold)"/>')
    out.append(text(GUT + 56, ly + 52, 'longest path: it sets the time; steps on it have a thick border', 12.5))
    out.append(text(GUT, ly + 78, 'Number in a step: assumed cost. "? ns": cost not in the model. No number: a few '
                                  'instructions, not costed.', 12.5, MUTED))
    return svg(max(W, 760), H, out, f'Dependency graph of {case}: {CASE_EN[case]}')


class Counter_:
    """Hands out 0, 1, 2 ... per key."""

    def __init__(self):
        self.n = defaultdict(int)

    def next(self, key):
        self.n[key] += 1
        return self.n[key] - 1


# ---------------------------------------------------------------- time axes
def _axis(out, x0, x1, y0, y1, t_max, step=1000):
    scale = (x1 - x0) / t_max
    for t in range(0, int(t_max) + 1, step):
        x = x0 + t * scale
        out.append(f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y1}" stroke="{FAINT}" stroke-width="1"/>')
        out.append(text(x, y1 + 16, f'{t // 1000} µs' if t else '0', 11.5, MUTED, anchor='middle'))
    return scale


def _bar(out, segs, x0, y, h, scale, t0=0):
    """One operation as a row of segments with a 2 px gap between neighbours; a label where it fits."""
    for k, step, a, b in segs:
        xa, xb = x0 + (a - t0) * scale, x0 + (b - t0) * scale
        wpx = max(1.5, xb - xa - 2)
        if k.startswith('wait_'):
            what = {'wait_lock': 'waits for mm_lock', 'wait_engine': 'waits for the LZ4 engine'}[k]
            out.append(f'<rect x="{xa:.1f}" y="{y}" width="{wpx:.1f}" height="{h}" rx="3" fill="url(#standstill)" '
                       f'stroke="#8a8983" stroke-width="1"><title>{what}: {b - a} ns</title></rect>')
            label = f'{what} {b - a} ns'
            if wpx < tw(label, 12, True) + 8:
                out.append(text(xa, y - 6, label, 11.5, MUTED, extra=HALO))
                label = ''
        else:
            name = deps.STEPS[step].label
            out.append(f'<rect x="{xa:.1f}" y="{y}" width="{wpx:.1f}" height="{h}" rx="3" fill="{COLOR[k]}">'
                       f'<title>{escape(name)}: {b - a} ns ({KIND_EN[k]})</title></rect>')
            short = {'exception': 'exception', 'eret': 'return', 'notify': 'interrupt + wake-up',
                     'hw_decompress': 'DECOMPRESS', 'hw_compress': 'COMPRESS', 'hw_fail': 'DECOMPRESS',
                     'zero_frame': 'zero fill', 'tlb_inval': 'TLB inval', 'pick_victim': 'scan',
                     'reserve': 'reserve'}.get(step, '')
            label = f'{short} {b - a}' if short else ''
            if wpx < tw(label, 12, True) + 8:
                label = short if wpx >= tw(short, 12, True) + 8 else ''
        if label:
            out.append(text(xa + wpx / 2, y + h / 2 + 4.5, label, 12, anchor='middle', weight='bold'))


def _legend(out, x, y, kinds, waits=False):
    for k in kinds:
        out.append(f'<rect x="{x}" y="{y - 11}" width="14" height="14" rx="3" fill="{COLOR[k]}"/>')
        out.append(text(x + 20, y + 1, KIND_EN[k], 12.5))
        x += 44 + tw(KIND_EN[k], 12.5)
    if waits:
        out.append(f'<rect x="{x}" y="{y - 11}" width="14" height="14" rx="3" fill="url(#standstill)" stroke="#8a8983"/>')
        out.append(text(x + 20, y + 1, 'stands still, waits for another operation', 12.5))


TIMELINE = ('first_touch', 'fault_ro', 'fault_rw', 'evict_ro', 'evict_rw')


def timeline(w):
    W, x0, x1, top, rowh, h = 1180, 170, 1040, 150, 74, 34
    ops = {c: deps.overlap([(c, c, 0)], w)[0] for c in TIMELINE}
    t_max = 10000
    out = [text(30, 36, 'Where the time of one operation goes', 21, weight='bold'),
           text(30, 60, 'Each row is one operation running alone, steps in the order kernel.py runs them. '
                        'Assumed step costs, not measurements of a chip.', 13.5, MUTED)]
    _legend(out, 30, 92, ('cpu', 'lock', 'kernel'))
    _legend(out, 30, 116, ('hw', 'notify'))
    bottom = top + len(TIMELINE) * rowh
    scale = _axis(out, x0, x1, top - 8, bottom - 14, t_max)
    for i, c in enumerate(TIMELINE):
        y = top + i * rowh
        o = ops[c]
        out.append(text(30, y + 15, c, 14, weight='bold'))
        out.append(text(30, y + 32, f'{o["end"]} ns', 12.5, MUTED))
        _bar(out, o['segs'], x0, y, h, scale)
        lock = sum(b - a for k, _, a, b in o['segs'] if k == 'lock')
        out.append(text(x0 + o['end'] * scale + 8, y + h / 2 + 4.5, f'mm_lock held {lock} ns', 12, MUTED, extra=HALO))
        # steps the model has no cost for: a mark at the moment they happen
        t, marks = 0, []
        for s in deps.nodes(c):
            if deps.STEPS[s].unknown:
                marks.append((t, s))
            t += deps.cost(s, w)
        for t, s in marks:
            x = x0 + t * scale
            out.append(f'<path d="M{x:.1f},{y - 3} l-5,-9 l10,0 z" fill="{INK}"><title>{escape(deps.STEPS[s].label)}: '
                       f'cost not in the model</title></path>')
            out.append(text(x + 8, y - 5, deps.STEPS[s].label + ', ? ns', 11.5, MUTED, extra=HALO))
    out.append(text(30, bottom + 30, 'Triangle: a step whose cost the model does not have. Steps of a few '
                                     'instructions have no width here.', 12.5, MUTED))
    return svg(W, bottom + 50, out, 'Time of each kernel operation running alone, by what it keeps busy')


def together(w):
    W, x0, x1, top, rowh, h = 1180, 190, 1150, 150, 70, 34
    ops = deps.overlap(deps.SHOWN_TOGETHER, w)
    t_max = (max(o['end'] for o in ops) // 1000 + 1) * 1000
    out = [text(30, 36, 'Three operations at once: where they stand still for each other', 21, weight='bold'),
           text(30, 60, 'A constructed moment: two faults arrive while the reclaimer compresses a page. '
                        'Each runs on a core of its own. Assumed step costs.', 13.5, MUTED)]
    _legend(out, 30, 92, ('cpu', 'lock', 'kernel'))
    _legend(out, 30, 116, ('hw', 'notify'), waits=True)
    bottom = top + (len(ops) + 2) * rowh
    scale = _axis(out, x0, x1, top - 8, bottom - 14, t_max)
    for i, o in enumerate(ops):
        y = top + i * rowh
        alone = deps.schedule(o['case'], w)['serial']
        out.append(text(30, y + 15, o['label'], 14, weight='bold'))
        out.append(text(30, y + 32, f'{o["end"] - o["start"]} ns, alone {alone} ns', 12.5, MUTED))
        _bar(out, o['segs'], x0, y, h, scale)
    # who holds the two things there is one of
    for j, (res, name, k) in enumerate((('lock', 'mm_lock', 'lock'), ('hw', 'LZ4 engine', 'hw'))):
        y = top + (len(ops) + j) * rowh
        out.append(text(30, y + 15, name, 14, weight='bold'))
        out.append(text(30, y + 32, 'one holder at a time', 12.5, MUTED))
        out.append(f'<line x1="{x0}" y1="{y + h / 2}" x2="{x1}" y2="{y + h / 2}" stroke="{FAINT}" stroke-width="1"/>')
        for o in ops:
            who = o['label'].split(':')[0]
            runs = []
            for kk, _, a, b in o['segs']:
                if kk == res:
                    if runs and runs[-1][1] == a:
                        runs[-1][1] = b
                    else:
                        runs.append([a, b])
            for a, b in runs:
                xa, wpx = x0 + a * scale, max(1.5, (b - a) * scale - 2)
                out.append(f'<rect x="{xa:.1f}" y="{y}" width="{wpx:.1f}" height="{h}" rx="3" fill="{COLOR[k]}">'
                           f'<title>{escape(who)}: {b - a} ns</title></rect>')
                if wpx >= tw(who, 12, True) + 8:
                    out.append(text(xa + wpx / 2, y + h / 2 + 4.5, who, 12, anchor='middle', weight='bold'))
    return svg(W, bottom + 20, out, 'Two page faults and one eviction at the same time, with the stretches where one waits '
                                    'for the lock or for the LZ4 engine')


FILES = {f'graph-{c}.svg': (lambda w, c=c: graph(c, w)) for c in deps.CASES}
FILES['timeline.svg'] = timeline
FILES['three-at-once.svg'] = together


def render(w):
    return {name: fn(w) for name, fn in FILES.items()}


def write(w):
    os.makedirs(FIG_DIR, exist_ok=True)
    paths = []
    for name, body in render(w).items():
        path = os.path.join(FIG_DIR, name)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(body)
        paths.append(path)
    return paths
