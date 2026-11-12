/* Counts the instructions each kernel step of kstep.h retires, by running it.
 *
 * For every step there are two functions of the same shape: one prepares the arguments, the other
 * prepares them and runs the step. Both are called n times through one loop, the CPU's count of retired
 * instructions is read before and after, and the difference per call is the step. The count comes from
 * proc_pid_rusage (macOS, Apple silicon). It depends on the compiler and the instruction set, not on how
 * fast this machine is: the same binary retires the same instructions on any AArch64 core.
 *
 * Output: one JSON object on stdout. Run through micro.py, which passes the sizes on the build line.
 */
#include <libproc.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include "kstep.h"

static uint64_t instr_now(void)
{
    struct rusage_info_v4 r;
    proc_pid_rusage(getpid(), RUSAGE_INFO_V4, (rusage_info_t *)&r);
    return r.ri_instructions;
}

typedef uint32_t (*step_fn)(struct kernel *, struct thread *, struct op *, uint32_t);

static uint32_t *idx;                   /* idx[i]: the page the i-th call works on, every RW page once */
static uint32_t g_n = 5;                /* chunks of the example page */
uint32_t g_acc;                         /* what the steps returned, added up: keeps their results alive */
static step_fn volatile g_fn;           /* the loop loads its target from here, so it cannot be specialised */
static uint8_t g_page[LZ4_PAGE_SIZE];

static __attribute__((noinline)) double per_call(step_fn which, struct kernel *k, struct thread *t, struct op *o,
                                                 uint32_t n)
{
    g_fn = which;
    step_fn fn = g_fn;
    uint32_t acc = 0;
    uint64_t a = instr_now();
    for (uint32_t i = 0; i < n; i++)
        acc += fn(k, t, o, i);
    a = instr_now() - a;
    g_acc += acc;
    return (double)a / n;
}

/* ---- the state every measurement starts from ---- */
static void fill(struct kernel *k, struct thread *t, struct op *o)
{
    for (uint32_t h = 0; h < PAGES; h++) {
        k->state[h] = S_UNTOUCHED;
        k->frame_of[h] = -1;
        k->fresh_n[h] = 0;
        k->pins[h] = 0;
        k->pte[h] = 0;
        k->cot[h].flags = LZ4_FLAG_VALID;
        k->cot[h].count = (uint8_t)g_n;
        k->cot[h].comp_len = (uint16_t)(g_n * 512 - 356);    /* 5 chunks: 2204 B */
        k->cot[h].checksum = 0x1234ABCD;
        for (unsigned j = 0; j < LZ4_CHUNK_SLOTS; j++)
            lz4_chunk_set(k->cot[h].chunk[j], j < g_n ? 1000 + 9 * j : 0);
    }
    memset(k->incompressible, 0, (PAGES + 63) / 64 * 8);
    for (uint32_t f = 0; f < FRAMES; f++) {
        k->owner[f] = -1;
        k->free_stack[f] = (int32_t)(FRAMES - 1 - f);
    }
    memset(k->bitmap, 0, NWORDS * 8);
    k->free_top = FRAMES;
    k->hand = k->cursor = k->strikes = k->job_tail = k->cpl_head = k->frame_waiters = 0;
    k->free_chunks = POOL_CHUNKS;
    k->tag = 7;
    k->pool_full = k->lz4_off = k->lock = 0;
    for (unsigned j = 0; j < CPL_ENTRIES; j++)
        k->cpl_ring[j] = (struct lz4_completion){.status = LZ4_STATUS_OK, .length = 2204, .checksum = 0x1234ABCD, .tag = 7};
    t->fresh[0] = idx[1];
    t->fresh_pos = 0;
    memset(o, 0, sizeof *o);
    o->e = k->cot[0];
    o->use_hw = 1;
    o->tag = 7;
    o->cpl = k->cpl_ring[0];
    for (unsigned j = 0; j < LZ4_CHUNK_SLOTS; j++)
        o->c[j] = 2000 + 9 * j;
}

/* every frame holds a present page; frame f belongs to page idx[f] (RW) or RO_FIRST + f (ro != 0) */
static void all_present(struct kernel *k, int ro)
{
    for (uint32_t f = 0; f < FRAMES; f++) {
        uint32_t h = ro ? RO_FIRST + f : idx[f];
        k->owner[f] = (int32_t)h;
        k->frame_of[h] = (int32_t)f;
        k->state[h] = S_PRESENT;
        k->pte[h] = (FC_BASE + ((uint64_t)f << 12)) | PTE_ATTR | PTE_VALID;
    }
    k->free_top = 0;
}

/* STEP: a step that returns nothing. STEP_R: a step whose result the caller branches on; the result is
 * returned, so the instructions that compute it are counted. */
#define STEP_R(name, PREP, EXPR)                                                                            \
    static __attribute__((noinline)) uint32_t base_##name(struct kernel *k, struct thread *t, struct op *o, \
                                                          uint32_t i)                                       \
    {                                                                                                       \
        (void)k; (void)t; (void)o; (void)i;                                                                 \
        PREP;                                                                                               \
        return 0;                                                                                           \
    }                                                                                                       \
    static __attribute__((noinline)) uint32_t full_##name(struct kernel *k, struct thread *t, struct op *o, \
                                                          uint32_t i)                                       \
    {                                                                                                       \
        (void)k; (void)t; (void)o; (void)i;                                                                 \
        PREP;                                                                                               \
        return (uint32_t)(EXPR);                                                                            \
    }
#define STEP(name, PREP, BODY) STEP_R(name, PREP, ((BODY), 0))

/* five instructions that do nothing: the measurement has to say 5 */
static inline __attribute__((always_inline)) void five_nops(void) { __asm__ volatile("nop\nnop\nnop\nnop\nnop"); }
STEP(calib5, , five_nops())
STEP(lock, k->lock = 0, k_lock(k))
STEP(unlock, , k_unlock(k))
STEP_R(check_state, o->h = idx[i], k_check_state(k, o))
STEP(take_frame, o->h = idx[i], k_take_frame(k, o))
STEP(zero_frame, o->f = (int32_t)i, k_zero_frame(k, o))
STEP_R(cot_read, o->h = idx[i], k_cot_read(k, o))
STEP(mark_decompressing, o->h = idx[i], k_mark_decompressing(k, o))
STEP(set_state, o->h = idx[i], k_set_state(k, o, S_PRESENT))
STEP(note_hw, , k_note_hw(k, (int)o->use_hw, (int)o->s))
STEP(cot_clear, o->h = idx[i], k_cot_clear(k, o))
STEP(release_chunks, , k_release_chunks(k, o))
STEP(pte_map, o->h = idx[i], k_pte_map(k, o))
STEP(note_fresh, o->h = idx[i], k_note_fresh(k, t, o))
STEP_R(wake_check, , k_wake_check(k))
STEP(desc_decompress, , k_desc_decompress(k, o))
STEP(desc_compress, , k_desc_compress(k, o, g_n + 2))
STEP(submit, , k_submit(k, o))
STEP_R(cpl_read, , k_cpl_read(k, o))
STEP(frame_write, o->f = (int32_t)i, k_frame_write(k, o, g_page))
STEP_R(reclaim_check, , k_reclaim_check(k))
STEP_R(pick_victim, , k_pick_victim(k, &o->s))
STEP_R(reserve, , k_reserve(k, o, g_n + 2, &o->s))
STEP(find_frame, o->h = idx[i], k_find_frame(k, o))
STEP(pte_clear, o->h = idx[i], k_pte_clear(k, o))
STEP(cot_store, o->h = idx[i], k_cot_store(k, o, g_n))
STEP(trim, , k_bitmap_release(k, o->c + g_n, 2))
STEP(release_all, , k_bitmap_release(k, o->c, g_n + 2))
STEP_R(put_frame, o->h = idx[i], k_put_frame(k, o))
STEP(mark_incompressible, o->h = idx[i], k_mark_incompressible(k, o))

/* ---- starting states of the measurements that need one ---- */
static void st_none(struct kernel *k) { (void)k; }
static void st_bits_used(struct kernel *k) { memset(k->bitmap, 0xFF, NWORDS * 8); k->free_chunks = 0; }
static void st_present_rw(struct kernel *k) { all_present(k, 0); }
static void st_present_ro(struct kernel *k) { all_present(k, 1); }

/* 16 frames the hand has to pass, then one it can take; which reason makes it pass is the argument */
static void st_skip(struct kernel *k, int why)
{
    all_present(k, 0);
    for (uint32_t f = 0; f < FRAMES; f++) {
        if (f % 17 == 16)
            continue;
        uint32_t h = idx[f];
        if (why == 0) {                                 /* free frame */
            k->owner[f] = -1;
        } else if (why == 1) {                          /* fresh */
            k->fresh_n[h] = 1;
        } else if (why == 2) {                          /* known incompressible */
            k->incompressible[h >> 6] |= 1ull << (h & 63);
        } else {                                        /* accessed */
            k->pte[h] |= PTE_AF;
        }
    }
}
static void st_skip_free(struct kernel *k) { st_skip(k, 0); }
static void st_skip_fresh(struct kernel *k) { st_skip(k, 1); }
static void st_skip_incompressible(struct kernel *k) { st_skip(k, 2); }
static void st_skip_accessed(struct kernel *k) { st_skip(k, 3); }

/* bitmap patterns for reserve: every word has exactly 7 zero bits, with `gap` all-ones words between them */
static void st_words(struct kernel *k, unsigned gap, unsigned zeros)
{
    uint32_t free = 0;
    for (uint32_t w = 0; w < NWORDS; w++) {
        if (w % (gap + 1) == 0) {
            k->bitmap[w] = ~0ull << zeros;              /* the low `zeros` bits are free */
            free += zeros;
        } else {
            k->bitmap[w] = ~0ull;
        }
    }
    k->free_chunks = free;
    k->cursor = 0;
}
static void st_words_7(struct kernel *k) { st_words(k, 0, 7); }
static void st_words_7_gap9(struct kernel *k) { st_words(k, 9, 7); }
static void st_words_1(struct kernel *k) { st_words(k, 0, 1); }

static void st_frames_held(struct kernel *k)
{
    for (uint32_t i = 0; i < FRAMES; i++) {
        k->frame_of[idx[i]] = (int32_t)i;
        k->owner[i] = (int32_t)idx[i];
    }
    k->free_top = 0;
}

static int first = 1;

static void report(const char *name, const char *note, uint32_t n, void (*start)(struct kernel *), step_fn base,
                   step_fn full, struct kernel *k, struct thread *t, struct op *o)
{
    double b = 1e30, f = 1e30;
    for (int rep = 0; rep < 5; rep++) {
        double v;
        fill(k, t, o); start(k);
        v = per_call(base, k, t, o, n);
        if (v < b) b = v;
        fill(k, t, o); start(k);
        v = per_call(full, k, t, o, n);
        if (v < f) f = v;
    }
    printf("%s\n  \"%s\": {\"instr\": %.2f, \"calls\": %u, \"note\": \"%s\"}", first ? "" : ",", name, f - b, n, note);
    first = 0;
}

#define RUN(key, name, n, start, note) report(key, note, n, start, base_##name, full_##name, &K, &T, &O)

int main(void)
{
    static struct kernel K;
    static struct thread T;
    static struct op O;
    static uint32_t reg[32];
    K.state = calloc(PAGES, 1);
    K.frame_of = calloc(PAGES, 4);
    K.fresh_n = calloc(PAGES, 2);
    K.pins = calloc(PAGES, 2);
    K.incompressible = calloc((PAGES + 63) / 64, 8);
    K.owner = calloc(FRAMES, 4);
    K.free_stack = calloc(FRAMES, 4);
    K.bitmap = calloc(NWORDS, 8);
    K.cot = calloc(PAGES, sizeof *K.cot);
    K.pte = calloc(PAGES, 8);
    K.job_ring = calloc(JOB_ENTRIES, LZ4_JOB_SLOT_SIZE);
    K.cpl_ring = calloc(CPL_ENTRIES, sizeof *K.cpl_ring);
    K.frames = calloc(FRAME_MASK + 1, LZ4_PAGE_SIZE);
    K.reg = reg;
    idx = calloc(RO_FIRST, 4);
    for (uint32_t i = 0; i < RO_FIRST; i++)
        idx[i] = (uint32_t)(((uint64_t)i * 40503u) % RO_FIRST);     /* every RW page once, in a scattered order */
    for (unsigned i = 0; i < LZ4_PAGE_SIZE; i++)
        g_page[i] = (uint8_t)(i * 7);

    printf("{");
    RUN("calib5", calib5, 30000, st_none, "five NOPs: checks the method");
    RUN("lock", lock, 30000, st_none, "atomic exchange, nobody else holds it");
    RUN("unlock", unlock, 30000, st_none, "atomic store");
    RUN("check_state", check_state, 30000, st_none, "page untouched, a frame is free: the longest way through");
    RUN("take_frame", take_frame, 30000, st_none, "");
    RUN("zero_frame", zero_frame, 20000, st_none, "memset of 4096 B as the C library does it (DC ZVA, 64 B a step)");
    RUN("cot_read", cot_read, 30000, st_none, "copy 32 B, test the valid flag");
    RUN("mark_decompressing", mark_decompressing, 30000, st_none, "");
    RUN("set_state", set_state, 30000, st_none, "one byte store");
    RUN("note_hw", note_hw, 30000, st_none, "the job was answered and the answer was right");
    RUN("cot_clear", cot_clear, 30000, st_none, "32 B of zeros");
    RUN("release_chunks", release_chunks, 30000, st_bits_used, "5 chunks");
    RUN("pte_map", pte_map, 30000, st_none, "one 8 B store");
    RUN("note_fresh", note_fresh, 30000, st_none, "protect = 1, the thread had an older page on its list");
    RUN("wake_check", wake_check, 30000, st_none, "compare only");
    RUN("desc_decompress", desc_decompress, 30000, st_none, "new tag, 48 B descriptor from the COT entry");
    RUN("desc_compress", desc_compress, 30000, st_none, "new tag, 48 B descriptor with 7 chunk numbers");
    RUN("submit", submit, 30000, st_none, "48 B into the ring slot, tail, one register store");
    RUN("cpl_read", cpl_read, 30000, st_none, "16 B out of the ring, tag compare, head, one register store");
    RUN("frame_write", frame_write, 20000, st_none, "memcpy of 4096 B as the C library does it");
    RUN("reclaim_check", reclaim_check, 30000, st_none, "compare only");
    RUN("pick_victim.rw_first", pick_victim, 30000, st_present_rw, "the first frame the hand meets can go, RW page");
    RUN("pick_victim.ro_first", pick_victim, 30000, st_present_ro, "the first frame the hand meets can go, RO page");
    RUN("pick_victim.16_free", pick_victim, 2000, st_skip_free, "the hand passes 16 free frames first");
    RUN("pick_victim.16_fresh", pick_victim, 2000, st_skip_fresh, "the hand passes 16 fresh pages first");
    RUN("pick_victim.16_incompressible", pick_victim, 2000, st_skip_incompressible,
        "the hand passes 16 incompressible RW pages first");
    RUN("pick_victim.16_accessed", pick_victim, 2000, st_skip_accessed,
        "the hand passes 16 accessed pages first and clears their accessed flag");
    RUN("reserve.empty_pool", reserve, 30000, st_none, "7 chunks, all bits free: 1.11 words a call");
    RUN("reserve.2_words", reserve, 1000, st_words_7, "7 chunks, every word has 7 free bits: 2 words a call");
    RUN("reserve.11_words", reserve, 800, st_words_7_gap9,
        "7 chunks, 9 all-ones words between words with 7 free bits: 11 words a call");
    RUN("reserve.7_words", reserve, 1000, st_words_1, "7 chunks, one free bit a word: 7 words a call");
    RUN("find_frame", find_frame, 30000, st_frames_held, "");
    RUN("pte_clear", pte_clear, 30000, st_none, "one 8 B store");
    RUN("cot_store", cot_store, 30000, st_none, "32 B entry with 5 chunk numbers");
    RUN("trim", trim, 30000, st_bits_used, "2 chunks back");
    RUN("release_all", release_all, 30000, st_bits_used, "7 chunks back");
    RUN("put_frame", put_frame, 30000, st_frames_held, "");
    RUN("mark_incompressible", mark_incompressible, 30000, st_none, "set one bit");
    printf("\n}\n");
    return 0;
}
