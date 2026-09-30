# HADES v1 — Tiny Tapeout cocotb tests

`tb.v` instantiates the wrapper `tt_um_hades`; `test.py` drives only the chip pins (reset, loader on `uio[4]`, EXECUTE on `uio[5]`, WAITBYTE data with
STROBE `uio[3]`, EMIT bytes on `uo_out`), so the same tests run at RTL and at gate level.

```sh
pip install -r requirements.txt     # cocotb; Icarus Verilog (iverilog) must be installed
make sim                            # RTL
make -B GATES=yes                   # gate level: copy the hardened netlist to gate_level_netlist.v first, set PDK_ROOT
```

The tests cover reset and initialisation, the loader, EXECUTE and restart, every SCAN op and EMIT source, WAITBYTE, MASK, STA, LDQ/LDA/LDM (2 cycles, hazards),
the 6-bit `min_dist`/`min2_dist` (popcount/distance 32), all BRANCH conditions and 15 golden workloads.
