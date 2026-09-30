# HADES v1 — processing-near-memory Hamming search engine

[![gds](../../workflows/gds/badge.svg)](../../actions/workflows/gds.yaml) [![test](../../workflows/test/badge.svg)](../../actions/workflows/test.yaml) [![docs](../../workflows/docs/badge.svg)](../../actions/workflows/docs.yaml)

HADES is a small processing-near-memory (PNM) engine for masked binary similarity search, built for Tiny Tapeout (SKY130, `ttsky26d`, 3×2 tiles).
The data rows sit in an on-chip register file and the compute logic next to it scans them in place, so only results leave the chip. A host loads a
16-bit-instruction program (32 slots) and up to 16 rows of 32 bits; the engine then computes Hamming distance (top-2, threshold bitmap, exact match)
and OR/AND/popcount reductions over the rows and streams the results back over an 8-bit port.

See [docs/info.md](docs/info.md) for how to use it.

Rows are written by a program (4 `WAITBYTE` + `STA row`). Known limitation: `LDQ`/`LDA`/`LDM` are not implemented (the row operand is ignored), so Q/A/MASK can only be set via `WAITBYTE`.

The RTL is written in [Veryl](https://veryl-lang.org) (`src-veryl/`). Run `veryl build` after editing it: the generated `src/*.sv` is committed and CI does not run Veryl.

## Tests
```sh
cd test && make sim            # RTL
cd test && make -B GATES=yes   # gate level; needs test/gate_level_netlist.v (hardened netlist) and PDK_ROOT
```

## License
Apache-2.0 (see [LICENSE](LICENSE)). The `rf_top` macro is by Sylvain Munaut / Tiny Tapeout — see [RF Macro](https://tinytapeout.com/chips/ttsky25a/tt_um_tnt_rf_test).
