# HADES: Hamming-Aware Decode, Execute, and Search

[![gds](../../workflows/gds/badge.svg)](../../actions/workflows/gds.yaml) [![test](../../workflows/test/badge.svg)](../../actions/workflows/test.yaml) [![docs](../../workflows/docs/badge.svg)](../../actions/workflows/docs.yaml)

HADES is a small processing-near-memory (PNM) engine for masked binary similarity search, built for Tiny Tapeout (SKY130, `ttsky26d`, 2x2 tiles).
The data rows sit in an on-chip register file and the compute logic next to it scans them in place, so only results leave the chip. A host loads a
16-bit-instruction program (32 slots) and up to 16 rows of 32 bits. The engine then computes Hamming distance (top-2, threshold bitmap, exact match)
and OR/AND/popcount reductions over the rows and streams the results back over an 8-bit port.

See [docs/info.md](docs/info.md) for how to use it.

## Architecture
- 16 data rows of 32 bits and the 32-instruction program share one register-file macro (`rf_top`).
- Three working registers (Q, A, MASK) and a small set of result registers. `LDQ`/`LDA`/`LDM row` load them from a data row on-chip (2 cycles each), so a query, threshold or mask can come from stored data or a previous result (`STA` then `LDx`) without the host resending it.
- `SCAN` runs a masked XOR and popcount over a range of rows. `SCANP` reads two rows per cycle, and `SCANSEL` scans only the rows selected by `MATCH`.
- Distances and popcounts are 6 bits (32 is representable), with identity `0x3F`.
- Rows are written by a program (4 `RECV` + `STA row`), and results are streamed out with `SEND`.

## Layout
| Path | Contents |
|---|---|
| `src-veryl/` | Veryl RTL sources |
| `src/` | generated SystemVerilog, wrapper `tt_um_hades.v` and the `rf_top` macro (committed, CI does not run Veryl) |
| `test/` | cocotb tests (RTL and gate level) |
| `sim/` | standalone Icarus testbench |
| `tools/` | assembler (`hades_asm.py`), instruction-level simulator (`hades_sim.py`) and its tests |
| `eval/` | evaluation scripts and results (see `eval/README.md`) |
| `docs/` | usage, ISA, evaluation and paper sources |

## Build
Run `veryl build` after editing `src-veryl/`.

## Tests
Needs Icarus Verilog (`iverilog`) and `pip install -r test/requirements.txt`.

```sh
cd test && make sim                                   # cocotb, RTL
cd test && make sim COCOTB_TEST_MODULES=test_scansel  # one module
cd test && make -B GATES=yes                          # gate level
python3 tools/test_hades.py   # assembler and simulator tests
```

## License
Apache-2.0 (see [LICENSE](LICENSE)). The `rf_top` macro is by Sylvain Munaut / Tiny Tapeout, see [RF Macro](https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_rf_test).
