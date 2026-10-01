import random

import cocotb
from cocotb.triggers import ClockCycles

from hades_tb import *
from hades_ref import *


@cocotb.test()
async def test_scansel_directed(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0x5CA11)
    rows = scansel_rows(rng)
    await h.fresh(rows)
    for sel in SELECTIONS:
        for op in range(8):
            for acc in (0, 1):
                q = rng.choice([SCANSEL_Q0, rng.getrandbits(32), SCANSEL_Q0 ^ 0x00010000])
                mask = rng.choice([ALL_ONES, 0xFFFF0000 | rng.getrandbits(16), rng.getrandbits(32), 0x0000FFFF])
                a0 = rng.getrandbits(32) if op in (ROR, RAND) else rng.randrange(40)
                await run_scansel(h, f, f"SCANSEL sel{sel:04x} op{op} acc{acc}", rows, sel, q, mask, a0, [('scansel', op, acc)])
    f.done()


@cocotb.test()
async def test_scansel_all_ones_equals_scan(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0xA11)
    rows = scansel_rows(rng)
    await h.fresh(rows)
    for op in range(8):
        for acc in (0, 1):
            q = rng.getrandbits(32)
            mask = rng.choice([ALL_ONES, rng.getrandbits(32)])
            a0 = rng.getrandbits(32) if op in (ROR, RAND) else rng.randrange(40)
            res = []
            for st in (('scansel', op, acc), ('scan', 0, 16, op, acc)):
                res.append(await run_scansel(h, f, f"{st}", rows, 0xFFFF, q, mask, a0, [st]))
            f.chk(res[0] == res[1], f"op{op} acc{acc}: SCANSEL {res[0]} vs SCAN {res[1]}")
            f.chk(res[0][1] is not None and res[0][1] == res[1][1], f"op{op} acc{acc}: cycle counts differ")
    f.done()


@cocotb.test()
async def test_scansel_chains(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0xC4A1)
    rows = scansel_rows(rng)
    await h.fresh(rows)
    skipped = 0
    for i in range(300):
        steps = []
        for _ in range(rng.randrange(1, 5)):
            kind = rng.choice(('scansel', 'scansel', 'scan', 'scanp'))
            op = rng.randrange(8)
            acc = rng.choice((0, 1))
            if kind == 'scansel':
                steps.append(('scansel', op, acc))
            else:
                steps.append((kind, rng.randrange(16), rng.randrange(1, 17), op, acc))
            if rng.random() < 0.3:
                steps.append(('wb8', rng.choice((0, 1, 2)), rng.randrange(40)))
            if rng.random() < 0.3:
                steps.append(('emit', rng.choice(EMIT_ORDER)))
        sel = rng.choice([rng.getrandbits(16), rng.getrandbits(16) | rng.getrandbits(16), 0xFFFF, 0x0000, 1 << rng.randrange(16)])
        q = rng.choice([SCANSEL_Q0, rng.getrandbits(32)])
        mask = rng.choice([ALL_ONES, rng.getrandbits(32) | 1, 0x0000FFFF])
        a0 = rng.randrange(1 << 32) if rng.random() < 0.5 else rng.randrange(40)
        r = await run_scansel(h, f, f"chain{i} sel{sel:04x} {steps}", rows, sel, q, mask, a0, steps)
        skipped += r[0] is None
    f.chk(skipped < 60, f"too many chain cases skipped ({skipped})")
    f.done()


@cocotb.test()
async def test_scansel_narrowing(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0x9A55)
    rows = scansel_rows(rng)
    await h.fresh(rows)
    for sel in (0xFFFF, 0x0FF0, 0xAAAA, 0x0001):
        for thr1, thr2 in ((20, 8), (6, 3), (3, 3), (40, 0)):
            steps = [('scansel', THR, 0), ('wb8', 1, thr2), ('scansel', THR, 0), ('scansel', EQUAL, 0), ('scansel', HAM, 0)]
            await run_scansel(h, f, f"narrow sel{sel:04x} thr{thr1},{thr2}", rows, sel, SCANSEL_Q0, ALL_ONES, thr1, steps)
    f.done()


@cocotb.test()
async def test_scansel_fetch_and_branch(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0xF37C)
    rows = scansel_rows(rng)
    await h.fresh(rows)
    for pad in (0, 1):
        for sel in (0x0000, 0x0001, 0x8000, 0x0006, 0xFFFF):
            for cond, name in ((C_MATNZ, 'MATNZ'), (C_MINV, 'MINV'), (C_CNTNZ, 'CNTNZ')):
                for op in (HAM, EQUAL):
                    p0, ref = scansel_setup(rows, sel)
                    p = Prog()
                    p.wb32(2, ALL_ONES)
                    ref.wb(2, ALL_ONES)
                    if pad:
                        p.unmask()
                    k = ref.scansel(op, 0)
                    p.scansel(op, 0, k)
                    p.branch(cond, 1)
                    p.send(E_CNT)
                    p.send(E_MLO)
                    p.halt()
                    s = ref.s
                    taken = {C_MATNZ: s.MATCH != 0, C_MINV: s.MIN_VALID, C_CNTNZ: s.count != 0}[cond]
                    exp = ([s.MATCH & 0xFF] if taken else [s.count, s.MATCH & 0xFF])
                    await h.reset()
                    await h.run(p0, until_halt=300)
                    h.emits.clear()
                    await h.load(p.words)
                    await h.execute_request()
                    await h.run_schedule(p.sched, until_halt=300)
                    f.chk(h.emits == exp, f"branch pad{pad} sel{sel:04x} {name} op{op}: SEND {h.emits} expected {exp}")
                    skipped = 1 if taken else 0
                    f.chk(h.halt_cycle == len(p.sched) - skipped + HALT_LATENCY,
                          f"branch pad{pad} sel{sel:04x} {name} op{op}: HALT cycle {h.halt_cycle}")
    f.done()


@cocotb.test()
async def test_scansel_restart_mid_scan(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0x7E57)
    rows = scansel_rows(rng)
    sel = 0xB6D5
    p0, ref = scansel_setup(rows, sel, q_after=SCANSEL_Q0 ^ 0x40)
    p1 = Prog()
    exp = []
    for kind, op in (('scansel', HAM2), ('scansel', ROR), ('scan', RPOP), ('scansel', RMAXPOP), ('scansel', RAND)):
        if kind == 'scansel':
            k = ref.scansel(op, 0)
            p1.scansel(op, 0, k)
        else:
            p1.scan(0, 16, op, 0)
            ref.scan(0, 16, op, 0)
        for e in ((E_IDX, E_DIST, E_IDX2, E_DIST2) if op in (HAM2, RMAXPOP) else (E_A0, E_A1)):
            p1.send(e)
            exp.append(ref.emits()[EMIT_ORDER.index(e)])
    p1.halt()
    assert len(p1.words) <= 32
    await h.fresh(rows)
    await h.run(p0, until_halt=300)
    h.emits.clear()
    await h.load(p1.words)
    await h.execute_request()
    await h.run_schedule(p1.sched, until_halt=300)
    f.chk(h.emits == exp, f"restart baseline: SEND {h.emits} expected {exp}")
    for k in range(1, 70):
        await h.execute_request()
        for _ in range(k):
            await h._cycle(0, 0)
        await h.execute_request()
        h.halt_cycle = None
        for _ in range(3):
            await h._cycle(0, 0)
        h.emits.clear()
        await h.run_schedule(p1.sched[3:], until_halt=300)
        f.chk(h.emits == exp, f"restart after {k} cycles: SEND {h.emits} expected {exp}")
        f.chk(h.halt_cycle == len(p1.sched) + HALT_LATENCY, f"restart after {k} cycles: HALT cycle {h.halt_cycle}")
    f.done()


@cocotb.test()
async def test_scansel_positions(dut):
    h = Host(dut)
    f = Fails()
    rng = random.Random(0x7051)
    rows = scansel_rows(rng)
    await h.fresh(rows)
    for r in range(16):
        for op in (HAM, RPOP):
            q = rng.choice([SCANSEL_Q0, rng.getrandbits(32)])
            mask = rng.choice([ALL_ONES, rng.getrandbits(32) | 1])
            await run_scansel(h, f, f"single row {r} op{op}", rows, 1 << r, q, mask, rng.randrange(40), [('scansel', op, 0)])

    for fa, fb in ((0xF, 0x0), (0x0, 0xF), (0x5, 0xA), (0xF, 0xF)):
        for sel in (0x0000, 0x0001, 0x8421, 0xFFFF):
            p0, ref = scansel_setup(rows, sel)
            p1, exp = scansel_body(ref, SCANSEL_Q0 ^ 0x1234, ALL_ONES, 7, [('scansel', HAM, 0)])
            idx = [i for i, w in enumerate(p1.words) if (w >> 12) == 0xB]
            f.chk(len(idx) == 1, "exactly one SCANSEL word expected")
            p1.words[idx[0]] |= (fa << 8) | (fb << 4)
            await run_pair(h, f, f"SCANSEL reserved A={fa:#x} B={fb:#x} sel{sel:04x}", rows, p0, p1, exp)

    for r in (0, 6, 15):
        value = rng.getrandbits(32)
        p0, ref = scansel_setup(rows, (1 << r) | 0x8001)
        p1, exp = scansel_body(ref, None, None, None, [('wb', 1, value), ('sta', r), ('wb', 0, value), ('scansel', HAM, 0)])
        await run_pair(h, f, f"STA row{r} then SCANSEL", rows, p0, p1, exp)
        h.rows_state = None
    f.done()
