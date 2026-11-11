"""Synthetic page contents and page access streams.

There is no real workload, so pages are made to order: a page with target LZ4
ratio r is r*4096 random bytes (incompressible literals) and the rest a
repeated 4-byte pattern (one long match), spread over four segments. The ratio
of each page is drawn from a clipped normal distribution; pages above the
compress limit come out incompressible, pages near zero are zero pages.

Accesses follow a hot-set model: with probability p_hot the page is drawn from
a fixed hot set (hot RO pages and hot RW pages, sized in pages), otherwise
uniformly from the whole compressible range. Writes hit RW pages only. The
first access to a heap page is always a write that fills the whole page (the
program initialises its memory); later writes overwrite write_bytes bytes at a
random offset. phase_len > 0 replaces a fraction of each hot set every
phase_len accesses.

Two generators: rng drives the access stream, crng the page contents, so the
stream does not depend on how many pages the kernel asked to be generated.

User software. Every page belongs to one user program (a client of the memory
system). The clients split each of the three page ranges, .data, heap and RO
image, in proportion to their shares, so each program has its own code and its
own data. Ownership is a label only: it does not change which pages the stream
touches, so results with and without it are the same. The names are examples,
not taken from a real product; --clients replaces them.
"""
import random

CLIENTS = (('UI', 40), ('MEDIA', 27), ('NET', 20), ('LOG', 13))
MAX_CLIENTS = 8


def parse_clients(text):
    """'UI:40,MEDIA:27' -> (('UI', 40.0), ('MEDIA', 27.0))"""
    out = []
    for part in text.split(','):
        name, _, share = part.strip().partition(':')
        out.append((name.strip(), float(share or 1)))
    return tuple(out)


class Workload:
    def __init__(self, cfg, seed=1, ro_ratio=0.55, ro_sd=0.18, rw_ratio=0.45, rw_sd=0.20,
                 zero_frac=0.02, hot_ro_pages=7680, hot_rw_pages=20480, p_hot=0.9,
                 write_frac=0.3, phase_len=0, phase_frac=0.2, write_bytes=16, clients=CLIENTS):
        self.cfg = cfg
        self.seed = seed
        self.rng = random.Random(seed)
        self.crng = random.Random(seed * 7919 + 1)
        self.touched = bytearray(cfg.rw_pages)
        for h in range(cfg.data_pages):
            self.touched[h] = 1
        self.ro_ratio, self.ro_sd = ro_ratio, ro_sd
        self.rw_ratio, self.rw_sd = rw_ratio, rw_sd
        self.zero_frac = zero_frac
        self.hot_ro_n = min(hot_ro_pages, cfg.ro_pages)
        self.hot_rw_n = min(hot_rw_pages, cfg.rw_pages)
        self.p_hot = p_hot
        self.write_frac = write_frac
        self.phase_len = phase_len
        self.phase_frac = phase_frac
        self.write_bytes = write_bytes
        self.hot_ro = []
        self.hot_rw = []
        self.clients, self.owner = self._partition(clients)

    # ---- user software
    def _partition(self, clients):
        """Split the .data, heap and RO ranges among the clients. owner[h] is the client index."""
        cfg = self.cfg
        clients = tuple((str(n), float(s)) for n, s in clients)
        names = [n for n, _ in clients]
        if not 1 <= len(clients) <= MAX_CLIENTS:
            raise ValueError(f'between 1 and {MAX_CLIENTS} clients')
        if len(set(names)) != len(names) or not all(names) or any(s <= 0 for _, s in clients):
            raise ValueError('client names must be distinct and shares positive')
        total = sum(s for _, s in clients)
        out = [{'name': n, 'share_pct': round(s / total * 100, 1), 'pages': 0} for n, s in clients]
        owner = bytearray(cfg.pages)
        for key, lo, hi in (('data', 0, cfg.data_pages), ('heap', cfg.data_pages, cfg.rw_pages),
                            ('ro', cfg.ro_first, cfg.pages)):
            acc, a = 0.0, lo
            for i, (_, s) in enumerate(clients):
                acc += s
                b = hi if i == len(clients) - 1 else lo + round((hi - lo) * acc / total)
                out[i][key] = [a, b]          # handles a <= h < b
                out[i]['pages'] += b - a
                owner[a:b] = bytes([i]) * (b - a)
                a = b
        return out, owner

    def client_of(self, h):
        return self.owner[h]

    def params(self):
        return {'seed': self.seed, 'ro_ratio': self.ro_ratio, 'ro_sd': self.ro_sd,
                'rw_ratio': self.rw_ratio, 'rw_sd': self.rw_sd, 'zero_frac': self.zero_frac,
                'hot_ro_pages': self.hot_ro_n, 'hot_rw_pages': self.hot_rw_n, 'p_hot': self.p_hot,
                'write_frac': self.write_frac, 'phase_len': self.phase_len,
                'phase_frac': self.phase_frac, 'write_bytes': self.write_bytes}

    # ---- page contents
    def _ratio(self, mean, sd):
        if self.crng.random() < self.zero_frac:
            return 0.0
        return min(max(self.crng.gauss(mean, sd), 0.0), 1.0)

    def make_page(self, ratio):
        page = self.cfg.page
        rng = self.crng
        if ratio < 0.02:
            return bytes(page)
        n_rand = max(0, min(page, int(round(ratio * page)) - 12))
        segs = 4
        seg = page // segs
        out = bytearray()
        left = n_rand
        for s in range(segs):
            r = min(seg, left // (segs - s))
            left -= r
            out += rng.randbytes(r)
            fill = seg - r
            if fill:
                pat = rng.randbytes(4)
                out += (pat * (fill // 4 + 1))[:fill]
        return bytes(out)

    def ro_page(self):
        return self.make_page(self._ratio(self.ro_ratio, self.ro_sd))

    def rw_page(self):
        return self.make_page(self._ratio(self.rw_ratio, self.rw_sd))

    def mutate(self, mv):
        """A CPU write: overwrite write_bytes bytes of the frame at a random offset."""
        n = self.write_bytes
        off = self.crng.randrange(0, len(mv) - n)
        mv[off:off + n] = self.crng.randbytes(n)

    def fill(self, mv):
        """The program initialises a freshly touched page with its own data."""
        mv[:] = self.rw_page()

    # ---- access stream
    def accesses(self, n):
        cfg, rng = self.cfg, self.rng
        self.hot_ro = rng.sample(range(cfg.ro_first, cfg.pages), self.hot_ro_n)
        self.hot_rw = rng.sample(range(cfg.rw_pages), self.hot_rw_n)
        hot_ro, hot_rw = self.hot_ro, self.hot_rw
        total_hot = len(hot_ro) + len(hot_rw)
        p_rw = len(hot_rw) / total_hot if total_hot else 0.0
        for i in range(n):
            if self.phase_len and i and i % self.phase_len == 0:
                self._shift(hot_ro, cfg.ro_first, cfg.pages)
                self._shift(hot_rw, 0, cfg.rw_pages)
            if total_hot and rng.random() < self.p_hot:
                if rng.random() < p_rw:
                    h = hot_rw[rng.randrange(len(hot_rw))]
                else:
                    h = hot_ro[rng.randrange(len(hot_ro))]
            else:
                h = rng.randrange(cfg.pages)
            if h < cfg.rw_pages:
                if not self.touched[h]:
                    self.touched[h] = 1
                    w = True
                else:
                    w = rng.random() < self.write_frac
            else:
                w = False
            yield h, w

    def _shift(self, hot, lo, hi):
        if not hot:
            return
        k = int(len(hot) * self.phase_frac)
        for i in self.rng.sample(range(len(hot)), k):
            hot[i] = self.rng.randrange(lo, hi)
