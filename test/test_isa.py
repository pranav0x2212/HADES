import random

import cocotb
from cocotb.triggers import ClockCycles

from hades_tb import *
from hades_ref import *


@cocotb.test()
async def test_recv_registers_and_sta(dut):
    h = Host(dut)
    f = Fails()

    q = 0x44332211
    rows = rows_with(r0=q, r1=q ^ 0x1, r2=q ^ 0x100, r3=q ^ 0x10000, r4=q ^ 0x1000000)
    p = Prog()
    for pos in range(4):
        p.wb(0, pos, (q >> (8 * pos)) & 0xFF)
    p.scan(0, 5, EQUAL); p.send(E_MLO); p.send(E_CNT); p.halt()
    await check_prog(h, f, "RECV Q lanes", p, [1, 1], rows=rows)

    p = Prog(); p.loada(0xA1, 0xA2, 0xA3, 0xA4)
    for s in (E_A0, E_A1, E_A2, E_A3):
        p.send(s)
    p.halt()
    await check_prog(h, f, "RECV A lanes", p, [0xA1, 0xA2, 0xA3, 0xA4])

    ones = rows_with(r15=ALL_ONES)

    def read_mask(p):
        p.scan(15, 1, ROR)
        for s in (E_A0, E_A1, E_A2, E_A3):
            p.send(s)
        p.halt()

    p = Prog(); p.wb(2, 1, 0x12); p.wb(2, 3, 0x34); read_mask(p)
    await check_prog(h, f, "RECV MASK lanes", p, [0xFF, 0x12, 0xFF, 0x34], rows=ones)
    p = Prog(); p.wb(2, 0, 0); p.wb(2, 2, 0x55); p.unmask(); read_mask(p)
    await check_prog(h, f, "UNMASK", p, [0xFF] * 4, rows=ones)
    p = Prog(); p.loadq(5); p.wb(2, 0, 0); p.scan(0, 6, HAM); p.send(E_IDX); p.send(E_DIST); read_mask(p)
    await check_prog(h, f, "MASK byte 0 cleared, NEAREST", p, [5, 0, 0x00, 0xFF, 0xFF, 0xFF], rows=ones)

    rows = rows_with(r14=0xAB)
    p = Prog(); p.wb(0, 0, 0xAB)
    for pos in (1, 2, 3):
        p.wb(0, pos, 0)
    p.scan(14, 1, EQUAL); p.send(E_CNT); p.halt()
    sched = [(0, 0)] * 20 + p.sched
    await h.fresh(rows)
    await h.load(p.words)
    await h.execute_request()
    await h.run_schedule(sched[:20], tail=0)
    f.chk(h.pins()["halt"] == 0 and h.pins()["busy"] == 1 and not h.emits, "RECV stalls (BUSY, no HALT) until STROBE")
    await h.run_schedule(sched[20:])
    f.chk(h.emits == [1] and h.pins()["halt"] == 1, f"RECV after a stall: SEND {h.emits}")

    rows = rows_with(r14=0xC7)
    p = Prog(); p.wb(0, 0, 0xC7)
    for pos in (1, 2, 3):
        p.wb(0, pos, 0)
    p.scan(14, 1, EQUAL); p.send(E_CNT); p.halt()
    await h.fresh(rows)
    await h.run(p)
    f.chk(h.emits == [1] and h.halt_cycle == len(p.sched) + HALT_LATENCY,
          f"RECV with STROBE already high consumes in one cycle: SEND {h.emits}, HALT at {h.halt_cycle} of {len(p.sched)}")

    p = Prog(gap=3)
    p.loadq(1); p.scan(6, 10, HAM); p.loadq(5); p.scan(0, 6, HAM, acc=1); p.send(E_IDX); p.send(E_DIST); p.halt()
    await check_prog(h, f, "Q reloaded between chained scans (STROBE gaps)", p, [5, 0])

    p = Prog(); p.loada(0x10, 0x20, 0x30, 0x40); p.sta(0); p.loada(0xAA, 0xBB, 0xCC, 0xDD); p.sta(15)
    p.scan(15, 1, ROR); p.send(E_A0); p.send(E_A3); p.halt()
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

    p = Prog(); p.branch(C_ALWAYS, 1); p.send(E_IDX); p.send(E_DIST); p.halt()
    await check_prog(h, f, "ALWAYS forward", p, [0x3F])
    p = q5(); p.scan(5, 1, EQUAL); p.branch(C_MATNZ, 1); p.branch(C_ALWAYS, 0xFD); p.send(E_IDX); p.halt()
    await check_prog(h, f, "MATCH_NZ", p, [0])
    p = q5(); p.wb(1, 0, 4); p.scan(0, 16, THR); p.branch(C_THR, 1); p.send(E_DIST2); p.send(E_IDX); p.halt()
    await check_prog(h, f, "THRESHOLD_HIT", p, [5])
    p = Prog(); p.branch(C_NTHR, 1); p.send(E_IDX); p.send(E_DIST); p.halt()
    await check_prog(h, f, "NOT_THRESHOLD_HIT", p, [0x3F])
    p = q5(); p.branch(C_MINV, 2); p.scan(5, 1, HAM); p.branch(C_MINV, 1); p.send(E_DIST2); p.send(E_IDX); p.halt()
    await check_prog(h, f, "MIN_VALID", p, [5])
    p = q5(); p.scan(0, 1, EQUAL); p.branch(C_CNTNZ, 2); p.scan(5, 1, EQUAL, acc=1); p.branch(C_CNTNZ, 1)
    p.send(E_DIST); p.send(E_CNT); p.halt()
    await check_prog(h, f, "COUNT_NZ", p, [1])
    p = Prog(); p.loada(0, 0, 0, 0); p.branch(C_AZ, 1); p.send(E_IDX); p.branch(C_ANZ, 1); p.send(E_DIST); p.halt()
    await check_prog(h, f, "A_ZERO / A_NONZERO with A=0", p, [0x3F])
    p = Prog(); p.loada(0xEF, 0xBE, 0xAD, 0xDE); p.branch(C_ANZ, 1); p.send(E_IDX); p.send(E_DIST)
    for s in (E_A0, E_A1, E_A2, E_A3):
        p.send(s)
    p.halt()
    await check_prog(h, f, "A_NONZERO taken", p, [0x3F, 0xEF, 0xBE, 0xAD, 0xDE])
    p = q5(); p.scan(5, 1, HAM); p.branch(C_MINV, 1); p.branch(C_ALWAYS, 0xFD); p.send(E_DIST); p.halt()
    await check_prog(h, f, "backward offset not taken", p, [0])

    p = Prog()
    p.loadq(1); p.scan(5, 1, EQUAL); p.send(E_CNT); p.branch(C_CNTNZ, 1); p.branch(C_ALWAYS, 0xF8); p.send(E_DIST); p.halt()
    p.sched = ([(1, 1)] * 4 + [(0, 1)] * 5 + [(5, 1)] * 4 + [(0, 1)] * 6)
    await check_prog(h, f, "RECV loop with backward BRANCH", p, [0, 1, 0x3F])
    f.done()


@cocotb.test()
async def test_ldq(dut):
    h = Host(dut)
    p = Prog(); p.ldq(5); p.scan(5, 1, EQUAL); p.send(E_CNT); p.halt()
    await h.fresh()
    await h.run(p, until_halt=60)
    assert h.emits == [1], f"LDQ 5 should load data row 5, got {h.emits}"


@cocotb.test()
async def test_lda(dut):
    h = Host(dut)
    p = Prog(); p.lda(6); p.send(E_A0); p.halt()
    await h.fresh()
    await h.run(p, until_halt=60)
    assert h.emits == [6], f"LDA 6 should load data row 6, got {h.emits}"


@cocotb.test()
async def test_ldm(dut):
    h = Host(dut)
    p = Prog(); p.ldm(7); p.scan(15, 1, ROR); p.send(E_A0); p.halt()
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
    p = Prog(); p.wb32(1, 0x44332211); p.sta(3); p.lda(0); p.lda(3); p.send(E_A0); p.send(E_A3); p.halt()
    await check_prog(h, f, "STA then LDA same row", p, [0x11, 0x44], rows=rows)
    p = Prog(); p.lda(9); p.branch(C_AZ, 1); p.send(E_IDX); p.lda(2); p.branch(C_ANZ, 1); p.send(E_IDX)
    p.ldm(2); p.ldq(15); p.scan(0, 16, HAM); p.send(E_DIST); p.halt()
    await check_prog(h, f, "LDA/BRANCH and LDM/LDQ then SCAN", p, [0], rows=rows)
    p = Prog(); p.ldq(15); p.scan(0, 16, EQUAL); p.send(E_CNT); p.send(E_MHI); p.halt()
    await check_prog(h, f, "LDQ row 15 then EQUAL", p, [1, 0x80], rows=rows)
    p = Prog(); p.ldq(5); p.wb(0, 0, 0x06); p.scan(0, 16, EQUAL); p.send(E_CNT); p.send(E_MLO); p.halt()
    await check_prog(h, f, "LDQ then RECV patches Q byte 0", p, [0, 0x00], rows=rows)
    f.done()
    h.rows_state = None


@cocotb.test()
async def test_ldx_rows_and_restart(dut):
    h = Host(dut)
    f = Fails()
    rows = rows_with(r15=ALL_ONES)
    for pad in (0, 1):
        for r in range(16):
            row_bytes = [(rows[r] >> (8 * i)) & 0xFF for i in range(4)]
            p = Prog()
            if pad:
                p.unmask()
            p.ldq(r); p.scan(0, 16, EQUAL); p.send(E_CNT); p.send(E_MLO); p.send(E_MHI); p.halt()
            await check_prog(h, f, f"LDQ row{r} pad{pad}", p, [1, (1 << r) & 0xFF, (1 << r) >> 8], rows=rows)
            p = Prog()
            if pad:
                p.unmask()
            p.lda(r)
            for s in (E_A0, E_A1, E_A2, E_A3):
                p.send(s)
            p.halt()
            await check_prog(h, f, f"LDA row{r} pad{pad}", p, row_bytes, rows=rows)
            p = Prog()
            if pad:
                p.unmask()
            p.ldm(r); p.scan(15, 1, ROR)
            for s in (E_A0, E_A1, E_A2, E_A3):
                p.send(s)
            p.halt()
            await check_prog(h, f, f"LDM row{r} pad{pad}", p, row_bytes, rows=rows)

    p = Prog()
    p.ldq(9); p.lda(6); p.scan(0, 16, EQUAL); p.send(E_MLO); p.send(E_MHI); p.send(E_A0); p.halt()
    exp = [0x00, 0x02, 6]
    await h.fresh(DEF_ROWS)
    await h.run(p, until_halt=200)
    f.chk(h.emits == exp, f"LDx restart baseline: SEND {h.emits} expected {exp}")
    for k in range(1, 13):
        await h.execute_request()
        for _ in range(k):
            await h._cycle(0, 0)
        await h.execute_request()
        h.halt_cycle = None
        for _ in range(3):
            await h._cycle(0, 0)
        h.emits.clear()
        await h.run_schedule(p.sched[3:], until_halt=200)
        f.chk(h.emits == exp, f"restart after {k} cycles: SEND {h.emits} expected {exp}")
        f.chk(h.halt_cycle == len(p.sched) + HALT_LATENCY, f"restart after {k} cycles: HALT cycle {h.halt_cycle}")
    f.done()


@cocotb.test()
async def test_branch_both_ways(dut):
    h = Host(dut)
    f = Fails()
    rows = list(DEF_ROWS)
    await h.fresh(rows)
    scenarios = {
        'reset': ([], False),
        'a_zero': ([('wb', 1, 0)], True),
        'a_nonzero': ([('wb', 1, 0x100)], True),
        'within_miss': ([('wb', 0, 0x80808080), ('wb', 1, 0), ('scan', 0, 16, THR, 0)], True),
        'within_hit': ([('wb', 0, 0x80808080), ('wb', 1, 4), ('scan', 0, 16, THR, 0)], True),
        'equal_hit': ([('wb', 0, rows[5]), ('scan', 0, 16, EQUAL, 0)], False),
        'equal_miss': ([('wb', 0, 0xDEADBEEF), ('scan', 0, 16, EQUAL, 0)], False),
        'nearest': ([('wb', 0, 0x05050505), ('scan', 0, 16, HAM, 0)], False),
    }
    conds = [(C_ALWAYS, 'ALWAYS'), (C_THR, 'THRESHOLD_HIT'), (C_NTHR, 'NOT_THRESH'), (C_MINV, 'MIN_VALID'),
             (C_CNTNZ, 'COUNT_NZ'), (C_MATNZ, 'MATCH_NZ'), (C_AZ, 'A_ZERO'), (C_ANZ, 'A_NONZERO')]
    for sname, (steps, a_defined) in scenarios.items():
        for cond, cname in conds:
            if cond in (C_AZ, C_ANZ) and not a_defined:
                continue
            p = Prog()
            ref = Ref(rows)
            for st in steps:
                if st[0] == 'wb':
                    p.wb32(st[1], st[2])
                    ref.wb(st[1], st[2])
                else:
                    p.scan(*st[1:])
                    ref.scan(*st[1:])
            s = ref.s
            taken = {C_ALWAYS: True, C_THR: s.THRESHOLD_HIT, C_NTHR: not s.THRESHOLD_HIT, C_MINV: s.MIN_VALID,
                     C_CNTNZ: s.count != 0, C_MATNZ: s.MATCH != 0, C_AZ: s.A == 0, C_ANZ: s.A != 0}[cond]
            p.branch(cond, 1)
            p.send(E_CNT)
            p.send(E_FLG)
            p.halt()
            flags = (2 if s.THRESHOLD_HIT else 0) | (1 if s.MIN_VALID else 0)
            exp = ([] if taken else [s.count]) + [flags]
            await h.reset()
            await h.run(p, until_halt=200)
            f.chk(h.emits == exp, f"{cname} in {sname} (taken={taken}): SEND {h.emits} expected {exp}")
            f.chk(h.halt_cycle == len(p.sched) - (1 if taken else 0) + HALT_LATENCY, f"{cname} in {sname}: HALT cycle {h.halt_cycle}")

    p = Prog()
    p.branch(C_ALWAYS, 17)
    p.send(E_IDX)
    p.halt()
    for _ in range(15):
        p.send(E_DIST)
    p.branch(C_ALWAYS, (1 - 19) & 0xFF)
    await h.reset()
    await h.run(p, until_halt=100)
    f.chk(h.emits == [0] and h.pins()["halt"] == 1, f"long forward and backward BRANCH: SEND {h.emits}")
    f.chk(h.halt_cycle == 4 + HALT_LATENCY, f"long BRANCH path executes 4 instructions: HALT cycle {h.halt_cycle}")
    f.done()
