import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge

OP_SHQ = 0
OP_SHM = 1
OP_THR = 2
OP_WR  = 3
OP_RUN = 4
OP_RDO = 5


async def strobe(dut, op, data):
    await FallingEdge(dut.clk)
    dut.ui_in.value  = data
    dut.uio_in.value = op << 1
    await ClockCycles(dut.clk, 2)
    dut.uio_in.value = (op << 1) | 1
    await ClockCycles(dut.clk, 4)
    dut.uio_in.value = op << 1
    await ClockCycles(dut.clk, 3)


async def load32(dut, op, word):
    for shift in (24, 16, 8, 0):
        await strobe(dut, op, (word >> shift) & 0xFF)


@cocotb.test()
async def test_reset_state(dut):
    clock = Clock(dut.clk, 40, unit="ns")
    cocotb.start_soon(clock.start())

    dut.ena.value    = 1
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    dut.rst_n.value  = 0
    await ClockCycles(dut.clk, 8)
    dut.rst_n.value  = 1
    await ClockCycles(dut.clk, 4)

    status = int(dut.uio_out.value) & 0xE0
    assert status == 0, f"expected busy/done/any_hit=0 after reset, got uio_out={dut.uio_out.value}"


@cocotb.test()
async def test_write_and_search(dut):
    clock = Clock(dut.clk, 40, unit="ns")
    cocotb.start_soon(clock.start())

    dut.ena.value    = 1
    dut.ui_in.value  = 0
    dut.uio_in.value = 0
    dut.rst_n.value  = 0
    await ClockCycles(dut.clk, 8)
    dut.rst_n.value  = 1
    await ClockCycles(dut.clk, 4)

    db = [0xCAFEBABE] + [0xA0000000 | (i * 0x01010101) for i in range(1, 16)]

    for word in db:
        await load32(dut, OP_SHQ, word)
        await strobe(dut, OP_WR, 0x00)

    await load32(dut, OP_SHQ, db[0])
    await load32(dut, OP_SHM, 0xFFFFFFFF)
    await strobe(dut, OP_THR, 5)

    await strobe(dut, OP_RUN, 0x00)

    for _ in range(200):
        await ClockCycles(dut.clk, 1)
        if (int(dut.uio_out.value) >> 6) & 1:
            break
    else:
        assert False, "timeout: done never asserted"

    best_idx = int(dut.uo_out.value) & 0x0F
    assert best_idx == 0, f"expected best_idx=0, got {best_idx}"

    await strobe(dut, OP_RDO, 0x00)
    best_dist = int(dut.uo_out.value) & 0x3F
    assert best_dist == 0, f"expected best_dist=0, got {best_dist}"

    assert (int(dut.uio_out.value) >> 7) & 1, "expected any_hit=1"

    await strobe(dut, OP_RDO, 0x00)
    hits_lo = int(dut.uo_out.value)
    await strobe(dut, OP_RDO, 0x00)
    hits_hi = int(dut.uo_out.value)
    hits = (hits_hi << 8) | hits_lo
    assert hits & (1 << 0), f"expected hits[0]=1, got hits=0x{hits:04x}"
