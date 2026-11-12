"""The same kernel.py, run by several threads at once. Still no time.

Every thread of the real system is a task here: each user SW thread, the
reclaimer thread and the LZ4 HW. Only one task runs at any moment. A task runs
until it reaches a point where the real system could switch to somebody else:

    before it takes the lock            while it waits for a job, a page or a frame
    before the CPU runs an instruction  while a job is in flight in the LZ4 HW

At each such point a chooser decides who goes next. The same choices give the
same run, byte for byte, so a failing schedule can be run again.

    RandomChooser   a seeded random walk through the schedules
    PlanChooser     nobody is interrupted, except at the steps a plan names;
                    explore() uses it to try every schedule with one or two interruptions
    PreferChooser   one task always runs first when it can: a thread of higher priority

What the kernel is checked against while it runs:

    lock      a table is touched only by the task that holds the lock
    TLB       no core uses a translation the kernel has taken away      StaleTlb
    jobs      no two jobs share a frame or a chunk; the CPU never touches
              a frame a job owns; a pinned frame is never in a job      JobRace
    data      every instruction sees what user SW last wrote            DataMismatch
    cache     rules C1 to C4 of cache.py                                CacheError
    context   no page fault where nobody can wait                       FaultNotAllowed
    end       every user thread finishes, or memory is really used up   Deadlock
    audit     rules A0 to A7 of check.py once everybody is done

Things that go wrong on purpose, as steps of a user thread's script:

    damage    one byte of a stored stream is flipped
    hwfault   the next COMPRESS or DECOMPRESS of the LZ4 HW fails in a given way (hw.py)
    hwdown    the LZ4 HW stops answering for good
    kill      another user thread is ended; it notices between two kernel entries
"""
import random
import threading
from collections import Counter, deque
from dataclasses import dataclass
from math import ceil

from .codec import crc32
from .kernel import COMPRESSED, COMPRESSING, DECOMPRESSING, PRESENT, S_NAME, KernelBug, OutOfMemory
from .machine import DataMismatch, Machine, NoProgress, Port
from lz4sim.config import SystemConfig

RUNNABLE, BLOCKED, DONE = 'runnable', 'blocked', 'done'
RETRY_LIMIT = 8


class Deadlock(Exception):
    """A thread waits for something nobody is going to give it."""


class StaleTlb(Exception):
    """A core used a translation after the kernel took it away."""


class JobRace(Exception):
    """A frame or a chunk a job owns was used by somebody else."""


class AliasError(Exception):
    """Kernel code reached a page through its own mapping while the page had no frame."""


class Killed(BaseException):
    pass


class Terminated(BaseException):
    """Only in the mutant kill_in_kernel: a thread is torn out of a kernel procedure where it sleeps."""


# --------------------------------------------------------------------- a small machine
@dataclass(frozen=True)
class TinyConfig(SystemConfig):
    """A machine of a few dozen pages, so that frames run out all the time and a run takes milliseconds."""
    n_frames: int = 12
    n_rw: int = 16
    n_data: int = 2
    n_ro: int = 8
    n_chunks: int = 240
    fc_low: int = 1
    fc_high: int = 2
    rw_raw_store: bool = True

    frames = property(lambda s: s.n_frames)
    rw_pages = property(lambda s: s.n_rw)
    data_pages = property(lambda s: s.n_data)
    ro_pages = property(lambda s: s.n_ro)
    pool_chunks = property(lambda s: s.n_chunks)
    hrt_base = property(lambda s: s.dram_base + s.page)
    cot_base = property(lambda s: s.hrt_base + s.page)
    pool_base = property(lambda s: s.cot_base + ceil(s.pages * 32 / s.page) * s.page)
    fc_base = property(lambda s: s.pool_base + s.n_chunks * s.chunk)
    dram_end = property(lambda s: s.fc_base + s.n_frames * s.page)


TINY = TinyConfig()
ROOMY = TinyConfig(n_frames=22)                           # all 16 RW pages fit and 6 frames are left for the 8 RO pages:
                                                          # for runs in which the LZ4 HW stops answering
TIGHT = TinyConfig(n_frames=3, n_data=1)                  # the two pages of one instruction and one frame more


# ------------------------------------------------------------------------- scheduler
class Task:
    def __init__(self, sched, name, body, core, context='thread'):
        self.sched, self.name, self.body, self.core, self.context = sched, name, body, core, context
        self.state, self.on, self.error = RUNNABLE, None, None
        self.dying = False                                # somebody has ended this thread and it has not noticed yet
        self.gate = threading.Lock()
        self.gate.acquire()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.gate.acquire()
        try:
            if not self.sched.killing:
                self.body(self)
        except Killed:
            pass
        except BaseException as e:                        # reported by the scheduler, in the main thread
            self.error = e
        self.state = DONE
        self.sched.back.release()


class RandomChooser:
    def __init__(self, seed, stay=0.5):
        self.rng, self.stay = random.Random(seed), stay

    def pick(self, step, ready, current):
        if current in ready and self.rng.random() < self.stay:
            return current
        return self.rng.choice(ready)


class PlanChooser:
    """The running task keeps running until it has to wait; then the next one in line runs.
    plan = {step: k} interrupts the running task at that step in favour of the k-th other task.
    alts[step] says how many other tasks could have run at each step."""

    def __init__(self, plan=None):
        self.plan, self.alts = plan or {}, []

    def pick(self, step, ready, current):
        if current in ready:
            others = [t for t in ready if t is not current]
            self.alts.append(len(others))
            k = self.plan.get(step)
            return current if k is None else others[k]
        self.alts.append(0)
        if current is None:
            return ready[0]
        return min(ready, key=lambda t: (t.index - current.index) % len(t.sched.tasks))


class PreferChooser(PlanChooser):
    """The named task runs whenever it can run. Otherwise as PlanChooser without a plan."""

    def __init__(self, name):
        super().__init__()
        self.name = name

    def pick(self, step, ready, current):
        for t in ready:
            if t.name == self.name:
                return t
        return super().pick(step, ready, current)


class Scheduler:
    def __init__(self, chooser):
        self.chooser = chooser
        self.tasks, self.current = [], None
        self.back = threading.Lock()
        self.back.acquire()
        self.steps, self.killing = 0, False
        self.kill_anywhere = False                        # the mutant: a thread that is ended does not finish its kernel procedure
        self.trace = deque(maxlen=40)
        self.left = []

    def spawn(self, name, body, core=0, context='thread'):
        t = Task(self, name, body, core, context)
        t.index = len(self.tasks)
        self.tasks.append(t)
        return t

    def run(self, limit=1_000_000):
        for t in self.tasks:
            t.thread.start()
        try:
            while True:
                ready = [t for t in self.tasks if t.state == RUNNABLE]
                if not ready:
                    break
                t = self.chooser.pick(self.steps, ready, self.current)
                self.steps += 1
                self.current = t
                t.gate.release()
                self.back.acquire()
                if t.error is not None:
                    t.error.add_note(self.describe(t))
                    raise t.error
                if self.steps > limit:
                    raise NoProgress(f'{limit} scheduling steps and still not finished')
            self.left = [(t, t.on) for t in self.tasks if t.state == BLOCKED]
        finally:
            self.killing = True
            for t in self.tasks:
                if t.state != DONE and t.thread.is_alive():
                    t.gate.release()
                    self.back.acquire()
            self.current = None

    def describe(self, t):
        last = ', '.join(f'{name}:{what}' for name, what in self.trace)
        return f'in task {t.name} at scheduling step {self.steps}; the last steps were {last}'

    # ---- called by the running task
    def pause(self, what):
        """A point where another task may run first. The caller stays runnable."""
        t = self.current
        self.trace.append((t.name, what))
        self.back.release()
        t.gate.acquire()
        if self.killing:
            raise Killed
        if t.dying and self.kill_anywhere:
            raise Terminated

    def block(self, key):
        """Sleep until somebody calls wake(key)."""
        t = self.current
        t.state, t.on = BLOCKED, key
        self.trace.append((t.name, f'waits for {key}'))
        self.back.release()
        t.gate.acquire()
        if self.killing:
            raise Killed
        if t.dying and self.kill_anywhere:
            raise Terminated

    def wake(self, key):
        for t in self.tasks:
            if t.state == BLOCKED and t.on == key:
                t.state, t.on = RUNNABLE, None


# ------------------------------------------------------------------------------ port
class Job:
    def __init__(self, desc, d, task):
        self.desc, self.task, self.cpl, self.done = desc, task, None, False
        self.frame, self.chunks = d['frame_pa'], set(d['chunk'][:d['count']])

    def __repr__(self):
        return f'job on frame {self.frame:#x}'


class ConcPort(Port):
    """The port when several threads call the kernel. Also one TLB per core."""

    def __init__(self, m):
        super().__init__(m)
        self.sched = m.sched
        self.holder = None                                # task that holds the lock
        self.jobs = deque()                               # handed to the LZ4 HW and not completed; the first is in flight
        self.reclaim_event = False
        self.tlb = [{} for _ in range(m.cores)]
        self.shootdown = True                             # pte_unmap flushes the TLB of every core
        self.atomic_wait = True                           # unlock and sleep are one step

    def _held(self):
        if not self.booting and self.holder is not self.sched.current:
            raise KernelBug('kernel table touched without the lock')

    def lock(self):
        s = self.sched
        s.pause('lock')
        while self.locked:
            self.st['lock_waits'] += 1
            s.block('lock')
        super().lock()
        self.holder = s.current

    def unlock(self):
        if self.holder is not self.sched.current:
            raise KernelBug('unlock by a thread that does not hold the lock')
        super().unlock()
        self.holder = None
        self.sched.wake('lock')

    def pte_unmap(self, h):
        super().pte_unmap(h)
        for tlb in self.tlb if self.shootdown else [self.tlb[self.sched.current.core]]:
            tlb.pop(h, None)

    def lz4_job(self, desc):
        s, k, cfg = self.sched, self.m.kernel, self.cfg
        if self.holder is s.current:
            raise KernelBug('job handed to the LZ4 HW with the lock held')
        job = Job(desc, self.m.spec.unpack('job_desc', desc), s.current)
        for other in self.jobs:
            if other.frame == job.frame or other.chunks & job.chunks:
                raise JobRace(f'two jobs at once on frame {job.frame:#x} or on one of its chunks')
        h = k.owner[(job.frame - cfg.fc_base) // cfg.page]
        if h >= 0 and k.pins[h]:
            raise JobRace(f'the frame of pinned page {h:#x} was given to the LZ4 HW')
        self.jobs.append(job)
        self.st['jobs_queued_max'] = max(self.st['jobs_queued_max'], len(self.jobs))
        s.wake('hw')
        while not job.done:
            s.block(job)
        return job.cpl                                    # None: the HW never answered and the driver has given up

    def wait_page(self, h):
        self._held()
        self.st['wait_page_' + S_NAME[self.m.kernel.state[h]]] += 1
        self.unlock()                                     # unlock and sleep are one step: no wake-up can fall between
        if not self.atomic_wait:
            self.sched.pause('about to sleep')
        self.sched.block(('page', h))
        self.lock()

    def wake_page(self, h):
        self._held()
        self.sched.wake(('page', h))

    def wait_frame(self):
        self._held()
        self.st['wait_frame'] += 1
        self.unlock()
        if not self.atomic_wait:
            self.sched.pause('about to sleep')
        self.sched.block('frame')
        self.lock()

    def wake_frame(self):
        self._held()
        self.sched.wake('frame')

    def wake_reclaimer(self):
        self.reclaim_event = True                         # kept even if the reclaimer is in the middle of a pass
        self.sched.wake('reclaimer')

    def may_wait(self):
        return self.sched.current.context == 'thread'

    def thread(self):
        return self.sched.current.name


# --------------------------------------------------------------------------- machine
class ConcMachine(Machine):
    PORT = ConcPort

    def __init__(self, cfg=TINY, seed=1, chooser=None, cores=2, protect=2, **kw):
        self.sched = Scheduler(chooser or RandomChooser(seed))
        self.cores = cores
        super().__init__(cfg, seed, protect=protect, **kw)
        self.kinds = Counter()
        self.ended = {}

    # ---- the tasks
    def _hw(self, task):
        s, port = self.sched, self.port
        while True:
            while not port.jobs:
                s.block('hw')
            job = port.jobs[0]
            s.pause('job in flight')                      # everybody else runs while the HW works
            job.cpl, job.done = self.hw.run(job.desc), True
            port.jobs.popleft()
            s.wake(job)

    def _reclaimer(self, task):
        s, port = self.sched, self.port
        while True:
            while not port.reclaim_event:
                s.block('reclaimer')
            port.reclaim_event = False
            self.kernel.reclaim()
            s.pause('reclaimer about to sleep')           # a request that arrives here must not be lost

    def _user(self, script):
        def body(task):
            k, held, end = self.kernel, [], 'done'
            try:
                for op, h, *arg in script:
                    if task.dying:                        # ended by somebody: noticed here, between two kernel entries
                        end = 'killed'
                        break
                    if op == 'run':                       # one instruction on code page h, perhaps with a data page
                        uses = [(h, False, True)] + ([(arg[0], arg[1], False)] if arg[0] is not None else [])
                        r = self.instruction(task, uses)
                    elif op == 'pin':
                        r = k.pin_page(h)
                        if r == 'pinned':
                            held.append(h)
                    elif op == 'unpin':
                        r = k.unpin_page(h)
                        held.remove(h)
                    elif op == 'isr':                     # an interrupt handler reads or writes page h
                        task.context = 'isr'
                        r = self.instruction(task, [(h, arg[0], False)])
                        task.context = 'thread'
                    elif op == 'alias':                   # kernel code reaches page h through its own mapping
                        r = self.alias(h, arg[0])
                    elif op == 'damage':
                        r = self.damage(h)
                    elif op == 'context':                 # from here on this is an ISR or an HRT thread
                        task.context, r = h, None
                    elif op == 'hwfault':                 # the next job of this opcode goes wrong in the LZ4 HW
                        r = self.hw.inject(h, arg[0])
                    elif op == 'hwdown':                  # the LZ4 HW stops answering for good
                        self.hw.down, r = True, None
                    elif op == 'kill':                    # this thread ends user thread h
                        r = self.kill(h)
                    if r in ('lost', 'killed'):           # the program cannot go on: it is ended
                        end = r
                        break
            except Terminated:                            # the mutant only: torn out in the middle of a kernel procedure
                end, task.dying = 'killed', False
            for h in held:
                k.unpin_page(h)
            self.port.lock()
            k.thread_gone(task.name)
            self.port.unlock()
            self.ended[task.name] = end
        return body

    # ---- the CPU
    def translate(self, core, h):
        port = self.port
        pa = port.tlb[core].get(h)
        if pa:
            if port.pte[h] != pa:
                raise StaleTlb(f'core {core} still translates page {h:#x} to {pa:#x}, the PTE says {port.pte[h]:#x}')
            return pa
        if port.pte[h]:
            port.tlb[core][h] = port.pte[h]
        return port.pte[h]

    def instruction(self, task, uses):
        """One instruction. It runs only when every page it needs is mapped at the same moment."""
        s, tries = self.sched, 0
        while True:
            s.pause('cpu')                                # between the return from a fault and the instruction
            for h, write, code in uses:
                if not self.translate(task.core, h):
                    r = self.kernel.page_fault(h)
                    self.kinds[r] += 1
                    if r == 'lost':
                        return 'lost'
                    if task.dying:                        # the fault has been served to its end; the instruction is not run
                        return 'killed'
                    tries += 1
                    if tries > RETRY_LIMIT * len(uses):
                        raise NoProgress(f'the instruction on pages {[hex(u[0]) for u in uses]} faulted {tries} times')
                    break
            else:
                break
        self.kinds['instructions'] += 1
        for h, write, code in uses:
            self.use(h, self.port.pte[h], write, code)
        return 'ran'

    def use(self, h, pa, write, code):
        port = self.port
        for job in port.jobs:
            if job.frame == pa:
                raise JobRace(f'the CPU touches frame {pa:#x} of page {h:#x} while a job owns it')
        self.cache.cpu_uses(pa, write, code)
        mv = self.dram.view(pa, self.cfg.page)
        if crc32(mv) != self.expect[h]:
            raise DataMismatch(f'page {h:#x} does not hold what user SW last wrote')
        port.accessed[h] = 1
        if write:
            port.dirty[h] = 1
            if self.expect[h] == self.zero_crc:
                self.wl.fill(mv)
            else:
                self.wl.mutate(mv)
            self.expect[h] = crc32(mv)

    def alias(self, h, write):
        f = self.kernel.frame_of[h]
        if f < 0:
            raise AliasError(f'kernel code used its own mapping of page {h:#x}, which has no frame')
        self.use(h, self.cfg.frame_pa(f), write, False)
        return 'ran'

    def kill(self, i):
        """The running thread ends user thread i. The victim finishes the kernel procedure it is in, if any."""
        s, t = self.sched, self.users[i]
        if t.state != DONE and t is not s.current and not t.dying:
            t.dying = True
            self.st['kills'] += 1
            if s.kill_anywhere and t.state == BLOCKED:    # the mutant: it does not wait for what it sleeps on
                t.state, t.on = RUNNABLE, None

    def damage(self, h):
        """Fault injection: one byte of the stored stream of page h, if it is stored right now."""
        if self.kernel.state[h] == COMPRESSED and h not in self.corrupted:
            e = self.spec.unpack('cot_entry', self.dram.view(self.cfg.entry_pa(h), 32))
            self.dram.view(self.cfg.chunk_pa(e['chunk'][0]), self.cfg.chunk)[0] ^= 0xFF
            self.corrupted.add(h)
            self.st['injected'] += 1

    # ---- one whole run
    def go(self, scripts, contexts=None):
        from .check import audit
        s = self.sched
        s.spawn('LZ4 HW', self._hw)
        self.reclaimer_task = s.spawn('reclaimer', self._reclaimer, core=self.cores - 1)
        self.users = users = [s.spawn(f'user{i}', self._user(sc), core=i % self.cores) for i, sc in enumerate(scripts)]
        s.run()
        stuck = [(t, on) for t, on in s.left if t in users]
        if stuck:
            what = ', '.join(f'{t.name} waits for {on}' for t, on in stuck)
            if all(on == 'frame' for _, on in stuck) and not self.could_free():
                raise OutOfMemory(what)
            raise Deadlock(what)
        self.result = audit(self)
        return self

    def could_free(self):
        """Is there a free frame, or a page the reclaimer would be allowed to take?"""
        k, cfg = self.kernel, self.cfg
        if k.free_frames:
            return True
        for h in range(cfg.pages):
            if k.state[h] == PRESENT and not k.pins[h] and not k.fresh_n[h]:
                if cfg.is_ro(h) or not (k.pool_full or k.lz4_off or h in k.incompressible):
                    return True
        return False


# --------------------------------------------------------------------------- scripts
HW_FAULTS = (('COMPRESS', 'bus_error'), ('DECOMPRESS', 'bus_error'), ('DECOMPRESS', 'bad_stream'))


def scripts(cfg=TINY, seed=1, users=3, length=30, pin=True, damage=0.0, forget_pin=False,
            faults=0, hw_down=False, kill=False, fault_kinds=HW_FAULTS):
    """What each user SW thread does. Two RW pages and one RO page are used by everybody,
    the rest is split between the threads. forget_pin: the driver uses pages without pinning them.
    faults, hw_down, kill: the last thread also makes that many jobs of the LZ4 HW fail, makes the HW
    stop answering, ends the first thread. They are added to the same scripts, which do not change otherwise."""
    rng = random.Random(seed * 1000003 + 17)
    shared_rw, shared_ro = [0, cfg.n_data], cfg.ro_first
    own_rw = [h for h in range(cfg.rw_pages) if h not in shared_rw]
    own_ro = list(range(cfg.ro_first + 1, cfg.pages))
    out = []
    for i in range(users):
        rw, ro = own_rw[i::users], own_ro[i::users]
        sc = []
        while len(sc) < length:
            x = rng.random()
            if pin and i == 0 and x < 0.08:               # a driver: pin, use from an ISR and through the alias, unpin
                h = rng.choice(shared_rw + rw)
                ops = [('pin', h), ('isr', h, rng.random() < 0.5), ('alias', h, True), ('unpin', h)]
                sc += ops[1:3] if forget_pin else ops
            elif 0.08 <= x < 0.08 + damage:
                sc.append(('damage', rng.choice(shared_rw + rw)))
            else:
                code = shared_ro if rng.random() < 0.3 else rng.choice(ro)
                y = rng.random()
                data = None if y < 0.15 else rng.choice(shared_rw) if y < 0.5 else rng.choice(rw)
                sc.append(('run', code, data, data is not None and rng.random() < 0.4))
        out.append(sc)
    extra, last = random.Random(seed * 7919 + 5), out[-1]
    for _ in range(faults):
        last.insert(extra.randrange(len(last) + 1), ('hwfault', *extra.choice(fault_kinds)))
    if hw_down:
        last.insert(extra.randrange(len(last) // 2 + 1), ('hwdown', None))
    if kill and users > 1:
        last.insert(extra.randrange(len(last) + 1), ('kill', 0))
    return out


SCRIPT_KW = ('users', 'length', 'pin', 'damage', 'forget_pin', 'script_seed', 'faults', 'hw_down', 'kill', 'fault_kinds')


def one(seed=1, chooser=None, machine=ConcMachine, cfg=TINY, change=None, prepare=None, **kw):
    """Build, boot and run one machine. `prepare` may alter it before boot, `change` between boot and the run."""
    script_kw = {k: kw.pop(k) for k in SCRIPT_KW if k in kw}
    if kw.pop('reclaimer_first', False):
        chooser = PreferChooser('reclaimer')
    m = machine(cfg, seed=seed, chooser=chooser, **kw)
    m.build_image()
    if prepare:
        prepare(m)
    m.boot()
    if change:
        change(m)
    return m.go(scripts(cfg, script_kw.pop('script_seed', seed), **script_kw))


def explore(bound=1, run=None, **kw):
    """Every schedule with at most `bound` interruptions of a running task. Returns how many there were."""
    run = run or one
    runs = 0

    def level(plan, after, left):
        nonlocal runs
        ch = PlanChooser(plan)
        try:
            run(chooser=ch, **kw)
        except Exception as e:
            e.add_note(f'schedule: interruptions {plan}, as step: number of the task that runs instead')
            raise
        runs += 1
        if left:
            for step in range(after, len(ch.alts)):
                for k in range(ch.alts[step]):
                    level({**plan, step: k}, step + 1, left - 1)
    level({}, 0, bound)
    return runs


# --------------------------------------------------------------------------- mutants
# Each one takes away a single thing the control procedure does. If no check stops the
# machine afterwards, the check is missing or the thing was not needed.
def _without(call):
    def change(m):
        setattr(m.port, call, lambda *a: None)
    return change


def _skip_state(state):
    def change(m):
        real = m.kernel.set_state
        m.kernel.set_state = lambda h, s: None if s == state else real(h, s)
    return change


def _local_flush(m):
    m.port.shootdown = False


def _dcache_only(m):
    m.port.cache_invalidate = lambda pa: m.cache.invalidate(pa, icache=False)


def _unlatched(m):
    def wake_reclaimer():
        t = m.reclaimer_task
        if t.state == BLOCKED and t.on == 'reclaimer':    # a request that arrives during a pass is dropped
            m.port.reclaim_event = True
            m.sched.wake('reclaimer')
    m.port.wake_reclaimer = wake_reclaimer


def _sleepy_wait(m):
    m.port.atomic_wait = False


def _shared_tag(m):
    k = m.kernel

    def lz4_job(**fields):                                # as it was before this file existed
        k.tag = (k.tag + 1) & 0xFFFFFFFF or 1
        cpl = k.spec.unpack('completion', k.port.lz4_job(k.spec.pack('job_desc', dict(fields, tag=k.tag))))
        if cpl['tag'] != k.tag:
            raise KernelBug(f'completion tag {cpl["tag"]:#x}, expected {k.tag:#x}')
        return cpl
    k.lz4_job = lz4_job


def _no_sw_decode(m):
    m.kernel.sw_decode = lambda h, e, chunks, pa: False   # the page is given up at the first answer that is not OK


def _leak_on_failure(m):
    real = m.bitmap.release
    m.bitmap.release = lambda chunks, op='release': None if op == 'failed' else real(chunks, op)


def _kill_anywhere(m):
    m.sched.kill_anywhere = True


def _sw_decode_no_clean(m):
    real_sw, real_clean, skip = m.kernel.sw_decode, m.port.cache_clean, set()
    m.port.cache_clean = lambda pa: None if pa in skip else real_clean(pa)

    def sw_decode(h, e, chunks, pa):
        skip.add(pa)
        try:
            return real_sw(h, e, chunks, pa)
        finally:
            skip.discard(pa)
    m.kernel.sw_decode = sw_decode


def _cached_chunk_read(m):
    real = m.port.chunk_read
    m.port.chunk_read = lambda c: real(c, fresh=False)


MUTANTS = {
    'shared_tag': dict(change=_shared_tag),
    'no_wake_frame': dict(change=_without('wake_frame')),
    'no_wake_page': dict(change=_without('wake_page')),
    'wait_not_atomic': dict(change=_sleepy_wait),
    'unlatched_reclaimer': dict(change=_unlatched),
    'no_decompressing': dict(change=_skip_state(DECOMPRESSING)),
    'no_compressing': dict(change=_skip_state(COMPRESSING)),
    'local_tlb_flush': dict(change=_local_flush),
    'no_cache_clean': dict(change=_without('cache_clean')),
    'no_cache_invalidate': dict(change=_without('cache_invalidate')),
    'invalidate_dcache_only': dict(change=_dcache_only),
    'forget_pin': dict(forget_pin=True),
    # one user thread on three frames, and a reclaimer of higher priority than user SW
    'protect_1': dict(protect=1, cfg=TIGHT, users=1, pin=False, reclaimer_first=True),
    # two user threads on three frames: fewer frames than the sizing rule asks for
    'too_few_frames': dict(cfg=TIGHT, users=2, pin=False),
    # the four below need something to go wrong first: jobs that fail, a thread that is ended, a cache that is not empty at boot
    'no_sw_decode': dict(change=_no_sw_decode, faults=2, fault_kinds=(('DECOMPRESS', 'bad_stream'), ('DECOMPRESS', 'bus_error'))),
    'sw_decode_no_clean': dict(change=_sw_decode_no_clean, faults=2,
                               fault_kinds=(('DECOMPRESS', 'bad_stream'), ('DECOMPRESS', 'bus_error'))),
    'leak_on_job_failure': dict(change=_leak_on_failure, faults=2, fault_kinds=(('COMPRESS', 'bus_error'),)),
    'kill_in_kernel': dict(change=_kill_anywhere, kill=True),
    'no_boot_flush': dict(prepare=_without('cache_flush_layer')),
    'chunk_read_cached': dict(change=_cached_chunk_read, verify=True),
}


def first_failure(name, runs=300, **kw):
    """Run a mutant under random schedules until a check stops it: (schedule number, exception) or None."""
    for seed in range(1, runs + 1):
        try:
            one(seed, **dict(MUTANTS[name], **kw))
        except Exception as e:
            return seed, e
    return None


# ------------------------------------------------------------------ numbers for the document
def survey(runs=300, **kw):
    """Random schedules of the kernel as it is. Every one must end clean. Returns what happened in them."""
    n = Counter()
    for seed in range(1, runs + 1):
        m = one(seed, **kw)
        n['schedules'] += 1
        n['steps'] += m.sched.steps
        n['jobs_queued_max'] = max(n['jobs_queued_max'], m.port.st.pop('jobs_queued_max', 0))
        for src in (m.kinds, m.port.st, m.hw.st):
            n.update(src)
        n.update({'cache_' + k: v for k, v in m.cache.st.items()})
        n.update({k: m.kernel.st[k] for k in ('pin_page', 'unpin_page', 'evict_ro', 'evict_rw', 'reclaim_stuck',
                                              'sw_decode', 'sw_decode_ok', 'compress_failed', 'lz4_off',
                                              'verified', 'verify_failed')})
        n['injected'] += m.st['injected']
        n['kills'] += m.st['kills']
        n['threads_ended_lost'] += sum(1 for end in m.ended.values() if end == 'lost')
        n['threads_ended_killed'] += sum(1 for end in m.ended.values() if end == 'killed')
        n['lost_pages'] += m.result.get('lost', 0)
        n['streams_checked'] += m.result.get('streams_checked', 0)
    return dict(n)


EXPLORE = (dict(bound=1, seed=1, users=2, length=8), dict(bound=2, seed=1, users=2, length=8),
           dict(bound=1, seed=3, users=3, length=30))


def explore_table(cases=EXPLORE):
    return [dict(case, schedules=explore(**case)) for case in cases]


def mutant_table(runs=300):
    rows = []
    for name in MUTANTS:
        hit = first_failure(name, runs)
        rows.append({'name': name, 'schedule': hit[0] if hit else None,
                     'stopped_by': type(hit[1]).__name__ if hit else None, 'text': str(hit[1]) if hit else None})
    return rows
