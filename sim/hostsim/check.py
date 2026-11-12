"""Audit of the whole machine between two kernel entries. Looks only at DRAM, the PTEs and the
kernel tables; knows nothing about how the kernel got there. Raises AuditError on the first violation.

    A1  frames    a page has a frame exactly when it is present; PTE, frame_of and owner agree;
                  every frame is either free or held by one page
    A2  chunks    every chunk is either free in the bitmap or listed by exactly one valid COT entry
    A3  COT       an RO entry is always valid; an RW entry is valid exactly when the page is compressed (or lost)
    A4  contents  every page, wherever it is now, still holds what user SW last put there
    A5  guard     kernel image, pinned run-time data and HRT memory have not changed by a single byte
    A6  held      a page that is pinned, or that a thread still needs for its instruction, is present;
                  the count kept per page agrees with the list kept per thread
    A7  lost      a page is lost only if its stored stream really cannot be turned back into the page
"""
import hashlib
from collections import Counter
from math import ceil

from .codec import LibCodec, crc32
from .kernel import COMPRESSED, LOST, PRESENT, UNTOUCHED, S_NAME


class AuditError(Exception):
    pass


def audit(m):
    cfg, k, port, dram, spec = m.cfg, m.kernel, m.port, m.dram, m.spec
    FL = spec.enum['flag']
    ref = LibCodec()
    n = Counter()

    def bad(rule, text):
        raise AuditError(f'{rule}: {text}')

    if port.locked:
        bad('A0', 'the lock is still held')
    free = list(k.free_frames)
    if len(set(free)) != len(free):
        bad('A1', 'a frame is on the free list twice')
    held = {}
    listed = {}
    for h in range(cfg.pages):
        s, f, ro = k.state[h], k.frame_of[h], cfg.is_ro(h)
        n[S_NAME[s]] += 1
        if s not in (UNTOUCHED, COMPRESSED, PRESENT, LOST):
            bad('A1', f'page {h:#x} is {S_NAME[s]} with no job in flight')
        # A1
        if (s == PRESENT) != (f >= 0) or (s == PRESENT) != bool(port.pte[h]):
            bad('A1', f'page {h:#x} is {S_NAME[s]}, frame {f}, PTE {port.pte[h]:#x}')
        if s == PRESENT:
            if port.pte[h] != cfg.frame_pa(f) or k.owner[f] != h or f in held:
                bad('A1', f'page {h:#x}: PTE, frame_of and owner disagree on frame {f}')
            held[f] = h
        # A3
        e = spec.unpack('cot_entry', dram.view(cfg.entry_pa(h), 32))
        valid = bool(e['flags'] & FL.VALID)
        if ro and not (valid and e['flags'] & FL.RO):
            bad('A3', f'RO page {h:#x} has no valid RO entry')
        if not ro and valid != (s in (COMPRESSED, LOST)):
            bad('A3', f'RW page {h:#x} is {S_NAME[s]} but its entry is {"valid" if valid else "empty"}')
        if not valid and bytes(dram.view(cfg.entry_pa(h), 32)) != bytes(32):
            bad('A3', f'page {h:#x}: an entry that is not valid must be all zeros')
        # A2
        if valid:
            if e['count'] != ceil(e['comp_len'] / cfg.chunk) or not 1 <= e['count'] <= 8:
                bad('A2', f'page {h:#x}: count {e["count"]} does not fit comp_len {e["comp_len"]}')
            for c in e['chunk'][:e['count']]:
                if c >= cfg.pool_chunks or c in listed:
                    bad('A2', f'chunk {c:#x} of page {h:#x} is out of range or also listed by page {listed.get(c, 0):#x}')
                listed[c] = h
        # A4
        if s == PRESENT:
            if crc32(dram.view(cfg.frame_pa(f), cfg.page)) != m.expect[h]:
                bad('A4', f'present page {h:#x} does not hold what was written')
        elif s == UNTOUCHED:
            if m.expect[h] != m.zero_crc:
                bad('A4', f'untouched page {h:#x} was written')
        elif s == COMPRESSED and h not in m.corrupted:
            stream = b''.join(bytes(dram.view(cfg.chunk_pa(c), cfg.chunk)) for c in e['chunk'][:e['count']])[:e['comp_len']]
            if crc32(stream) != e['checksum']:
                bad('A4', f'stored stream of page {h:#x} does not match its CRC-32')
            page = stream if e['flags'] & FL.RAW else ref.decompress(stream, cfg.page)
            if page is None or crc32(page) != m.expect[h]:
                bad('A4', f'stored stream of page {h:#x} does not decompress to the page')
            n['streams_checked'] += 1
        elif s == LOST:                                   # A7
            stream = b''.join(bytes(dram.view(cfg.chunk_pa(c), cfg.chunk)) for c in e['chunk'][:e['count']])[:e['comp_len']]
            page = None
            if crc32(stream) == e['checksum']:
                page = stream if e['flags'] & FL.RAW else ref.decompress(stream, cfg.page)
            if page is not None and crc32(page) == m.expect[h]:
                bad('A7', f'page {h:#x} is lost, but its stored stream is intact and decodes to the page')
    needed = Counter(h for mine in k.fresh.values() for h in mine)
    for h in range(cfg.pages):
        if k.fresh_n[h] != needed[h]:
            bad('A6', f'page {h:#x}: fresh_n says {k.fresh_n[h]}, the threads list it {needed[h]} times')
        if (k.pins[h] or k.fresh_n[h]) and k.state[h] != PRESENT:
            bad('A6', f'page {h:#x} is {S_NAME[k.state[h]]} while pinned {k.pins[h]} times, needed {k.fresh_n[h]} times')
    n.update(pinned=sum(1 for h in range(cfg.pages) if k.pins[h]), needed=len(needed))
    if set(held) & set(free) or len(held) + len(free) != cfg.frames:
        bad('A1', f'{len(held)} frames held and {len(free)} free do not add up to {cfg.frames}')
    for f in range(cfg.frames):
        if (f in held) != (k.owner[f] >= 0):
            bad('A1', f'owner[{f}] is {k.owner[f]} but the frame is {"held" if f in held else "free"}')
    free_chunks = m.bitmap.enumerate_free()
    if len(free_chunks) != m.bitmap.free:
        bad('A2', f'bitmap counts {m.bitmap.free} free chunks but has {len(free_chunks)} clear bits')
    if free_chunks & set(listed) or len(free_chunks) + len(listed) != cfg.pool_chunks:
        bad('A2', f'{len(listed)} chunks listed and {len(free_chunks)} free do not add up to {cfg.pool_chunks}')
    size = cfg.cot_base - cfg.dram_base
    if m.guard is not None and hashlib.blake2b(dram.view(cfg.dram_base, size)).digest() != m.guard:
        bad('A5', 'memory below the COT changed: kernel image, pinned data or HRT memory')
    n.update(frames_held=len(held), frames_free=len(free), chunks_listed=len(listed), chunks_free=len(free_chunks),
             guard_bytes=size)
    return dict(n)
