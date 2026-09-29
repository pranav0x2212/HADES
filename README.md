# HADES v1 — processing-near-memory Hamming search engine

[![gds](../../workflows/gds/badge.svg)](../../actions/workflows/gds.yaml) [![test](../../workflows/test/badge.svg)](../../actions/workflows/test.yaml) [![docs](../../workflows/docs/badge.svg)](../../actions/workflows/docs.yaml)

HADES is a small Tiny Tapeout (SKY130, `ttsky26d`, **3×2 tiles**) accelerator for masked binary similarity search. A host loads a
16-bit-instruction program (32 slots) and up to 16 rows of 32 bits into one on-chip TNT `rf_top` register file; the engine then
scans rows (Hamming distance, top-2, threshold bitmap, exact match, OR/AND/popcount reductions) and streams results back over an
8-bit port. See [docs/info.md](docs/info.md) for how to use it.

## Quick start (host view)
1. Reset, wait 16 clocks (program memory is initialised to HALT).
2. Load the program with the byte-serial loader (`uio[4]` LD_STROBE, bytes on `ui[7:0]`, high byte first).
3. Rising edge on `uio[5]` (EXECUTE): the program starts at instruction 0. Another EXECUTE restarts it.
4. WAITBYTE data in through `ui[7:0]` + `uio[3]` (STROBE); EMIT bytes out on `uo[7:0]` while `uio[0]` (READY) is high; `uio[1]` = BUSY, `uio[2]` = HALT.

## Repository layout
| Path | Content |
|---|---|
| `src-veryl/` | **Source of truth**: the RTL, written in [Veryl](https://veryl-lang.org) (0.21) |
| `src/` | Generated SystemVerilog (`veryl build`), the Verilog TT wrapper `tt_um_hades.v`, the `rf_top.v` simulation model, `config.json` |
| `macro/rf_top/` | TNT `rf_top` register-file macro (GDS/LEF/LIB) with provenance notes |
| `sim/` | Canonical RTL regression (`run_all.sh`, `tb.v`, golden workload vectors) |
| `test/` | Tiny Tapeout cocotb tests (RTL and gate level) |
| `docs/` | `info.md` (project datasheet page) |
| `experiments/` | Historical investigations and superseded testbenches (not part of the build) |

## Build and test
```sh
veryl build                # regenerate src/*.sv from src-veryl/ (generated files are committed; CI does not run Veryl)
sim/run_all.sh          # full RTL regression (Icarus Verilog)
cd test && make sim        # Tiny Tapeout cocotb tests, RTL
cd test && make -B GATES=yes   # gate level (needs the hardened netlist as test/gate_level_netlist.v and PDK_ROOT)
```
The GitHub Actions run the Tiny Tapeout flow (`gds`, `precheck`, `gl_test`), `test` (cocotb) and `docs`.

## License
Apache-2.0 (see [LICENSE](LICENSE)). The `rf_top` macro is by Sylvain Munaut / Tiny Tapeout — see [RF Macro](https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_rf_test).
