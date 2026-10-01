import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

UIO_STROBE = 1 << 3
UIO_LD = 1 << 4
UIO_EXEC = 1 << 5

E_IDX, E_DIST, E_A0, E_A1, E_A2, E_A3, E_MLO, E_MHI, E_CNT, E_FLG, E_IDX2, E_DIST2 = range(12)
HAM, HAM2, THR, EQUAL, ROR, RAND, RPOP, RMAXPOP = range(8)
C_ALWAYS, C_THR, C_NTHR, C_MINV, C_CNTNZ, C_MATNZ, C_AZ, C_ANZ = range(8)
INIT_CLOCKS = 18
HALT_LATENCY = 1
DEF_ROWS = [j * 0x01010101 for j in range(16)]
ALL_ONES = 0xFFFFFFFF


class Prog:

    def __init__(self, gap=0):
        self.words = []
        self.sched = []
        self.gap = gap
        self.gap_left = 0

    def _cycles(self, n):
        for _ in range(n):
            self.sched.append((0, 0 if self.gap_left else 1))
            self.gap_left = max(0, self.gap_left - 1)

    def word(self, w, cycles=1):
        self.words.append(w)
        self._cycles(cycles)

    def wb(self, dst, pos, byte):
        self.words.append(0x5000 | (dst << 10) | (pos << 8))
        while self.gap_left:
            self._cycles(1)
        self.sched.append((byte, 1))
        self.gap_left = self.gap

    def wb32(self, dst, value):
        for pos in range(4):
            self.wb(dst, pos, (value >> (8 * pos)) & 0xFF)

    def loadq(self, byte):
        for pos in range(4):
            self.wb(0, pos, byte)

    def loada(self, *b):
        for pos in range(4):
            self.wb(1, pos, b[pos])

    def sta(self, row):
        self.word(0x3000 | (row << 8))

    def scan(self, base, length, op, acc=0):
        rows = min(base + length - 1, 15) - base + 1
        self.word(0x4000 | (base << 8) | ((length - 1) << 4) | (acc << 3) | op, rows + 1)

    def scanp(self, base, length, op, acc=0):
        rows = min(base + length - 1, 15) - base + 1
        cyc = 1 + (rows + 1) // 2 if op in (EQUAL, ROR, RAND) else rows + 1
        self.word(0xA000 | (base << 8) | ((length - 1) << 4) | (acc << 3) | op, cyc)

    def scansel(self, op, acc, k):
        self.word(0xB000 | (acc << 3) | op, 1 + k)

    def send(self, src):
        self.word(0x6000 | (src << 8))

    def branch(self, cond, off):
        self.word(0x7000 | (cond << 8) | (off & 0xFF))

    def unmask(self):
        self.word(0x9000)

    def ldq(self, row):
        self.word(0x0000 | (row << 8), 2)

    def lda(self, row):
        self.word(0x1000 | (row << 8), 2)

    def ldm(self, row):
        self.word(0x2000 | (row << 8), 2)

    def halt(self):
        self.word(0x8000)


def popcount(x):
    return bin(x).count("1")


def nearest(rows, q):
    d = [popcount(r ^ q) for r in rows]
    best = min(d)
    return d.index(best), best, d


class Fails(list):
    def chk(self, cond, msg):
        if not cond:
            self.append(msg)

    def done(self):
        assert not self, "\n".join(self)


class Host:
    def __init__(self, dut):
        self.dut = dut
        self.uio = 0
        self.emits = []
        self.rows_state = None
        self.cyc = 0
        self.halt_cycle = None
        dut.ena.value = 1
        dut.ui_in.value = 0
        dut.uio_in.value = 0
        dut.rst_n.value = 0
        cocotb.start_soon(Clock(dut.clk, 20, unit="ns").start())
        cocotb.start_soon(self._monitor())

    async def _monitor(self):
        while True:
            await ClockCycles(self.dut.clk, 1)
            if self.dut.rst_n.value.is_resolvable and int(self.dut.rst_n.value) == 1 and self.dut.uio_out.value.is_resolvable:
                if int(self.dut.uio_out.value) & 1:
                    self.emits.append(int(self.dut.uo_out.value))

    def pins(self):
        v = int(self.dut.uio_out.value)
        return {"ready": v & 1, "busy": (v >> 1) & 1, "halt": (v >> 2) & 1}

    def idle(self):
        return self.pins() == {"ready": 0, "busy": 0, "halt": 0}

    def set_uio(self, mask, on):
        self.uio = (self.uio | mask) if on else (self.uio & ~mask)
        self.dut.uio_in.value = self.uio

    async def clocks(self, n):
        await ClockCycles(self.dut.clk, n)

    async def reset(self):
        self.emits.clear()
        self.uio = 0
        self.dut.ui_in.value = 0
        self.dut.uio_in.value = 0
        self.dut.rst_n.value = 0
        await ClockCycles(self.dut.clk, 4)
        self.dut.rst_n.value = 1
        await ClockCycles(self.dut.clk, INIT_CLOCKS)

    async def load_byte(self, b, hold=1):
        self.dut.ui_in.value = b
        self.set_uio(UIO_LD, 1)
        await ClockCycles(self.dut.clk, hold)
        self.set_uio(UIO_LD, 0)
        await ClockCycles(self.dut.clk, 1)

    async def load(self, words):
        for w in words:
            await self.load_byte(w >> 8)
            await self.load_byte(w & 0xFF)
        self.dut.ui_in.value = 0

    async def execute_request(self):
        self.cyc = 0
        self.halt_cycle = None
        self.set_uio(UIO_EXEC, 1)
        await ClockCycles(self.dut.clk, 1)
        self.set_uio(UIO_EXEC, 0)
        await ClockCycles(self.dut.clk, 1)

    async def _cycle(self, b, s):
        self.dut.ui_in.value = b
        self.set_uio(UIO_STROBE, s)
        await ClockCycles(self.dut.clk, 1)
        self.cyc += 1
        if self.halt_cycle is None and self.pins()["halt"]:
            self.halt_cycle = self.cyc

    async def run_schedule(self, sched, tail=3, until_halt=0):
        for b, s in sched:
            await self._cycle(b, s)
        n = 0
        while until_halt and self.halt_cycle is None and n < until_halt:
            await self._cycle(0, 0)
            n += 1
        self.set_uio(UIO_STROBE, 0)
        self.dut.ui_in.value = 0
        for _ in range(tail):
            await self._cycle(0, 0)

    async def run(self, prog, tail=3, until_halt=0):
        await self.load(prog.words)
        await self.execute_request()
        await self.run_schedule(prog.sched, tail, until_halt)

    async def rerun(self, prog, tail=3, until_halt=0):
        await self.execute_request()
        await self.run_schedule(prog.sched, tail, until_halt)

    async def preload(self, rows):
        todo = [r for r in range(16) if self.rows_state is None or self.rows_state[r] != rows[r]]
        for i in range(0, len(todo), 6):
            await self.reset()
            p = Prog()
            for r in todo[i:i + 6]:
                p.wb32(1, rows[r])
                p.sta(r)
            p.halt()
            await self.run(p)
        self.rows_state = list(rows)

    async def fresh(self, rows=None):
        rows = DEF_ROWS if rows is None else rows
        await self.reset()
        if self.rows_state != rows:
            await self.preload(rows)
            await self.reset()
        self.emits.clear()

    async def read_rows(self):
        out = []
        for base in range(0, 16, 6):
            await self.reset()
            p = Prog()
            for r in range(base, min(base + 6, 16)):
                p.scan(r, 1, ROR)
                for s in (E_A0, E_A1, E_A2, E_A3):
                    p.send(s)
            p.halt()
            await self.run(p)
            e = self.emits
            out += [e[4 * k] | e[4 * k + 1] << 8 | e[4 * k + 2] << 16 | e[4 * k + 3] << 24 for k in range(len(e) // 4)]
        return out


def search_program(rows, q):
    p = Prog()
    for i, r in enumerate(rows):
        p.wb32(1, r)
        p.sta(i)
    p.wb32(0, q)
    p.scan(0, len(rows), HAM)
    p.send(E_IDX)
    p.send(E_DIST)
    p.halt()
    return p


async def check_prog(h, f, name, prog, exp, rows=None, halt=True, until_halt=600):
    await h.fresh(rows)
    await h.run(prog, until_halt=until_halt)
    f.chk(h.emits == exp, f"{name}: SEND {[hex(x) for x in h.emits]} expected {[hex(x) for x in exp]}")
    if halt is not None:
        f.chk((h.pins()["halt"] == 1) == halt, f"{name}: HALT {'not ' if halt else ''}asserted unexpectedly")


def rows_with(**kw):
    rows = list(DEF_ROWS)
    for k, v in kw.items():
        rows[int(k[1:])] = v
    return rows


def unhex(s, w):
    return [int(s[i:i + w], 16) for i in range(0, len(s), w)]
