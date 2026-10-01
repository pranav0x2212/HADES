import random

import cocotb
from cocotb.triggers import ClockCycles

from hades_tb import *
from hades_ref import *


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
        p.send(src)
    p.halt()
    await h.run(p)
    flags = (1 << 1 if match else 0) | 1
    assert h.emits == [match & 0xFF, count, flags], f"WITHIN result {h.emits}, expected {[match & 0xFF, count, flags]}"


@cocotb.test()
async def test_scan_operations(dut):
    h = Host(dut)
    f = Fails()

    def q5():
        p = Prog()
        p.loadq(5)
        return p

    p = q5(); p.scan(0, 16, HAM); p.send(E_IDX); p.send(E_DIST); p.halt()
    await check_prog(h, f, "NEAREST", p, [5, 0])
    p = q5(); p.scan(0, 16, HAM2)
    for s in (E_IDX, E_DIST, E_IDX2, E_DIST2):
        p.send(s)
    p.halt()
    await check_prog(h, f, "NEAREST2", p, [5, 0, 1, 4])
    p = q5(); p.wb(1, 0, 4); p.scan(0, 16, THR)
    for s in (E_MLO, E_MHI, E_CNT, E_FLG):
        p.send(s)
    p.halt()
    await check_prog(h, f, "WITHIN", p, [0xB2, 0x20, 5, 3])
    p = q5(); p.scan(0, 16, EQUAL); p.send(E_MLO); p.send(E_MHI); p.send(E_CNT); p.halt()
    await check_prog(h, f, "EQUAL", p, [0x20, 0, 1])
    p = Prog(); p.scan(0, 6, ROR); p.send(E_A0); p.halt()
    await check_prog(h, f, "REDUCE_OR rows 0-5", p, [0x07])
    p = Prog(); p.scan(4, 2, RAND); p.send(E_A0); p.halt()
    await check_prog(h, f, "REDUCE_AND rows 4-5", p, [0x04])
    p = Prog(); p.scan(0, 6, RPOP); p.send(E_A0); p.halt()
    await check_prog(h, f, "REDUCE_POP rows 0-5", p, [0x1C])
    p = Prog(); p.scan(0, 6, RMAXPOP); p.send(E_IDX); p.send(E_DIST); p.halt()
    await check_prog(h, f, "ARGMAX_POP rows 0-5", p, [3, 8])
    p = q5(); p.scan(6, 10, HAM); p.scan(0, 6, HAM, acc=1); p.send(E_IDX); p.send(E_DIST); p.halt()
    await check_prog(h, f, "NEAREST ACC chained scan", p, [5, 0])
    p = Prog(); p.scan(12, 8, RPOP); p.send(E_A0); p.halt()
    await check_prog(h, f, "range clamp at row 15", p, [0x30])
    p = q5(); p.loada(4, 0xB1, 0xB2, 0xB3); p.scan(0, 16, THR)
    for s in range(13):
        p.send(s)
    p.halt()
    await check_prog(h, f, "all SEND sources", p,
                     [5, 0, 4, 0xB1, 0xB2, 0xB3, 0xB2, 0x20, 5, 3, 0, 0x3F, 0xFF])

    cycles = []
    for n in (1, 16):
        p = Prog(); p.scan(0, n, ROR); p.halt()
        await h.fresh()
        await h.run(p, until_halt=100)
        cycles.append(h.halt_cycle)
    f.chk(cycles[1] - cycles[0] == 15, f"a 16-row SCAN takes 15 more cycles than a 1-row SCAN: {cycles}")
    f.done()


async def maxpop32(dut, rows):
    h = Host(dut)
    p = Prog(); p.scan(0, 16, RMAXPOP); p.send(E_IDX); p.send(E_DIST); p.halt()
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
    p = Prog(); p.loadq(0); p.scan(0, 16, HAM); p.send(E_IDX); p.send(E_DIST); p.halt()
    await h.fresh([ALL_ONES] * 16)
    await h.run(p, until_halt=200)
    h.rows_state = None
    assert h.emits == [0, 32] and h.pins()["halt"] == 1, f"got {h.emits}"


@cocotb.test()
async def test_value_corners(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0xC0E5)
    rows = [0x00000000, 0x7FFFFFFF, 0xFFFFFFFF, 0x80000000, 0xFFFFFFFE, 0x0000FFFF, 0xFFFF0000, 0x00000001,
            0x55555555, 0xAAAAAAAA, 0x0F0F0F0F, 0xF0F0F0F0, 0x12345678, 0x87654321, 0xFFFFFFFF, 0x00000000]
    for a0 in (0, 1, 31, 32, 33, 63, 64, 127, 255, 0x12340003, 0xFFFFFF00):
        await run_body(h, f, f"WITHIN A={a0:#x}", rows, 0, ALL_ONES, a0, [('scan', 0, 16, THR, 0)])
    ones = [ALL_ONES] * 16
    for op in (HAM, HAM2, THR):
        await run_body(h, f, f"distance 32 op{op}", ones, 0, ALL_ONES, 32, [('scan', 0, 16, op, 0)])
    rand_rows = [rng.getrandbits(32) for _ in range(16)]
    for op in range(8):
        for acc in (0, 1):
            a0 = rng.getrandbits(32) if op in (ROR, RAND) else rng.randrange(40)
            await run_body(h, f, f"MASK=0 op{op} acc{acc}", rand_rows, rng.getrandbits(32), 0, a0, [('scan', 0, 16, op, acc)])
    emits, _ = await run_body(h, f, "REDUCE_POP all ones", ones, 0, ALL_ONES, 0, [('scan', 0, 16, RPOP, 0)])
    f.chk(emits is not None and emits[2:6] == [0x00, 0x02, 0x00, 0x00], f"REDUCE_POP of 16 all-ones rows must be 512: {emits}")
    f.done()


@cocotb.test()
async def test_count_saturation_plain(dut):
    h = Host(dut)
    f = Fails()
    q = 0xA5A5A5A5
    rows = [q] * 16
    chains = [
        [('scan', 0, 16, EQUAL, 0), ('scan', 0, 16, EQUAL, 1), ('scan', 0, 16, EQUAL, 1)],
        [('scan', 0, 15, EQUAL, 0), ('scan', 1, 15, EQUAL, 1), ('scan', 0, 16, EQUAL, 1), ('scan', 3, 3, EQUAL, 1)],
        [('scan', 0, 16, THR, 0), ('scan', 0, 16, THR, 1), ('scan', 0, 16, THR, 1)],
        [('scan', 5, 11, THR, 0), ('scan', 0, 16, THR, 1), ('scan', 0, 16, THR, 1)],
    ]
    for steps in chains:
        emits, _ = await run_body(h, f, f"saturate {steps}", rows, q, ALL_ONES, 63, steps)
        f.chk(emits is not None and emits[8] == 31, f"count must saturate at 31: {emits}")
    f.done()


@cocotb.test()
async def test_scan_edges(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0x5ED6E5)
    rows = scansel_rows(rng)
    await h.fresh(rows)
    for op in range(8):
        for base, ln in ((0, 16), (15, 16), (15, 1), (7, 9), (0, 1), (8, 1), (3, 13)):
            for acc in (0, 1):
                q = rng.choice([SCANSEL_Q0, rng.getrandbits(32)])
                mask = rng.choice([ALL_ONES, rng.getrandbits(32) | 1, 0x0000FFFF])
                a0 = rng.getrandbits(32) if op in (ROR, RAND) else rng.randrange(40)
                await run_scansel(h, f, f"SCAN op{op} base{base} len{ln} acc{acc}", rows, rng.getrandbits(16), q, mask, a0,
                                  [('scan', base, ln, op, acc)])
    f.done()
