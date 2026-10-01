import random

import cocotb
from cocotb.triggers import ClockCycles

from hades_tb import *
from golden_data import GOLDEN


async def run_golden(h, f, g):
    name, halts, cycles, prog, rows, sched, exp, exp_rows = g
    await h.fresh(unhex(rows, 8))
    await h.load(unhex(prog, 4))
    await h.execute_request()
    await h.run_schedule([(b, 1) for b in unhex(sched, 2)])
    f.chk(h.emits == unhex(exp, 2), f"{name}: SEND {h.emits} expected {unhex(exp, 2)}")
    if halts:
        f.chk(h.halt_cycle == cycles + HALT_LATENCY, f"{name}: HALT at cycle {h.halt_cycle}, model {cycles}")
    else:
        f.chk(h.pins()["halt"] == 0 and h.pins()["busy"] == 1, f"{name}: expected to end stalled on RECV")
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
