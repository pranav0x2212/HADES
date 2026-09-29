## HADES v1

HADES v1 is a masked Hamming-distance nearest-neighbour / threshold / reduction search engine driven by a 32-instruction, 16-bit program.
16 rows x 32 bits of data and the 32-instruction program share one TinyTapeout register-file macro (TNT `rf_top`, 32 x 32).

### Using the chip
1. Hold `rst_n` low, then release it. Wait at least **16 clocks** (the chip fills program memory with HALT).
2. **Load the program** through the loader: put a byte on `ui[7:0]` and give `uio[4]` (LD_STROBE) a rising edge. Send each 16-bit instruction as
   two bytes, high byte first; instructions go to slots 0, 1, 2, ... Unused slots stay HALT.
3. Give `uio[5]` (EXECUTE) a rising edge. The program starts at instruction 0 about 2 clocks later. Another EXECUTE (running or halted) restarts at instruction 0
   and keeps Q/A/MASK/results/data rows. EXECUTE is ignored during reset/initialisation and while a loader byte pair is incomplete.
4. Read results on `uo[7:0]` when `uio[0]` (READY) is high (EMIT). `uio[1]` = BUSY, `uio[2]` = HALT. For WAITBYTE, put a byte on `ui[7:0]` and raise `uio[3]` (STROBE).

A reset erases the program. Loading a program while it is executing is not supported.

### Pins
| Pin | Direction | Function |
|---|---|---|
| ui[7:0] | in | WAITBYTE data / loader byte |
| uo[7:0] | out | EMIT data (valid with READY) |
| uio[0] / [1] / [2] | out | READY / BUSY / HALT |
| uio[3] | in | STROBE (WAITBYTE data valid) |
| uio[4] | in | LD_STROBE (loader byte valid, rising edge) |
| uio[5] | in | EXECUTE (rising edge) |

### How to test
The cocotb tests in `test/` drive only the chip pins and run at RTL and at gate level (`make sim`, `make -B GATES=yes`).
