# HADES Rev2 — Tiny Tapeout cocotb tests

`tb.v` instantiates the wrapper `tt_um_hades`; the test modules drive only the chip pins (reset, loader on `uio[4]`, EXECUTE on `uio[5]`, RECV data with
STROBE `uio[3]`, SEND bytes on `uo_out`), so the same tests run at RTL and at gate level.

```sh
pip install -r requirements.txt     # cocotb; Icarus Verilog (iverilog) must be installed
make sim                            # RTL
make -B GATES=yes                   # gate level: copy the hardened netlist to gate_level_netlist.v first, set PDK_ROOT
make sim COCOTB_TEST_MODULES=test_scansel    # a single module
```

| Module | Covers |
|---|---|
| `test_host.py` | reset and initialisation, loader, EXECUTE and restart, end-to-end search |
| `test_isa.py` | LDQ/LDA/LDM (all rows, 2 cycles, hazards, restart), STA, RECV/SEND, MASK/UNMASK, every BRANCH condition both ways |
| `test_scan.py` | SCAN with all 8 ops, INIT/ACC, WITHIN thresholds, 32-bit distance and popcount corners, MASK = 0, count saturation, clamp edges |
| `test_scanp.py` | SCANP (dual-row) for every base/length, ACC chains, fallback ops, fetch/branch, hazards, restart |
| `test_scansel.py` | SCANSEL (MATCH-selected) empty/single/multiple selections, all ops, chains, narrowing, reserved fields, restart |
| `test_golden.py` | the 15 golden workloads |

Shared code: `hades_tb.py` (pin-level host and program builders), `hades_ref.py` (self-contained reference model and model-driven program builders), `golden_data.py` (golden workload table).
New test modules must be added to `COCOTB_TEST_MODULES` in the Makefile.
