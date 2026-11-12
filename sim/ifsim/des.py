"""A small discrete-event kernel: integer nanoseconds, generator processes.

A process is a generator that yields Event objects and is resumed with the
event's value when it fires. Nothing here knows about the design.
"""
import heapq
from collections import deque


class Event:
    __slots__ = ('sim', 'done', 'value', '_cbs')

    def __init__(self, sim):
        self.sim = sim
        self.done = False
        self.value = None
        self._cbs = []

    def succeed(self, value=None):
        if self.done:
            raise RuntimeError('event fired twice')
        self.done = True
        self.value = value
        cbs, self._cbs = self._cbs, None
        push, now = self.sim._push, self.sim.now
        for cb in cbs:
            push(now, cb, self)
        return self

    def then(self, cb):
        if self.done:
            self.sim._push(self.sim.now, cb, self)
        else:
            self._cbs.append(cb)


class Process(Event):
    __slots__ = ('gen', 'name')

    def __init__(self, sim, gen, name=''):
        super().__init__(sim)
        self.gen = gen
        self.name = name
        sim._push(sim.now, self._step, None)

    def _step(self, ev):
        try:
            nxt = self.gen.send(ev.value if ev is not None else None)
        except StopIteration as e:
            self.succeed(e.value)
            return
        nxt.then(self._step)


class Sim:
    def __init__(self):
        self.now = 0
        self._q = []
        self._n = 0
        self.events = 0

    def _push(self, t, fn, arg):
        heapq.heappush(self._q, (t, self._n, fn, arg))
        self._n += 1

    def event(self):
        return Event(self)

    def timeout(self, delay, value=None):
        ev = Event(self)
        self._push(self.now + int(delay), ev.succeed, value)
        return ev

    def process(self, gen, name=''):
        return Process(self, gen, name)

    def any_of(self, *evs):
        out = Event(self)

        def cb(ev):
            if not out.done:
                out.succeed(ev)
        for e in evs:
            e.then(cb)
        return out

    def run(self, until=None, stop=None):
        q = self._q
        pop = heapq.heappop
        while q:
            if until is not None and q[0][0] > until:
                self.now = until
                return
            t, _, fn, arg = pop(q)
            self.now = t
            self.events += 1
            fn(arg)
            if stop is not None and stop.done:
                return


class Resource:
    """A counted resource with a FIFO queue; keeps busy time and waiting time."""

    def __init__(self, sim, name, capacity=1):
        self.sim = sim
        self.name = name
        self.cap = capacity
        self.users = 0
        self.q = deque()
        self.busy_ns = 0
        self.wait_ns = 0
        self.grants = 0
        self.waited = 0
        self.max_q = 0
        self._t = 0

    def _account(self):
        now = self.sim.now
        self.busy_ns += self.users * (now - self._t)
        self._t = now

    def acquire(self):
        ev = Event(self.sim)
        if self.users < self.cap:
            self._account()
            self.users += 1
            self.grants += 1
            ev.succeed(0)
        else:
            self.q.append((ev, self.sim.now))
            if len(self.q) > self.max_q:
                self.max_q = len(self.q)
        return ev

    def release(self):
        self._account()
        if self.q:
            ev, t = self.q.popleft()
            w = self.sim.now - t
            self.wait_ns += w
            self.waited += 1
            self.grants += 1
            ev.succeed(w)
        else:
            self.users -= 1


class Signal:
    """Broadcast wake-up: everyone waiting on wait() resumes at the next fire()."""

    def __init__(self, sim):
        self.sim = sim
        self._ev = None

    def wait(self):
        if self._ev is None or self._ev.done:
            self._ev = Event(self.sim)
        return self._ev

    def fire(self):
        if self._ev is not None and not self._ev.done:
            self._ev.succeed()
