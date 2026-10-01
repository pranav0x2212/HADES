import random

import cocotb
from cocotb.triggers import ClockCycles

from hades_tb import *
from hades_ref import *


@cocotb.test()
async def test_scanp_all_base_len(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0x5CA2)
    q = 0x9E3779B9
    rows = mixed_rows(rng, q)
    await h.fresh(rows)
    for op in (EQUAL, ROR, RAND):
        for base in range(16):
            for ln in range(1, 17):
                mask = rng.choice([ALL_ONES, 0x0000FFFF, rng.getrandbits(32) | 1])
                p, exp = scanp_prog(rows, q, mask, rng.getrandbits(32), [(base, ln, op, 0)])
                await run_scanp(h, f, f"SCANP op{op} base{base} len{ln} mask{mask:08x}", p, exp, rows)
    f.done()


@cocotb.test()
async def test_scanp_chains_acc(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0xACC)
    q = 0xA5C3_0F96
    rows = mixed_rows(rng, q)
    await h.fresh(rows)
    for i in range(120):
        op = rng.choice((EQUAL, ROR, RAND))
        scans = []
        for k in range(rng.randrange(1, 4)):
            scans.append((rng.randrange(16), rng.randrange(1, 17), op, 1 if (k or rng.random() < 0.3) else 0))
        mask = rng.choice([ALL_ONES, rng.getrandbits(32), 0xFFFF0000])
        p, exp = scanp_prog(rows, q, mask, rng.getrandbits(32), scans)
        await run_scanp(h, f, f"chain{i} {scans} mask{mask:08x}", p, exp, rows)
    f.done()


@cocotb.test()
async def test_scanp_count_saturates(dut):
    h = Host(dut)
    f = Fails()
    q = 0xA5A5A5A5
    rows = [q] * 16
    await h.fresh(rows)
    for scans in ([(0, 16, EQUAL, 0), (0, 16, EQUAL, 1), (0, 16, EQUAL, 1)],
                  [(0, 15, EQUAL, 0), (1, 15, EQUAL, 1), (0, 16, EQUAL, 1), (3, 3, EQUAL, 1)],
                  [(5, 11, EQUAL, 0)] + [(0, 16, EQUAL, 1)] * 2):
        p, exp = scanp_prog(rows, q, ALL_ONES, 0, scans)
        await run_scanp(h, f, f"saturate {scans}", p, exp, rows)
        f.chk(exp[6] == 31, f"model sanity: count {exp[6]}")
    f.done()


@cocotb.test()
async def test_scanp_fallback_ops_match_scan(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0xFA11)
    rows = [rng.getrandbits(32) for _ in range(16)]
    await h.fresh(rows)
    for op in (HAM, HAM2, THR, RPOP, RMAXPOP):
        for base, ln, acc in ((0, 16, 0), (3, 9, 0), (15, 4, 0), (7, 1, 0), (6, 8, 0), (2, 13, 1)):
            res = []
            for mn in ("scan", "scanp"):
                p = Prog()
                p.wb32(0, 0x12345678)
                p.wb32(1, 0x00000007)
                getattr(p, mn)(base, ln, op, acc)
                for e in ALL_EMITS + [E_IDX2, E_DIST2]:
                    p.send(e)
                p.halt()
                await h.reset()
                await h.run(p, until_halt=400)
                res.append((list(h.emits), h.halt_cycle))
            f.chk(res[0] == res[1], f"fallback op{op} base{base} len{ln} acc{acc}: SCAN {res[0]} vs SCANP {res[1]}")
    f.done()


@cocotb.test()
async def test_scanp_fetch_and_branch(dut):
    h = Host(dut)
    f = Fails()
    q = 0x0F0F0F0F
    rows = [q ^ (1 << i) if i != 5 else q for i in range(16)]
    await h.fresh(rows)
    for pad in (0, 1):
        for ln in (1, 2, 3, 4, 7, 16):
            for qq, taken in ((q, True), (q ^ 0x80000000, False)):
                p = Prog()
                p.wb32(0, qq)
                if pad:
                    p.unmask()
                p.scanp(0, ln if ln >= 6 else 16, EQUAL, 0)
                p.branch(C_MATNZ, 1)
                p.send(E_CNT)
                p.send(E_MLO)
                p.halt()
                n = ln if ln >= 6 else 16
                hit = qq == q and n > 5
                exp = [rows_mlo(rows, qq, n)] if hit else [0, 0]
                await h.reset()
                await h.run(p, until_halt=200)
                f.chk(h.emits == exp, f"branch pad{pad} len{ln} taken={hit}: SEND {h.emits} expected {exp}")
                skipped = 1 if hit else 0
                f.chk(h.halt_cycle == len(p.sched) - skipped + HALT_LATENCY, f"branch pad{pad} len{ln}: HALT cycle {h.halt_cycle}")
    f.done()


@cocotb.test()
async def test_scanp_sta_ldx_hazards(dut):
    h = Host(dut)
    f = Fails()
    await h.fresh(DEF_ROWS)
    for row in (6, 7, 14, 15):
        for base in (6, 7):
            p = Prog()
            p.wb32(1, 0xCAFEF00D)
            p.sta(row)
            p.ldq(row)
            p.scanp(base, 16, EQUAL, 0)
            p.send(E_MLO)
            p.send(E_MHI)
            p.send(E_CNT)
            p.lda(row)
            p.scanp(0, 16, ROR, 0)
            p.send(E_A0)
            p.wb32(1, DEF_ROWS[row])
            p.sta(row)
            p.halt()
            hit = row >= base
            m = (1 << row) if hit else 0
            await h.reset()
            await h.run(p, until_halt=200)
            exp_a = 0
            for r in range(16):
                exp_a |= 0xCAFEF00D if r == row else DEF_ROWS[r]
            exp = [m & 0xFF, m >> 8, 1 if hit else 0, exp_a & 0xFF]
            f.chk(h.emits == exp, f"STA row{row} scan base{base}: SEND {h.emits} expected {exp}")
            f.chk(h.halt_cycle == len(p.sched) + HALT_LATENCY, f"STA row{row} base{base}: HALT cycle {h.halt_cycle}")
    f.done()


@cocotb.test()
async def test_scanp_restart_mid_scan(dut):
    h = Host(dut)
    f = Fails()
    rows = [0x01010101 << (i % 8) for i in range(16)]
    await h.fresh(rows)
    p = Prog()
    p.scanp(0, 16, ROR, 0)
    for e in (E_A0, E_A1):
        p.send(e)
    p.scan(0, 3, ROR, 0)
    for e in (E_A0, E_A1):
        p.send(e)
    p.scanp(0, 16, RAND, 0)
    p.send(E_A0)
    p.halt()
    exp = [0xFF, 0xFF, 0x07, 0x07, 0x00]
    await h.reset()
    await h.run(p, until_halt=200)
    f.chk(h.emits == exp, f"restart baseline: SEND {h.emits} expected {exp}")
    for k in range(1, 30):
        await h.reset()
        await h.load(p.words)
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
