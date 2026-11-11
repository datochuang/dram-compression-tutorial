"""Software-variant chunk allocator: one bit per chunk, owned by the kernel.

Searching is word-at-a-time: an all-ones 64-bit word is skipped with one
compare; in a word with clear bits, count-trailing-zeros of the inverted word
gives the next free chunk directly. A next-fit cursor continues from the last
word used, so the RO half (always all ones) is never visited.
"""
from collections import Counter

from .formats import F_VALID


class DoubleAllocation(Exception):
    pass


class DoubleFree(Exception):
    pass


WORD = 64
ALL = (1 << WORD) - 1


class KernelBitmap:
    def __init__(self, cfg, trace):
        self.cfg = cfg
        self.trace = trace
        n = cfg.pool_chunks
        self.n = n
        self.nwords = (n + WORD - 1) // WORD
        self.words = [0] * self.nwords
        pad = self.nwords * WORD - n
        if pad:
            self.words[-1] = (ALL << (WORD - pad)) & ALL
        self.free = n
        self.cursor = 0
        self.st = Counter()
        self.scan_max = 0

    @property
    def bytes(self):
        return self.nwords * 8

    def is_used(self, c):
        return (self.words[c >> 6] >> (c & 63)) & 1

    def mark_used(self, c):
        w, b = c >> 6, 1 << (c & 63)
        if self.words[w] & b:
            raise DoubleAllocation(c)
        self.words[w] |= b
        self.free -= 1

    def build_from_cot(self, dram):
        """Boot: walk every COT entry and set the bits of valid entries."""
        cfg = self.cfg
        used = entries = 0
        for h in range(cfg.pages):
            mv = dram.view(cfg.entry_pa(h), 32)
            if mv[0] & F_VALID:
                entries += 1
                for i in range(mv[1]):
                    self.mark_used(int.from_bytes(mv[8 + 3 * i:11 + 3 * i], 'little'))
                    used += 1
        self.st['build_entries'] = entries
        self.st['build_used'] = used
        # start the cursor at the first word with a clear bit, past the RO image
        for w, word in enumerate(self.words):
            if word != ALL:
                self.cursor = w
                break
        self.trace.emit('bitmap', who='kernel', op='build', entries=entries, used=used,
                        free=self.free, words=self.nwords)
        return used

    def reserve(self, n):
        if self.free < n:
            self.st['refused'] += 1
            return None
        out = []
        w = self.cursor
        scanned = 0
        while len(out) < n:
            word = self.words[w]
            scanned += 1
            if word != ALL:
                inv = ~word & ALL
                while inv and len(out) < n:
                    low = inv & -inv
                    out.append(w * WORD + low.bit_length() - 1)
                    word |= low
                    inv ^= low
                self.words[w] = word
                if len(out) == n:
                    break
            w += 1
            if w == self.nwords:
                w = 0
                self.st['wraps'] += 1
        self.cursor = w
        self.free -= n
        self.st['reserves'] += 1
        self.st['words_scanned'] += scanned
        self.scan_max = max(self.scan_max, scanned)
        self.trace.emit('chunk', who='kernel', op='reserve', chunks=out, words=scanned)
        return out

    def release(self, chunks, op='release'):
        for c in chunks:
            w, b = c >> 6, 1 << (c & 63)
            if not (self.words[w] & b):
                raise DoubleFree(c)
            self.words[w] &= ~b
        self.free += len(chunks)
        self.st['releases'] += 1
        if chunks:
            self.trace.emit('chunk', who='kernel', op=op, chunks=list(chunks))

    def enumerate_free(self):
        free = set()
        for w, word in enumerate(self.words):
            inv = ~word & ALL
            while inv:
                low = inv & -inv
                free.add(w * WORD + low.bit_length() - 1)
                inv ^= low
        return free
