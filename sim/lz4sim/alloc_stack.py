"""Baseline free-chunk stack, owned by the accelerator.

The top of the stack lives in SRAM (up to sram_cap numbers). The rest is a
linked list of list chunks in the pool: each list chunk is itself a free chunk
whose first 3 bytes point to the next list chunk and whose remaining bytes hold
169 free chunk numbers. INIT builds the list in groups of 170 starting at the
first chunk after the RO image. A pop below refill_below reads one list chunk
back (+170); a push above spill_above writes one out (-170).
"""
from collections import Counter

from .formats import NO_CHUNK, LIST_NUMBERS, pack_list_chunk, unpack_list_chunk


class HwFreeStack:
    def __init__(self, cfg, dram, trace):
        self.cfg = cfg
        self.dram = dram
        self.trace = trace
        self.sram = []              # top of stack is sram[-1]
        self.list_head = NO_CHUNK
        self.list_chunks = 0
        self.st = Counter()

    def free_count(self):
        return len(self.sram) + self.list_chunks * (LIST_NUMBERS + 1)

    def dram_events(self):
        """Refills + spills + init writes so far; the accelerator charges one DRAM access each."""
        return self.st['refills'] + self.st['spills'] + self.st['init_writes']

    def init(self, first_free):
        cfg = self.cfg
        g = cfg.list_group
        total = cfg.pool_chunks
        free = total - first_free
        groups, rest = divmod(free, g)
        self.sram = list(range(total - rest, total))
        head = NO_CHUNK
        for i in range(groups - 1, -1, -1):
            lc = first_free + i * g
            self.dram.write(cfg.chunk_pa(lc), pack_list_chunk(head, range(lc + 1, lc + g)))
            head = lc
        self.list_head = head
        self.list_chunks = groups
        self.st['init_writes'] = groups
        self.trace.emit('stack', who='hw', op='init', first_free=first_free, free=free,
                        list_head=self.list_head, list_chunks=groups, sram=len(self.sram))
        return free

    def pop(self):
        if len(self.sram) < self.cfg.refill_below and self.list_head != NO_CHUNK:
            self._refill()
        if not self.sram:
            self.st['empty'] += 1
            return None
        self.st['pops'] += 1
        return self.sram.pop()

    def push(self, c):
        self.sram.append(c)
        self.st['pushes'] += 1
        if len(self.sram) > self.cfg.spill_above:
            self._spill()

    def _refill(self):
        lc = self.list_head
        data = self.dram.read(self.cfg.chunk_pa(lc), self.cfg.chunk)
        nxt, numbers = unpack_list_chunk(data)
        self.sram.extend(numbers)
        self.sram.append(lc)
        self.list_head = nxt
        self.list_chunks -= 1
        self.st['refills'] += 1
        self.trace.emit('stack', who='hw', op='refill', list_chunk=lc, list_head=nxt,
                        sram=len(self.sram), list_chunks=self.list_chunks)

    def _spill(self):
        g = self.cfg.list_group
        batch = [self.sram.pop() for _ in range(g)]
        lc, numbers = batch[0], batch[1:]
        prev = self.list_head
        self.dram.write(self.cfg.chunk_pa(lc), pack_list_chunk(prev, numbers))
        self.list_head = lc
        self.list_chunks += 1
        self.st['spills'] += 1
        # next = the previous head, as written into the first 3 bytes of the new list chunk
        self.trace.emit('stack', who='hw', op='spill', list_chunk=lc, next=prev, numbers=numbers,
                        sram=len(self.sram), list_chunks=self.list_chunks)

    def enumerate_free(self):
        """Walk SRAM and the list in DRAM; used by audits only."""
        free = set(self.sram)
        head = self.list_head
        while head != NO_CHUNK:
            nxt, numbers = unpack_list_chunk(self.dram.view(self.cfg.chunk_pa(head), self.cfg.chunk))
            free.add(head)
            free.update(numbers)
            head = nxt
        return free
