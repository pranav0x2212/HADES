import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

UIO_STROBE = 1 << 3
UIO_LD = 1 << 4
UIO_EXEC = 1 << 5

E_IDX, E_DIST, E_A0, E_A1, E_A2, E_A3, E_MLO, E_MHI, E_CNT, E_FLG, E_IDX2, E_DIST2 = range(12)
HAM, HAM2, THR, EXACT, ROR, RAND, RPOP, RMAXPOP = range(8)
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

    def emit(self, src):
        self.word(0x6000 | (src << 8))

    def branch(self, cond, off):
        self.word(0x7000 | (cond << 8) | (off & 0xFF))

    def clrmask(self):
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
                    p.emit(s)
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
    p.emit(E_IDX)
    p.emit(E_DIST)
    p.halt()
    return p


async def check_prog(h, f, name, prog, exp, rows=None, halt=True, until_halt=600):
    await h.fresh(rows)
    await h.run(prog, until_halt=until_halt)
    f.chk(h.emits == exp, f"{name}: EMIT {[hex(x) for x in h.emits]} expected {[hex(x) for x in exp]}")
    if halt is not None:
        f.chk((h.pins()["halt"] == 1) == halt, f"{name}: HALT {'not ' if halt else ''}asserted unexpectedly")


GOLDEN = [
    ('Prog1', False, 144,
     '500051005200530040F06000610070F8800080008000800080008000800080008000800080008000800080008000800080008000800080008000800080008000',
     '000000000000000100000002000000030000000400000005000000060000000700000008000000090000000A0000000B0000000C0000000D0000000E0000000F',
     'E13B032E0000000000000000000000000000000000000000112A32B5000000000000000000000000000000000000000079080F080000000000000000000000000000000000000000B1F7ED4C00000000000000000000000000000000000000002E5D3A070000000000000000000000000000000000000000F97F21EE0000000000000000000000000000000000000000',
     '010E010C090901130E0D0913',
     ''),
    ('Prog2', False, 150,
     '500051005200530040F366006700680070F780008000800080008000800080008000800080008000800080008000800080008000800080008000800080008000',
     'DEAD0000DEAD0001DEAD0002DEAD0003DEAD0004DEAD0005DEAD0006DEAD0007DEAD0008DEAD0009DEAD000ADEAD000BDEAD000CDEAD000DDEAD000EDEAD000F',
     '232D178A000000000000000000000000000000000000000000209AF6B5000000000000000000000000000000000000000000887F66E8000000000000000000000000000000000000000000092402AA00000000000000000000000000000000000000000049F2C1550000000000000000000000000000000000000000001B27FE53000000000000000000000000000000000000000000',
     '000000000000000000000000000000000000',
     ''),
    ('Prog3', True, 28,
     '5000510052005300540040F260006100660067006800800080008000800080008000800080008000800080008000800080008000800080008000800080008000',
     '000000000000000100000002000000030000000400000005000000060000000700000008000000090000000A0000000B0000000C0000000D0000000E0000000F',
     '266E490DB10000000000000000000000000000000000000000000000',
     '060CFFFF10',
     ''),
    ('Prog4', False, 88,
     '54005000510052005300580059005A005B0040F268006600670070F3800080008000800080008000800080008000800080008000800080008000800080008000',
     '000000000101010102020202030303030404040405050505060606060707070708080808090909090A0A0A0A0B0B0B0B0C0C0C0C0D0D0D0D0E0E0E0E0F0F0F0F',
     '00EFF317F157E1E0970000000000000000000000000000000000000000008C3F5FD5DF3D34F8000000000000000000000000000000000000000000C08262B03750894F000000000000000000000000000000000000000000',
     '000000000000010100',
     ''),
    ('Prog5', True, 46,
     '5000510052005300540040F27204100040F160006A00690080008000800080008000800080008000800080008000800080008000800080008000800080008000',
     '000000000000000100000002000000030000000400000005000000060000000700000008000000090000000A0000000B0000000C0000000D0000000E0000000F',
     'A5E42428CA00000000000000000000000000000000000000000000000000000000000000000000000000000000',
     '050103',
     ''),
    ('Prog6', True, 45,
     '500051005200530040F0610073018000540040F26800660067008000800080008000800080008000800080008000800080008000800080008000800080008000',
     '000000000000000100000002000000030000000400000005000000060000000700000008000000090000000A0000000B0000000C0000000D0000000E0000000F',
     'B869D7590000000000000000000000000000000000000068000000000000000000000000000000000000000000',
     '1110FFFF',
     ''),
    ('Prog7', True, 82,
     '40F440F540F66200630064006500300040F462006300100062006300640065008000800080008000800080008000800080008000800080008000800080008000',
     'FF00FF00EE11EE11DD22DD22CC33CC33BB44BB44AA55AA559966996688778877778877886699669955AA55AA44BB44BB33CC33CC22DD22DD11EE11EE00FF00FF',
     '000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000',
     '00010000FFFF00010000',
     ''),
    ('Full32', True, 32,
     '900060006100680069006A006B0060006100680069006A006B0060006100680069006A006B0060006100680069006A006B0060006100680069006A006B008000',
     '00000000111111112222222233333333444444445555555566666666777777778888888899999999AAAAAAAABBBBBBBBCCCCCCCCDDDDDDDDEEEEEEEEFFFFFFFF',
     '0000000000000000000000000000000000000000000000000000000000000000',
     '003F0000003F003F0000003F003F0000003F003F0000003F003F0000003F',
     ''),
    ('Odd9', True, 25,
     '500051005200530040F160006A006B00800080008000800080008000800080008000800080008000800080008000800080008000800080008000800080008000',
     '9E3779B93C6EF372DAA66D2B78DDE6E41715609DB54CDA565384540FF1BBCDC88FF347812E2AC13ACC623AF36A99B4AC08D12E65A708A81E454021D7E3779B90',
     '1AB2E177000000000000000000000000000000000000000000',
     '0D0F0D',
     ''),
    ('RowsRW0', True, 34,
     '54005500560057003000400462006300640065005400550056005700310041046200630064006500540055005600570032004204620063006400650080008000',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5',
     'FB54C29D000000000000000125F5CA0000000000000098DBF55F0000000000000000',
     'FB54C29D0125F5CA98DBF55F',
     '9DC254FBCAF525015FF5DB98A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5'),
    ('RowsRW1', True, 34,
     '54005500560057003300430462006300640065005400550056005700340044046200630064006500540055005600570035004504620063006400650080008000',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5',
     'CDF4509000000000000000BDB1695600000000000000EAF20EEF0000000000000000',
     'CDF45090BDB16956EAF20EEF',
     'A5A5A5A5A5A5A5A5A5A5A5A59050F4CD5669B1BDEF0EF2EAA5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5'),
    ('RowsRW2', True, 34,
     '54005500560057003600460462006300640065005400550056005700370047046200630064006500540055005600570038004804620063006400650080008000',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5',
     '350DBBF3000000000000002147A9B2000000000000009498A9960000000000000000',
     '350DBBF32147A9B29498A996',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5F3BB0D35B2A9472196A99894A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5'),
    ('RowsRW3', True, 34,
     '540055005600570039004904620063006400650054005500560057003A004A04620063006400650054005500560057003B004B04620063006400650080008000',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5',
     '638E256800000000000000ADABA4EA00000000000000882B3D7D0000000000000000',
     '638E2568ADABA4EA882B3D7D',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A568258E63EAA4ABAD7D3D2B88A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5'),
    ('RowsRW4', True, 34,
     '54005500560057003C004C04620063006400650054005500560057003D004D04620063006400650054005500560057003E004E04620063006400650080008000',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5',
     '83BE460E00000000000000CA13166A000000000000004FA0B5DE0000000000000000',
     '83BE460ECA13166A4FA0B5DE',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A50E46BE836A1613CADEB5A04FA5A5A5A5'),
    ('RowsRW5', True, 12,
     '54005500560057003F004F0462006300640065008000800080008000800080008000800080008000800080008000800080008000800080008000800080008000',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5',
     '239C85F80000000000000000',
     '239C85F8',
     'A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5A5F8859C23'),
]


@cocotb.test()
async def test_reset_idle(dut):
    h = Host(dut)
    await h.reset()
    for _ in range(30):
        p = h.pins()
        assert p == {"ready": 0, "busy": 0, "halt": 0}, f"core must be idle after reset/initialisation, got {p}"
        await ClockCycles(dut.clk, 1)
    assert not h.emits


@cocotb.test()
async def test_no_run_before_execute_then_halt(dut):
    h = Host(dut)
    await h.reset()
    p = Prog()
    p.emit(E_DIST)
    p.halt()
    await h.load(p.words)
    await ClockCycles(dut.clk, 40)
    assert not h.emits and h.pins()["halt"] == 0, "a loaded program must not run before EXECUTE"
    await h.execute_request()
    await h.run_schedule(p.sched)
    assert h.emits == [0x3F], f"expected one EMIT of min_dist reset value, got {h.emits}"
    assert h.pins()["halt"] == 1


@cocotb.test()
async def test_empty_program_halts(dut):
    h = Host(dut)
    await h.reset()
    await h.execute_request()
    await ClockCycles(dut.clk, 6)
    assert h.pins()["halt"] == 1 and not h.emits, "unwritten program slots are HALT"


@cocotb.test()
async def test_end_to_end_search_and_restart(dut):
    h = Host(dut)
    await h.reset()
    rows = [0xFFFF0000, 0x0F0F0F0F, 0xA5A5A5A5, 0x12345678]
    q = 0x0F0F0F1F
    idx, dist, _ = nearest(rows, q)
    prog = search_program(rows, q)
    await h.run(prog)
    assert h.pins()["halt"] == 1
    assert h.emits == [idx, dist], f"HAMMING result {h.emits}, expected {[idx, dist]}"
    await h.rerun(prog)
    assert h.pins()["halt"] == 1
    assert h.emits == [idx, dist, idx, dist], f"restart result {h.emits}"


@cocotb.test()
async def test_random_search(dut):
    h = Host(dut)
    rng = random.Random(12345)
    for _ in range(3):
        await h.reset()
        rows = [rng.getrandbits(32) for _ in range(4)]
        q = rng.getrandbits(32)
        idx, dist, _ = nearest(rows, q)
        await h.run(search_program(rows, q))
        assert h.emits == [idx, dist], f"rows={[hex(r) for r in rows]} q={q:#x}: got {h.emits}, expected {[idx, dist]}"


@cocotb.test()
async def test_threshold_scan(dut):
    h = Host(dut)
    await h.reset()
    rows = [0x00000000, 0x000000FF, 0x0000FFFF, 0xFFFFFFFF]
    q = 0x00000003
    thr = 8
    _, _, d = nearest(rows, q)
    match = sum(1 << i for i, x in enumerate(d) if x <= thr)
    count = bin(match).count("1")
    p = Prog()
    for i, r in enumerate(rows):
        p.wb32(1, r)
        p.sta(i)
    p.wb32(0, q)
    p.wb(1, 0, thr)
    p.scan(0, len(rows), THR)
    for src in (E_MLO, E_CNT, E_FLG):
        p.emit(src)
    p.halt()
    await h.run(p)
    flags = (1 << 1 if match else 0) | 1
    assert h.emits == [match & 0xFF, count, flags], f"THRESHOLD result {h.emits}, expected {[match & 0xFF, count, flags]}"


@cocotb.test()
async def test_execute_ignored_with_pending_byte(dut):
    h = Host(dut)
    await h.reset()
    p = Prog()
    p.emit(E_DIST)
    p.emit(E_DIST)
    p.halt()
    await h.load_byte(p.words[0] >> 8)
    await h.load_byte(p.words[0] & 0xFF)
    await h.load_byte(p.words[1] >> 8)
    await h.execute_request()
    await ClockCycles(dut.clk, 10)
    assert h.pins() == {"ready": 0, "busy": 0, "halt": 0} and not h.emits, "EXECUTE with a pending loader byte must be ignored"
    await h.load_byte(p.words[1] & 0xFF)
    await h.load_byte(p.words[2] >> 8)
    await h.load_byte(p.words[2] & 0xFF)
    await h.execute_request()
    await h.run_schedule(p.sched)
    assert h.emits == [0x3F, 0x3F] and h.pins()["halt"] == 1


@cocotb.test()
async def test_reset_and_initialisation(dut):
    h = Host(dut)
    f = Fails()
    await h.fresh()
    p = Prog()
    p.emit(E_DIST)
    p.halt()
    await h.load(p.words)
    await h.reset()
    await h.execute_request()
    await h.clocks(6)
    f.chk(h.pins()["halt"] == 1 and not h.emits, "reset must erase the program")
    f.chk(await h.read_rows() == DEF_ROWS, "data rows must survive reset")

    await h.fresh()
    dut.rst_n.value = 0
    await h.clocks(2)
    await h.load([0x6100])
    h.set_uio(UIO_EXEC, 1)
    await h.clocks(2)
    h.set_uio(UIO_EXEC, 0)
    await h.load([0x6100])
    dut.rst_n.value = 1
    await h.clocks(INIT_CLOCKS)
    f.chk(h.idle() and not h.emits, "loader/EXECUTE during reset must do nothing")
    await h.execute_request()
    await h.clocks(6)
    f.chk(h.pins()["halt"] == 1 and not h.emits, "instruction sent during reset must not be stored")

    h.emits.clear()
    dut.rst_n.value = 0
    await h.clocks(4)
    dut.rst_n.value = 1
    await h.clocks(5)
    await h.execute_request()
    await h.clocks(20)
    f.chk(h.idle(), "EXECUTE inside the initialisation sweep must be ignored")

    await h.reset()
    dut.rst_n.value = 0
    h.set_uio(UIO_EXEC, 1)
    await h.clocks(4)
    dut.rst_n.value = 1
    await h.clocks(INIT_CLOCKS + 8)
    f.chk(h.idle(), "EXECUTE held high across reset release must not start the core")
    h.set_uio(UIO_EXEC, 0)
    await h.clocks(2)
    p = Prog()
    p.emit(E_DIST)
    p.halt()
    await h.run(p)
    f.chk(h.emits == [0x3F] and h.pins()["halt"] == 1, "a fresh EXECUTE edge after the hold must start the program")
    f.done()


@cocotb.test()
async def test_loader(dut):
    h = Host(dut)
    f = Fails()

    p = Prog()
    exp = []
    for j in range(15):
        b = (0x10 + 7 * j) & 0xFF
        p.wb(1, j % 4, b)
        p.emit(E_A0 + j % 4)
        exp.append(b)
    p.emit(E_DIST)
    p.halt()
    assert len(p.words) == 32
    await check_prog(h, f, "32 slots, two per word", p, exp + [0x3F])

    p = Prog()
    for s in (E_DIST, E_IDX, E_DIST2, E_FLG, E_DIST):
        p.emit(s)
    await check_prog(h, f, "odd instruction count (lone even slot)", p, [0x3F, 0, 0x3F, 0, 0x3F])

    await h.fresh()
    words = [0x6100] * 31 + [0x8000]
    await h.load(words + [0x6000, 0x6000])
    await h.execute_request()
    await h.run_schedule([], until_halt=100)
    f.chk(h.emits == [0, 0] + [0x3F] * 29, f"slot counter wrap: EMIT {h.emits}")

    await h.fresh()
    for b, hold in ((0x61, 10), (0x00, 10), (0x60, 3), (0x00, 3)):
        await h.load_byte(b, hold)
        await h.clocks(2)
    await h.execute_request()
    await h.run_schedule([], until_halt=50)
    f.chk(h.emits == [0x3F, 0] and h.pins()["halt"] == 1, f"LD_STROBE must be edge sensitive: EMIT {h.emits}")

    await h.fresh()
    dut.ui_in.value = 0x61
    h.set_uio(UIO_LD | UIO_EXEC, 1)
    await h.clocks(1)
    h.set_uio(UIO_LD | UIO_EXEC, 0)
    await h.clocks(12)
    f.chk(h.idle(), "EXECUTE in the same clock as a loader strobe must be ignored")
    f.done()


@cocotb.test()
async def test_execute_and_restart(dut):
    h = Host(dut)
    f = Fails()

    p = Prog()
    p.loadq(5)
    p.scan(0, 16, HAM)
    p.emit(E_IDX)
    p.emit(E_DIST)
    p.halt()
    await h.fresh()
    await h.load(p.words)
    dut.ui_in.value = 5
    h.set_uio(UIO_STROBE, 1)
    await h.clocks(40)
    f.chk(h.idle() and not h.emits, "no execution before EXECUTE")
    h.set_uio(UIO_STROBE, 0)
    await h.execute_request()
    await h.run_schedule(p.sched)
    f.chk(h.emits == [5, 0], f"run after idle strobe: EMIT {h.emits}")

    await h.fresh()
    p = Prog()
    p.halt()
    await h.run(p)
    f.chk(h.halt_cycle == len(p.sched) + HALT_LATENCY, f"EXECUTE latency: HALT seen at cycle {h.halt_cycle}")

    p = Prog()
    p.emit(E_IDX)
    p.emit(E_DIST)
    p.loadq(5)
    p.scan(0, 16, HAM)
    p.halt()
    await h.fresh()
    await h.run(p, until_halt=300)
    f.chk(h.emits == [0, 0x3F] and h.pins()["halt"] == 1, f"first run: EMIT {h.emits}")
    await h.rerun(p, until_halt=300)
    f.chk(h.emits == [0, 0x3F, 5, 0], f"restart must keep the previous run's results: EMIT {h.emits}")

    p = Prog()
    p.emit(E_DIST)
    p.wb(0, 0, 5)
    p.emit(E_IDX)
    p.halt()
    await h.fresh()
    await h.load(p.words)
    await h.execute_request()
    await h.run_schedule([(0, 0)] * 8, tail=0)
    pins = h.pins()
    f.chk(pins["busy"] == 1 and pins["halt"] == 0 and h.emits == [0x3F], "stalled on WAITBYTE while running")
    await h.execute_request()
    await h.run_schedule([(0, 0)] * 6, tail=0)
    f.chk(h.emits == [0x3F, 0x3F] and h.pins()["halt"] == 0, f"EXECUTE while running must restart at slot 0: EMIT {h.emits}")
    await h.run_schedule([(5, 1), (0, 1), (0, 1)])
    f.chk(h.emits == [0x3F, 0x3F, 0] and h.pins()["halt"] == 1, f"restarted run completes: EMIT {h.emits}")

    p = Prog()
    p.emit(E_DIST)
    p.halt()
    await h.fresh()
    await h.load(p.words)
    await h.reset()
    await h.execute_request()
    await h.clocks(6)
    f.chk(h.pins()["halt"] == 1 and not h.emits, "reset erases the program")
    f.done()


@cocotb.test()
async def test_scan_operations(dut):
    h = Host(dut)
    f = Fails()

    def q5():
        p = Prog()
        p.loadq(5)
        return p

    p = q5(); p.scan(0, 16, HAM); p.emit(E_IDX); p.emit(E_DIST); p.halt()
    await check_prog(h, f, "HAMMING", p, [5, 0])
    p = q5(); p.scan(0, 16, HAM2)
    for s in (E_IDX, E_DIST, E_IDX2, E_DIST2):
        p.emit(s)
    p.halt()
    await check_prog(h, f, "HAMMING2", p, [5, 0, 1, 4])
    p = q5(); p.wb(1, 0, 4); p.scan(0, 16, THR)
    for s in (E_MLO, E_MHI, E_CNT, E_FLG):
        p.emit(s)
    p.halt()
    await check_prog(h, f, "THRESHOLD", p, [0xB2, 0x20, 5, 3])
    p = q5(); p.scan(0, 16, EXACT); p.emit(E_MLO); p.emit(E_MHI); p.emit(E_CNT); p.halt()
    await check_prog(h, f, "EXACT", p, [0x20, 0, 1])
    p = Prog(); p.scan(0, 6, ROR); p.emit(E_A0); p.halt()
    await check_prog(h, f, "REDUCE_OR rows 0-5", p, [0x07])
    p = Prog(); p.scan(4, 2, RAND); p.emit(E_A0); p.halt()
    await check_prog(h, f, "REDUCE_AND rows 4-5", p, [0x04])
    p = Prog(); p.scan(0, 6, RPOP); p.emit(E_A0); p.halt()
    await check_prog(h, f, "REDUCE_POP rows 0-5", p, [0x1C])
    p = Prog(); p.scan(0, 6, RMAXPOP); p.emit(E_IDX); p.emit(E_DIST); p.halt()
    await check_prog(h, f, "REDUCE_MAXPOP rows 0-5", p, [3, 8])
    p = q5(); p.scan(6, 10, HAM); p.scan(0, 6, HAM, acc=1); p.emit(E_IDX); p.emit(E_DIST); p.halt()
    await check_prog(h, f, "HAMMING ACC chained scan", p, [5, 0])
    p = Prog(); p.scan(12, 8, RPOP); p.emit(E_A0); p.halt()
    await check_prog(h, f, "range clamp at row 15", p, [0x30])
    p = q5(); p.loada(4, 0xB1, 0xB2, 0xB3); p.scan(0, 16, THR)
    for s in range(13):
        p.emit(s)
    p.halt()
    await check_prog(h, f, "all EMIT sources", p,
                     [5, 0, 4, 0xB1, 0xB2, 0xB3, 0xB2, 0x20, 5, 3, 0, 0x3F, 0xFF])

    cycles = []
    for n in (1, 16):
        p = Prog(); p.scan(0, n, ROR); p.halt()
        await h.fresh()
        await h.run(p, until_halt=100)
        cycles.append(h.halt_cycle)
    f.chk(cycles[1] - cycles[0] == 15, f"a 16-row SCAN takes 15 more cycles than a 1-row SCAN: {cycles}")
    f.done()


def rows_with(**kw):
    rows = list(DEF_ROWS)
    for k, v in kw.items():
        rows[int(k[1:])] = v
    return rows


@cocotb.test()
async def test_waitbyte_registers_and_sta(dut):
    h = Host(dut)
    f = Fails()

    q = 0x44332211
    rows = rows_with(r0=q, r1=q ^ 0x1, r2=q ^ 0x100, r3=q ^ 0x10000, r4=q ^ 0x1000000)
    p = Prog()
    for pos in range(4):
        p.wb(0, pos, (q >> (8 * pos)) & 0xFF)
    p.scan(0, 5, EXACT); p.emit(E_MLO); p.emit(E_CNT); p.halt()
    await check_prog(h, f, "WAITBYTE Q lanes", p, [1, 1], rows=rows)

    p = Prog(); p.loada(0xA1, 0xA2, 0xA3, 0xA4)
    for s in (E_A0, E_A1, E_A2, E_A3):
        p.emit(s)
    p.halt()
    await check_prog(h, f, "WAITBYTE A lanes", p, [0xA1, 0xA2, 0xA3, 0xA4])

    ones = rows_with(r15=ALL_ONES)

    def read_mask(p):
        p.scan(15, 1, ROR)
        for s in (E_A0, E_A1, E_A2, E_A3):
            p.emit(s)
        p.halt()

    p = Prog(); p.wb(2, 1, 0x12); p.wb(2, 3, 0x34); read_mask(p)
    await check_prog(h, f, "WAITBYTE MASK lanes", p, [0xFF, 0x12, 0xFF, 0x34], rows=ones)
    p = Prog(); p.wb(2, 0, 0); p.wb(2, 2, 0x55); p.clrmask(); read_mask(p)
    await check_prog(h, f, "CLRMASK", p, [0xFF] * 4, rows=ones)
    p = Prog(); p.loadq(5); p.wb(2, 0, 0); p.scan(0, 6, HAM); p.emit(E_IDX); p.emit(E_DIST); read_mask(p)
    await check_prog(h, f, "MASK byte 0 cleared, HAMMING", p, [5, 0, 0x00, 0xFF, 0xFF, 0xFF], rows=ones)

    rows = rows_with(r14=0xAB)
    p = Prog(); p.wb(0, 0, 0xAB)
    for pos in (1, 2, 3):
        p.wb(0, pos, 0)
    p.scan(14, 1, EXACT); p.emit(E_CNT); p.halt()
    sched = [(0, 0)] * 20 + p.sched
    await h.fresh(rows)
    await h.load(p.words)
    await h.execute_request()
    await h.run_schedule(sched[:20], tail=0)
    f.chk(h.pins()["halt"] == 0 and h.pins()["busy"] == 1 and not h.emits, "WAITBYTE stalls (BUSY, no HALT) until STROBE")
    await h.run_schedule(sched[20:])
    f.chk(h.emits == [1] and h.pins()["halt"] == 1, f"WAITBYTE after a stall: EMIT {h.emits}")

    rows = rows_with(r14=0xC7)
    p = Prog(); p.wb(0, 0, 0xC7)
    for pos in (1, 2, 3):
        p.wb(0, pos, 0)
    p.scan(14, 1, EXACT); p.emit(E_CNT); p.halt()
    await h.fresh(rows)
    await h.run(p)
    f.chk(h.emits == [1] and h.halt_cycle == len(p.sched) + HALT_LATENCY,
          f"WAITBYTE with STROBE already high consumes in one cycle: EMIT {h.emits}, HALT at {h.halt_cycle} of {len(p.sched)}")

    p = Prog(gap=3)
    p.loadq(1); p.scan(6, 10, HAM); p.loadq(5); p.scan(0, 6, HAM, acc=1); p.emit(E_IDX); p.emit(E_DIST); p.halt()
    await check_prog(h, f, "Q reloaded between chained scans (STROBE gaps)", p, [5, 0])

    p = Prog(); p.loada(0x10, 0x20, 0x30, 0x40); p.sta(0); p.loada(0xAA, 0xBB, 0xCC, 0xDD); p.sta(15)
    p.scan(15, 1, ROR); p.emit(E_A0); p.emit(E_A3); p.halt()
    await check_prog(h, f, "STA rows 0 and 15", p, [0xAA, 0xDD])
    exp = list(DEF_ROWS)
    exp[0], exp[15] = 0x40302010, 0xDDCCBBAA
    f.chk(await h.read_rows() == exp, "STA writes exactly rows 0 and 15")
    h.rows_state = None
    f.done()


@cocotb.test()
async def test_branches(dut):
    h = Host(dut)
    f = Fails()

    def q5():
        p = Prog()
        p.loadq(5)
        return p

    p = Prog(); p.branch(C_ALWAYS, 1); p.emit(E_IDX); p.emit(E_DIST); p.halt()
    await check_prog(h, f, "ALWAYS forward", p, [0x3F])
    p = q5(); p.scan(5, 1, EXACT); p.branch(C_MATNZ, 1); p.branch(C_ALWAYS, 0xFD); p.emit(E_IDX); p.halt()
    await check_prog(h, f, "MATCH_NZ", p, [0])
    p = q5(); p.wb(1, 0, 4); p.scan(0, 16, THR); p.branch(C_THR, 1); p.emit(E_DIST2); p.emit(E_IDX); p.halt()
    await check_prog(h, f, "THRESHOLD_HIT", p, [5])
    p = Prog(); p.branch(C_NTHR, 1); p.emit(E_IDX); p.emit(E_DIST); p.halt()
    await check_prog(h, f, "NOT_THRESHOLD_HIT", p, [0x3F])
    p = q5(); p.branch(C_MINV, 2); p.scan(5, 1, HAM); p.branch(C_MINV, 1); p.emit(E_DIST2); p.emit(E_IDX); p.halt()
    await check_prog(h, f, "MIN_VALID", p, [5])
    p = q5(); p.scan(0, 1, EXACT); p.branch(C_CNTNZ, 2); p.scan(5, 1, EXACT, acc=1); p.branch(C_CNTNZ, 1)
    p.emit(E_DIST); p.emit(E_CNT); p.halt()
    await check_prog(h, f, "COUNT_NZ", p, [1])
    p = Prog(); p.loada(0, 0, 0, 0); p.branch(C_AZ, 1); p.emit(E_IDX); p.branch(C_ANZ, 1); p.emit(E_DIST); p.halt()
    await check_prog(h, f, "A_ZERO / A_NONZERO with A=0", p, [0x3F])
    p = Prog(); p.loada(0xEF, 0xBE, 0xAD, 0xDE); p.branch(C_ANZ, 1); p.emit(E_IDX); p.emit(E_DIST)
    for s in (E_A0, E_A1, E_A2, E_A3):
        p.emit(s)
    p.halt()
    await check_prog(h, f, "A_NONZERO taken", p, [0x3F, 0xEF, 0xBE, 0xAD, 0xDE])
    p = q5(); p.scan(5, 1, HAM); p.branch(C_MINV, 1); p.branch(C_ALWAYS, 0xFD); p.emit(E_DIST); p.halt()
    await check_prog(h, f, "backward offset not taken", p, [0])

    p = Prog()
    p.loadq(1); p.scan(5, 1, EXACT); p.emit(E_CNT); p.branch(C_CNTNZ, 1); p.branch(C_ALWAYS, 0xF8); p.emit(E_DIST); p.halt()
    p.sched = ([(1, 1)] * 4 + [(0, 1)] * 5 + [(5, 1)] * 4 + [(0, 1)] * 6)
    await check_prog(h, f, "WAITBYTE loop with backward BRANCH", p, [0, 1, 0x3F])
    f.done()


def unhex(s, w):
    return [int(s[i:i + w], 16) for i in range(0, len(s), w)]


async def run_golden(h, f, g):
    name, halts, cycles, prog, rows, sched, exp, exp_rows = g
    await h.fresh(unhex(rows, 8))
    await h.load(unhex(prog, 4))
    await h.execute_request()
    await h.run_schedule([(b, 1) for b in unhex(sched, 2)])
    f.chk(h.emits == unhex(exp, 2), f"{name}: EMIT {h.emits} expected {unhex(exp, 2)}")
    if halts:
        f.chk(h.halt_cycle == cycles + HALT_LATENCY, f"{name}: HALT at cycle {h.halt_cycle}, model {cycles}")
    else:
        f.chk(h.pins()["halt"] == 0 and h.pins()["busy"] == 1, f"{name}: expected to end stalled on WAITBYTE")
    if exp_rows:
        f.chk(await h.read_rows() == unhex(exp_rows, 8), f"{name}: final data rows")
    h.rows_state = None


@cocotb.test()
async def test_golden_workloads(dut):
    h = Host(dut)
    f = Fails()
    for g in GOLDEN:
        if g[0] != "Prog4":
            await run_golden(h, f, g)
    f.done()


@cocotb.test()
async def test_golden_prog4(dut):
    h = Host(dut)
    f = Fails()
    await run_golden(h, f, [g for g in GOLDEN if g[0] == "Prog4"][0])
    f.done()


@cocotb.test()
async def test_ldq(dut):
    h = Host(dut)
    p = Prog(); p.ldq(5); p.scan(5, 1, EXACT); p.emit(E_CNT); p.halt()
    await h.fresh()
    await h.run(p, until_halt=60)
    assert h.emits == [1], f"LDQ 5 should load data row 5, got {h.emits}"


@cocotb.test()
async def test_lda(dut):
    h = Host(dut)
    p = Prog(); p.lda(6); p.emit(E_A0); p.halt()
    await h.fresh()
    await h.run(p, until_halt=60)
    assert h.emits == [6], f"LDA 6 should load data row 6, got {h.emits}"


@cocotb.test()
async def test_ldm(dut):
    h = Host(dut)
    p = Prog(); p.ldm(7); p.scan(15, 1, ROR); p.emit(E_A0); p.halt()
    await h.fresh(rows_with(r15=ALL_ONES))
    await h.run(p, until_halt=60)
    assert h.emits == [7], f"LDM 7 should load data row 7, got {h.emits}"


@cocotb.test()
async def test_ldx_takes_two_cycles(dut):
    h = Host(dut)
    p = Prog(); p.ldq(5); p.lda(6); p.ldm(7); p.halt()
    await h.fresh()
    await h.run(p, until_halt=60)
    assert h.halt_cycle == 3 * 2 + 1 + HALT_LATENCY, f"3 LDx + HALT: halt at cycle {h.halt_cycle}"


@cocotb.test()
async def test_ldx_hazards(dut):
    h = Host(dut)
    f = Fails()
    rows = rows_with(r2=0x0000FFFF, r9=0, r15=0x0F0F0F0F)
    # STA then LDA of the same row, back to back; the next instruction sees the new A
    p = Prog(); p.wb32(1, 0x44332211); p.sta(3); p.lda(0); p.lda(3); p.emit(E_A0); p.emit(E_A3); p.halt()
    await check_prog(h, f, "STA then LDA same row", p, [0x11, 0x44], rows=rows)
    # LDA then BRANCH on A, LDM then SCAN using the new MASK, LDQ then SCAN using the new Q
    p = Prog(); p.lda(9); p.branch(C_AZ, 1); p.emit(E_IDX); p.lda(2); p.branch(C_ANZ, 1); p.emit(E_IDX)
    p.ldm(2); p.ldq(15); p.scan(0, 16, HAM); p.emit(E_DIST); p.halt()
    await check_prog(h, f, "LDA/BRANCH and LDM/LDQ then SCAN", p, [0], rows=rows)
    # LDQ row 15 then EXACT scan matches only row 15
    p = Prog(); p.ldq(15); p.scan(0, 16, EXACT); p.emit(E_CNT); p.emit(E_MHI); p.halt()
    await check_prog(h, f, "LDQ row 15 then EXACT", p, [1, 0x80], rows=rows)
    # LDx in a WAITBYTE stream: the extra cycle must not misalign a following WAITBYTE
    p = Prog(); p.ldq(5); p.wb(0, 0, 0x06); p.scan(0, 16, EXACT); p.emit(E_CNT); p.emit(E_MLO); p.halt()
    await check_prog(h, f, "LDQ then WAITBYTE patches Q byte 0", p, [0, 0x00], rows=rows)
    f.done()
    h.rows_state = None


async def maxpop32(dut, rows):
    h = Host(dut)
    p = Prog(); p.scan(0, 16, RMAXPOP); p.emit(E_IDX); p.emit(E_DIST); p.halt()
    await h.fresh(rows)
    await h.run(p, until_halt=120)
    h.rows_state = None
    return h


@cocotb.test()
async def test_maxpop_popcount_32(dut):
    h = await maxpop32(dut, [1] * 3 + [ALL_ONES] + [1] * 12)
    assert h.emits == [3, 32] and h.pins()["halt"] == 1, f"got {h.emits}"


@cocotb.test()
async def test_maxpop_32_not_overridden_by_later_rows(dut):
    h = await maxpop32(dut, [ALL_ONES] + [1] * 15)
    assert h.emits == [0, 32] and h.pins()["halt"] == 1, f"got {h.emits}"


@cocotb.test()
async def test_hamming_selects_distance_32(dut):
    h = Host(dut)
    p = Prog(); p.loadq(0); p.scan(0, 16, HAM); p.emit(E_IDX); p.emit(E_DIST); p.halt()
    await h.fresh([ALL_ONES] * 16)
    await h.run(p, until_halt=200)
    h.rows_state = None
    assert h.emits == [0, 32] and h.pins()["halt"] == 1, f"got {h.emits}"
