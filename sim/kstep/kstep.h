/* Kernel steps of the SW-leaning design, written out in C so that they can be counted.
 *
 * sim/hostsim/kernel.py says what the kernel does and in which order. It keeps its tables in Python
 * containers, which say nothing about bytes, cache lines or instructions. This file fixes one layout for
 * every table and writes each step of hostsim/deps.py:STEPS as the loads, stores and arithmetic it needs.
 * measure.c runs every step and counts the instructions the CPU retired.
 *
 * It is a reference for counting, not the kernel. Steps that need the privileged side of a CPU (exception
 * entry, TLB and cache maintenance, interrupts, sleeping and waking threads) are not here: see micro.py.
 *
 * The sizes come from the build line (-DPAGES=... and so on), which micro.py fills from lz4sim.config.
 */
#ifndef KSTEP_H
#define KSTEP_H

#include <stdint.h>
#include <string.h>

#include "lz4_hwif.h"

#define PROTECT 1                       /* pages of one thread the reclaimer leaves alone (kernel.py: protect) */
#define STRIKES 3
#define NWORDS ((POOL_CHUNKS + 63) / 64)
#define NONE 0xFFFFFFFFu

/* the six page states, numbered as in lz4sim/kernel.py */
enum { S_COMPRESSED, S_PRESENT, S_UNTOUCHED, S_COMPRESSING, S_DECOMPRESSING, S_LOST };

/* what check_state tells the page fault handler to do next */
enum { GO, SPURIOUS, LOST, WAIT_PAGE, WAIT_FRAME };

/* PTE of the CPU MMU. ASSUMPTION (K1 is open): one flat table with an 8 B entry per page of the layer,
 * bit 0 valid, bit 10 the accessed flag that the CPU MMU sets by itself. */
#define PTE_VALID 0x1ull
#define PTE_AF (1ull << 10)
#define PTE_ATTR 0x0060000000000B42ull  /* user, read and write, not global, bit 10 clear: only the pattern matters */

struct kernel {
    /* ---- kernel memory: pinned, outside the compression layer, lost at power-off ---- */
    uint8_t *state;                     /* [PAGES]   1 B   page state */
    int32_t *frame_of;                  /* [PAGES]   4 B   frame number of a page, -1 if none */
    uint16_t *fresh_n;                  /* [PAGES]   2 B   in how many threads' fresh lists the page is */
    uint16_t *pins;                     /* [PAGES]   2 B   pin_page count */
    uint64_t *incompressible;           /* [PAGES/64] 1 bit per page. kernel.py uses a set; a bitmap is the choice here */
    int32_t *owner;                     /* [FRAMES]  4 B   page that holds a frame, -1 if free */
    int32_t *free_stack;                /* [FRAMES]  4 B   stack of free frame numbers */
    uint64_t *bitmap;                   /* [NWORDS]  8 B   one bit per chunk, 1 = in use */
    uint32_t free_top;                  /* number of entries on free_stack */
    uint32_t hand;                      /* clock hand, a frame number */
    uint32_t cursor;                    /* word of the bitmap where the next search starts */
    uint32_t free_chunks;
    uint32_t tag;                       /* last job tag given out */
    uint32_t strikes;
    uint32_t job_tail, cpl_head;        /* the kernel's copies of the two ring indexes it owns */
    uint32_t frame_waiters;             /* threads asleep in wait_frame */
    uint8_t pool_full, lz4_off;
    uint8_t lock;                       /* mm_lock */
    /* ---- DRAM, at fixed addresses ---- */
    struct lz4_cot_entry *cot;          /* [PAGES]   32 B  at cot_base. The LZ4 HW never reads it */
    uint64_t *pte;                      /* [PAGES]   8 B   the page table the CPU MMU walks */
    uint8_t (*job_ring)[LZ4_JOB_SLOT_SIZE];     /* [JOB_ENTRIES] 64 B a slot, descriptor in the first 48 B */
    struct lz4_completion *cpl_ring;    /* [CPL_ENTRIES] 16 B */
    uint8_t *frames;                    /* the frame area; measure.c maps only a part of it */
    /* ---- LZ4 HW registers ---- */
    volatile uint32_t *reg;
};

struct thread {
    uint32_t fresh[PROTECT];            /* pages of this thread's latest faults */
    uint32_t fresh_pos;
};

/* what one operation carries from step to step: locals of the thread that runs it */
struct op {
    uint32_t h;                         /* the page */
    uint32_t s;                         /* state[h] as read */
    int32_t f;                          /* the frame */
    uint32_t pa;                        /* its physical address */
    uint32_t use_hw;
    uint32_t tag;
    uint32_t c[LZ4_CHUNK_SLOTS];        /* reserved chunk numbers (COMPRESS) */
    struct lz4_cot_entry e;             /* COT entry as read (DECOMPRESS) */
    struct lz4_job_desc desc;
    struct lz4_completion cpl;
};

#define INL static inline __attribute__((always_inline))

/* ------------------------------------------------------------------ the lock */
INL void k_lock(struct kernel *k)
{
    while (__atomic_exchange_n(&k->lock, 1, __ATOMIC_ACQUIRE))
        ;
}

INL void k_unlock(struct kernel *k)
{
    __atomic_store_n(&k->lock, 0, __ATOMIC_RELEASE);
}

/* ------------------------------------------------------------ page fault, lock held */
INL int k_check_state(struct kernel *k, struct op *o)
{
    uint32_t s = k->state[o->h];
    o->s = s;
    if (s == S_PRESENT)
        return SPURIOUS;
    if (s == S_LOST)
        return LOST;
    if (s == S_COMPRESSING || s == S_DECOMPRESSING)
        return WAIT_PAGE;
    if (!k->free_top)
        return WAIT_FRAME;
    return GO;
}

INL void k_take_frame(struct kernel *k, struct op *o)
{
    int32_t f = k->free_stack[--k->free_top];
    k->frame_of[o->h] = f;
    k->owner[f] = (int32_t)o->h;
    o->f = f;
    o->pa = FC_BASE + ((uint32_t)f << 12);
}

INL void k_zero_frame(struct kernel *k, struct op *o)
{
    memset(k->frames + ((size_t)(o->f & FRAME_MASK) << 12), 0, LZ4_PAGE_SIZE);
}

INL int k_cot_read(struct kernel *k, struct op *o)
{
    o->e = k->cot[o->h];                /* 32 B, half a cache line */
    return o->e.flags & LZ4_FLAG_VALID;
}

INL void k_mark_decompressing(struct kernel *k, struct op *o)
{
    o->use_hw = !k->lz4_off;
    k->state[o->h] = S_DECOMPRESSING;
}

INL void k_set_state(struct kernel *k, struct op *o, uint8_t s)
{
    k->state[o->h] = s;
}

INL void k_note_hw(struct kernel *k, int answered, int wrong)
{
    if (!answered)
        k->strikes = STRIKES;
    else if (wrong)
        k->strikes++;
    else
        k->strikes = 0;
    if (k->strikes >= STRIKES && !k->lz4_off)
        k->lz4_off = 1;
}

INL void k_cot_clear(struct kernel *k, struct op *o)
{
    memset(&k->cot[o->h], 0, sizeof k->cot[0]);
}

INL void k_bitmap_release(struct kernel *k, const uint32_t *c, unsigned n)
{
    for (unsigned i = 0; i < n; i++)
        k->bitmap[c[i] >> 6] &= ~(1ull << (c[i] & 63));
    k->free_chunks += n;
}

/* RW page is back in its frame: its chunks, as the COT entry lists them, return to the bitmap */
INL void k_release_chunks(struct kernel *k, struct op *o)
{
    unsigned n = o->e.count;
    for (unsigned i = 0; i < n; i++) {
        uint32_t c = lz4_chunk_get(o->e.chunk[i]);
        k->bitmap[c >> 6] &= ~(1ull << (c & 63));
    }
    k->free_chunks += n;
    k->pool_full = 0;
}

INL void k_pte_map(struct kernel *k, struct op *o)
{
    k->pte[o->h] = (uint64_t)o->pa | PTE_ATTR | PTE_AF | PTE_VALID;
}

INL void k_note_fresh(struct kernel *k, struct thread *t, struct op *o)
{
    uint32_t pos = t->fresh_pos;
    uint32_t old = t->fresh[pos];
    t->fresh[pos] = o->h;
    t->fresh_pos = pos + 1 == PROTECT ? 0 : pos + 1;
    k->fresh_n[o->h]++;
    if (old != NONE)
        k->fresh_n[old]--;
}

INL int k_wake_check(struct kernel *k)
{
    return k->free_top <= FC_LOW;       /* true: wake the reclaimer, an OS call that is not counted here */
}

/* ---------------------------------------------------------- one LZ4 job, no lock */
INL uint32_t k_new_tag(struct kernel *k)
{
    uint32_t tag = __atomic_add_fetch(&k->tag, 1, __ATOMIC_RELAXED);   /* other threads come through here too */
    return tag ? tag : 1;
}

INL void k_desc_decompress(struct kernel *k, struct op *o)
{
    struct lz4_job_desc *d = &o->desc;
    o->tag = k_new_tag(k);
    d->opcode = LZ4_OPCODE_DECOMPRESS;
    d->count = o->e.count;
    d->limit = LZ4_PAGE_SIZE;
    d->frame_pa = o->pa;
    d->comp_len = o->e.comp_len;
    d->flags = o->e.flags & LZ4_FLAG_RAW;
    d->checksum = o->e.checksum;
    d->tag = o->tag;
    memcpy(d->chunk, o->e.chunk, sizeof d->chunk);     /* same 24 B layout in the COT entry and the descriptor */
    d->rsvd = 0;
}

INL void k_desc_compress(struct kernel *k, struct op *o, unsigned n)
{
    struct lz4_job_desc *d = &o->desc;
    o->tag = k_new_tag(k);
    d->opcode = LZ4_OPCODE_COMPRESS;
    d->count = (uint8_t)n;
    d->limit = COMPRESS_LIMIT;
    d->frame_pa = o->pa;
    d->comp_len = 0;
    d->flags = 0;
    d->checksum = 0;
    d->tag = o->tag;
    memset(d->chunk, 0, sizeof d->chunk);
    for (unsigned i = 0; i < n; i++)
        lz4_chunk_set(d->chunk[i], o->c[i]);
    d->rsvd = 0;
}

INL void k_submit(struct kernel *k, struct op *o)
{
    uint32_t t = k->job_tail;
    memcpy(k->job_ring[t], &o->desc, sizeof o->desc);
    t = (t + 1) & (JOB_ENTRIES - 1);
    k->job_tail = t;
    k->reg[LZ4_REG_JOB_TAIL / 4] = t;   /* the doorbell: one register write */
}

INL int k_cpl_read(struct kernel *k, struct op *o)
{
    uint32_t hd = k->cpl_head;
    o->cpl = k->cpl_ring[hd];
    hd = (hd + 1) & (CPL_ENTRIES - 1);
    k->cpl_head = hd;
    k->reg[LZ4_REG_CPL_HEAD / 4] = hd;  /* one register write */
    return o->cpl.tag == o->tag;
}

INL void k_frame_write(struct kernel *k, struct op *o, const uint8_t *page)
{
    memcpy(k->frames + ((size_t)(o->f & FRAME_MASK) << 12), page, LZ4_PAGE_SIZE);
}

/* ------------------------------------------------------------- the reclaimer, lock held */
INL int k_reclaim_check(struct kernel *k)
{
    return k->free_top < FC_HIGH;
}

/* Clock scan. Returns the page to evict, or NONE. *looked: how many frames the hand passed. */
INL uint32_t k_pick_victim(struct kernel *k, uint32_t *looked)
{
    for (uint32_t step = 0; step < 2u * FRAMES; step++) {
        uint32_t f = k->hand;
        k->hand = f + 1 == FRAMES ? 0 : f + 1;
        int32_t h = k->owner[f];
        if (h < 0 || k->state[h] != S_PRESENT)          /* free frame, or a job is using it */
            continue;
        if (k->pins[h] | k->fresh_n[h])                 /* pinned, or just faulted in and not used yet */
            continue;
        if ((uint32_t)h < RO_FIRST &&                   /* an RW page */
            (k->pool_full || k->lz4_off || ((k->incompressible[h >> 6] >> (h & 63)) & 1)))
            continue;
        uint64_t p = k->pte[h];
        if (p & PTE_AF) {                               /* touched since the hand last passed: second chance */
            k->pte[h] = p & ~PTE_AF;
            continue;
        }
        *looked = step + 1;
        return (uint32_t)h;
    }
    *looked = 2u * FRAMES;
    return NONE;
}

/* Reserve n chunks: skip words that are all ones, in the first word with a zero bit take the lowest zero
 * (count trailing zeros of the inverted word; on AArch64 that is RBIT then CLZ). Next-fit from the cursor. */
INL int k_reserve(struct kernel *k, struct op *o, unsigned n, uint32_t *scanned)
{
    if (k->free_chunks < n) {
        k->pool_full = 1;
        return 0;
    }
    uint32_t w = k->cursor, words = 0;
    unsigned got = 0;
    for (;;) {
        uint64_t word = k->bitmap[w];
        words++;
        if (word != ~0ull) {
            uint64_t inv = ~word;
            while (inv && got < n) {
                o->c[got++] = w * 64 + (uint32_t)__builtin_ctzll(inv);
                inv &= inv - 1;                         /* clear the lowest set bit */
            }
            k->bitmap[w] = ~inv;                        /* every bit taken is now 1 */
            if (got == n)
                break;
        }
        if (++w == NWORDS)
            w = 0;
    }
    k->cursor = w;
    k->free_chunks -= n;
    *scanned = words;
    return 1;
}

INL void k_find_frame(struct kernel *k, struct op *o)
{
    o->f = k->frame_of[o->h];
    o->pa = FC_BASE + ((uint32_t)o->f << 12);
}

INL void k_pte_clear(struct kernel *k, struct op *o)
{
    k->pte[o->h] = 0;
}

INL void k_cot_store(struct kernel *k, struct op *o, unsigned used)
{
    struct lz4_cot_entry e;
    e.flags = LZ4_FLAG_VALID | (o->cpl.flags & LZ4_FLAG_RAW);
    e.count = (uint8_t)used;
    e.comp_len = o->cpl.length;
    e.checksum = o->cpl.checksum;
    memset(e.chunk, 0, sizeof e.chunk);
    for (unsigned i = 0; i < used; i++)
        lz4_chunk_set(e.chunk[i], o->c[i]);
    k->cot[o->h] = e;
}

INL int k_put_frame(struct kernel *k, struct op *o)
{
    int32_t f = k->frame_of[o->h];
    k->frame_of[o->h] = -1;
    k->owner[f] = -1;
    k->free_stack[k->free_top++] = f;
    return k->frame_waiters != 0;       /* true: wake them, an OS call that is not counted here */
}

INL void k_mark_incompressible(struct kernel *k, struct op *o)
{
    k->incompressible[o->h >> 6] |= 1ull << (o->h & 63);
}

#endif
