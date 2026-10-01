import random

import cocotb
from cocotb.triggers import ClockCycles

from hades_tb import *


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
    p.send(E_DIST)
    p.halt()
    await h.load(p.words)
    await ClockCycles(dut.clk, 40)
    assert not h.emits and h.pins()["halt"] == 0, "a loaded program must not run before EXECUTE"
    await h.execute_request()
    await h.run_schedule(p.sched)
    assert h.emits == [0x3F], f"expected one SEND of min_dist reset value, got {h.emits}"
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
    assert h.emits == [idx, dist], f"NEAREST result {h.emits}, expected {[idx, dist]}"
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
async def test_execute_ignored_with_pending_byte(dut):
    h = Host(dut)
    await h.reset()
    p = Prog()
    p.send(E_DIST)
    p.send(E_DIST)
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
    p.send(E_DIST)
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
    p.send(E_DIST)
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
        p.send(E_A0 + j % 4)
        exp.append(b)
    p.send(E_DIST)
    p.halt()
    assert len(p.words) == 32
    await check_prog(h, f, "32 slots, two per word", p, exp + [0x3F])

    p = Prog()
    for s in (E_DIST, E_IDX, E_DIST2, E_FLG, E_DIST):
        p.send(s)
    await check_prog(h, f, "odd instruction count (lone even slot)", p, [0x3F, 0, 0x3F, 0, 0x3F])

    await h.fresh()
    words = [0x6100] * 31 + [0x8000]
    await h.load(words + [0x6000, 0x6000])
    await h.execute_request()
    await h.run_schedule([], until_halt=100)
    f.chk(h.emits == [0, 0] + [0x3F] * 29, f"slot counter wrap: SEND {h.emits}")

    await h.fresh()
    for b, hold in ((0x61, 10), (0x00, 10), (0x60, 3), (0x00, 3)):
        await h.load_byte(b, hold)
        await h.clocks(2)
    await h.execute_request()
    await h.run_schedule([], until_halt=50)
    f.chk(h.emits == [0x3F, 0] and h.pins()["halt"] == 1, f"LD_STROBE must be edge sensitive: SEND {h.emits}")

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
    p.send(E_IDX)
    p.send(E_DIST)
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
    f.chk(h.emits == [5, 0], f"run after idle strobe: SEND {h.emits}")

    await h.fresh()
    p = Prog()
    p.halt()
    await h.run(p)
    f.chk(h.halt_cycle == len(p.sched) + HALT_LATENCY, f"EXECUTE latency: HALT seen at cycle {h.halt_cycle}")

    p = Prog()
    p.send(E_IDX)
    p.send(E_DIST)
    p.loadq(5)
    p.scan(0, 16, HAM)
    p.halt()
    await h.fresh()
    await h.run(p, until_halt=300)
    f.chk(h.emits == [0, 0x3F] and h.pins()["halt"] == 1, f"first run: SEND {h.emits}")
    await h.rerun(p, until_halt=300)
    f.chk(h.emits == [0, 0x3F, 5, 0], f"restart must keep the previous run's results: SEND {h.emits}")

    p = Prog()
    p.send(E_DIST)
    p.wb(0, 0, 5)
    p.send(E_IDX)
    p.halt()
    await h.fresh()
    await h.load(p.words)
    await h.execute_request()
    await h.run_schedule([(0, 0)] * 8, tail=0)
    pins = h.pins()
    f.chk(pins["busy"] == 1 and pins["halt"] == 0 and h.emits == [0x3F], "stalled on RECV while running")
    await h.execute_request()
    await h.run_schedule([(0, 0)] * 6, tail=0)
    f.chk(h.emits == [0x3F, 0x3F] and h.pins()["halt"] == 0, f"EXECUTE while running must restart at slot 0: SEND {h.emits}")
    await h.run_schedule([(5, 1), (0, 1), (0, 1)])
    f.chk(h.emits == [0x3F, 0x3F, 0] and h.pins()["halt"] == 1, f"restarted run completes: SEND {h.emits}")

    p = Prog()
    p.send(E_DIST)
    p.halt()
    await h.fresh()
    await h.load(p.words)
    await h.reset()
    await h.execute_request()
    await h.clocks(6)
    f.chk(h.pins()["halt"] == 1 and not h.emits, "reset erases the program")
    f.done()
