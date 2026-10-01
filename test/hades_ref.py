from dataclasses import dataclass, field

from hades_tb import *


@dataclass
class SimState:
    sram: list = field(default_factory=lambda: [0] * 16)
    Q: int = 0
    A: int = 0
    MASK: int = 0xFFFFFFFF
    min_dist: int = 0x3F
    min_idx: int = 0
    min2_dist: int = 0x3F
    min2_idx: int = 0
    MATCH: int = 0
    count: int = 0
    MIN_VALID: bool = False
    THRESHOLD_HIT: bool = False


def model_popcount(x):
    return bin(x & 0xFFFFFFFF).count('1')


def scan_rst_init(state, op):
    if op in (HAM, HAM2, THR):
        state.min_dist = 0x3F
        state.min_idx = 0
        state.MIN_VALID = False
    if op == HAM2:
        state.min2_dist = 0x3F
        state.min2_idx = 0
    if op in (THR, EQUAL):
        state.MATCH = 0
        state.count = 0
    if op == THR:
        state.THRESHOLD_HIT = False
    if op == ROR:
        state.A = 0x00000000
    if op == RAND:
        state.A = 0xFFFFFFFF
    if op == RPOP:
        state.A = 0
    if op == RMAXPOP:
        state.min_dist = 0
        state.min_idx = 0
        state.MIN_VALID = False


def scan_row(state, row, op):
    mem = state.sram[row]
    masked = mem & state.MASK
    if op == HAM:
        d = model_popcount((mem ^ state.Q) & state.MASK)
        if d < state.min_dist:
            state.min_dist = d
            state.min_idx = row
        state.MIN_VALID = True
    elif op == HAM2:
        d = model_popcount((mem ^ state.Q) & state.MASK)
        if d < state.min_dist:
            state.min2_dist = state.min_dist
            state.min2_idx = state.min_idx
            state.min_dist = d
            state.min_idx = row
        elif d < state.min2_dist:
            state.min2_dist = d
            state.min2_idx = row
        state.MIN_VALID = True
    elif op == THR:
        d = model_popcount((mem ^ state.Q) & state.MASK)
        if d < state.min_dist:
            state.min_dist = d
            state.min_idx = row
        thresh = state.A & 0xFF
        if d <= thresh:
            state.MATCH |= (1 << row)
            state.count = min(31, state.count + 1)
            state.THRESHOLD_HIT = True
        state.MIN_VALID = True
    elif op == EQUAL:
        if ((mem ^ state.Q) & state.MASK) == 0:
            state.MATCH |= (1 << row)
            state.count = min(31, state.count + 1)
    elif op == ROR:
        state.A = (state.A | masked) & 0xFFFFFFFF
    elif op == RAND:
        state.A = (state.A & masked) & 0xFFFFFFFF
    elif op == RPOP:
        state.A = min(512, state.A + model_popcount(masked))
    elif op == RMAXPOP:
        p = model_popcount(masked)
        if p > state.min_dist:
            state.min_dist = p
            state.min_idx = row
        state.MIN_VALID = True


ALL_EMITS = [E_A0, E_A1, E_A2, E_A3, E_MLO, E_MHI, E_CNT, E_FLG, E_IDX, E_DIST]


def m_scan(st, base, ln, op, acc, rows, q, mask):
    if not acc:
        if op == EQUAL:
            st["match"], st["count"] = 0, 0
        elif op == ROR:
            st["A"] = 0
        elif op == RAND:
            st["A"] = ALL_ONES
    for r in range(base, min(base + ln - 1, 15) + 1):
        x = (rows[r] ^ q) & mask if op == EQUAL else rows[r] & mask
        if op == EQUAL:
            if x == 0:
                st["match"] |= 1 << r
                st["count"] = min(31, st["count"] + 1)
        elif op == ROR:
            st["A"] |= x
        else:
            st["A"] &= x


def m_emits(st):
    a = st["A"]
    return [a & 0xFF, (a >> 8) & 0xFF, (a >> 16) & 0xFF, a >> 24, st["match"] & 0xFF, st["match"] >> 8,
            st["count"], 0, 0, 0x3F]


def scanp_prog(rows, q, mask, a0, scans, mn="scanp", pad=0):
    p = Prog()
    p.wb32(0, q)
    p.wb32(2, mask)
    p.wb32(1, a0)
    for _ in range(pad):
        p.unmask() if mask == ALL_ONES else p.send(E_FLG)
    st = {"A": a0, "match": 0, "count": 0}
    exp = []
    if pad and mask != ALL_ONES:
        exp = [0] * pad
    for sc in scans:
        getattr(p, mn)(*sc)
        m_scan(st, sc[0], sc[1], sc[2], sc[3], rows, q, mask)
    for e in ALL_EMITS:
        p.send(e)
    p.halt()
    return p, exp + m_emits(st)


def mixed_rows(rng, q):
    rows = []
    for _ in range(16):
        r = rng.random()
        rows.append(q if r < 0.35 else (q ^ (1 << rng.randrange(32))) if r < 0.6 else rng.getrandbits(32))
    return rows


async def run_scanp(h, f, name, prog, exp, rows, until=400):
    await h.reset()
    await h.run(prog, until_halt=until)
    f.chk(h.emits == exp, f"{name}: SEND {[hex(x) for x in h.emits]} expected {[hex(x) for x in exp]}")
    f.chk(h.halt_cycle == len(prog.sched) + HALT_LATENCY,
          f"{name}: HALT at cycle {h.halt_cycle}, model {len(prog.sched) + HALT_LATENCY}")


def rows_mlo(rows, q, n):
    m = 0
    for r in range(min(n, 16)):
        if rows[r] == q:
            m |= 1 << r
    return m & 0xFF


SCANSEL_Q0 = 0x9E3779B9
EMIT_ORDER = [E_IDX, E_DIST, E_A0, E_A1, E_A2, E_A3, E_MLO, E_MHI, E_CNT, E_FLG, E_IDX2, E_DIST2]
SELECTIONS = [0x0000, 0x0001, 0x8000, 0xFFFF, 0x5555, 0xAAAA, 0x0412, 0x8421, 0x00F0, 0x7FFE, 0x0F0F, 0x1000, 0x0003, 0xC000]


def scansel_rows(rng):
    return [SCANSEL_Q0 ^ (1 << r) ^ (rng.getrandbits(16) << 16) for r in range(16)]


class Ref:

    def __init__(self, rows):
        self.s = SimState(sram=list(rows))
        self.invalid = False

    def _chk_pop(self, op, acc):
        if op == RPOP and acc and self.s.A > 100:
            self.invalid = True

    def wb(self, dst, v):
        setattr(self.s, ("Q", "A", "MASK")[dst], v & ALL_ONES)

    def scan(self, base, ln, op, acc):
        self._chk_pop(op, acc)
        if not acc:
            scan_rst_init(self.s, op)
        for r in range(base, min(base + ln - 1, 15) + 1):
            scan_row(self.s, r, op)

    def scansel(self, op, acc):
        self._chk_pop(op, acc)
        sel = [r for r in range(16) if (self.s.MATCH >> r) & 1]
        if not acc:
            scan_rst_init(self.s, op)
        for r in sel:
            scan_row(self.s, r, op)
        return len(sel)

    def emits(self):
        s = self.s
        return [s.min_idx, s.min_dist, s.A & 0xFF, (s.A >> 8) & 0xFF, (s.A >> 16) & 0xFF, s.A >> 24, s.MATCH & 0xFF,
                s.MATCH >> 8, s.count, (s.THRESHOLD_HIT << 1) | s.MIN_VALID, s.min2_idx, s.min2_dist]


def scansel_setup(rows, sel, q_after=None):
    p = Prog()
    ref = Ref(rows)
    for dst, v in ((0, SCANSEL_Q0), (2, (~sel) & 0xFFFF)):
        p.wb32(dst, v)
        ref.wb(dst, v)
    p.scan(0, 16, EQUAL, 0)
    ref.scan(0, 16, EQUAL, 0)
    if q_after is not None:
        p.wb32(0, q_after)
        ref.wb(0, q_after)
        p.wb32(1, 0)
        ref.wb(1, 0)
    while len(p.words) < 32:
        p.halt()
    return p, ref


def scansel_body(ref, q, mask, a0, steps, emit_all=True, scansel_k=None):
    p = Prog()
    exp = []
    for dst, v in ((0, q), (2, mask), (1, a0)):
        if v is not None:
            p.wb32(dst, v)
            ref.wb(dst, v)
    for st in steps:
        if st[0] == 'wb':
            p.wb32(st[1], st[2])
            ref.wb(st[1], st[2])
        elif st[0] == 'wb8':
            p.wb(st[1], 0, st[2])
            old = (ref.s.Q, ref.s.A, ref.s.MASK)[st[1]]
            ref.wb(st[1], (old & ~0xFF) | st[2])
        elif st[0] == 'sta':
            p.sta(st[1])
            ref.s.sram[st[1]] = ref.s.A & ALL_ONES
        elif st[0] == 'scan':
            p.scan(*st[1:])
            ref.scan(*st[1:])
        elif st[0] == 'scanp':
            p.scanp(*st[1:])
            ref.scan(*st[1:])
        elif st[0] == 'scansel':
            k = ref.scansel(st[1], st[2])
            p.scansel(st[1], st[2], k)
        elif st[0] == 'emit':
            p.send(st[1])
            exp.append(ref.emits()[EMIT_ORDER.index(st[1])])
    if emit_all:
        for e in EMIT_ORDER:
            p.send(e)
        exp += ref.emits()
    p.halt()
    if len(p.words) > 32:
        raise OverflowError(f"test program too long: {len(p.words)} slots")
    return p, exp


async def run_pair(h, f, name, rows, p0, p1, exp, until=900):
    await h.fresh(rows)
    await h.run(p0, until_halt=300)
    h.emits.clear()
    await h.load(p1.words)
    await h.execute_request()
    await h.run_schedule(p1.sched, until_halt=until)
    f.chk(h.emits == exp, f"{name}: SEND {[hex(x) for x in h.emits]} expected {[hex(x) for x in exp]}")
    f.chk(h.halt_cycle == len(p1.sched) + HALT_LATENCY, f"{name}: HALT at cycle {h.halt_cycle}, model {len(p1.sched) + HALT_LATENCY}")
    return h.emits, h.halt_cycle


async def run_scansel(h, f, name, rows, sel, q, mask, a0, steps, until=900):
    steps = list(steps)
    while True:
        p0, ref = scansel_setup(rows, sel)
        try:
            p1, exp = scansel_body(ref, q, mask, a0, steps)
            break
        except OverflowError:
            steps.pop()
    if ref.invalid:
        return None, None
    return await run_pair(h, f, name, rows, p0, p1, exp, until)


async def run_body(h, f, name, rows, q, mask, a0, steps, until=900):
    ref = Ref(rows)
    p1, exp = scansel_body(ref, q, mask, a0, steps)
    await h.fresh(rows)
    await h.run(p1, until_halt=until)
    f.chk(h.emits == exp, f"{name}: SEND {[hex(x) for x in h.emits]} expected {[hex(x) for x in exp]}")
    f.chk(h.halt_cycle == len(p1.sched) + HALT_LATENCY, f"{name}: HALT at cycle {h.halt_cycle}, model {len(p1.sched) + HALT_LATENCY}")
    return h.emits, h.halt_cycle
