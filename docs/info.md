## HADES v0

HADES v0 is a masked Hamming-distance nearest-neighbour search engine. It stores up to 16 32-bit entries in on-chip SRAM and, on command, scans all entries to find the one with the lowest popcount(XOR) distance to a query vector, subject to a bit-mask. It also returns a threshold-match bitmap indicating which entries fall within a given distance.

A full scan over 16 entries completes in exactly 18 clock cycles.

### How it works

The core operates through a byte-serial command interface:

| `uio_in[3:1]` (op) | Action |
|---|---|
| 0 | Shift `ui_in` byte into query register (MSB first, 4 calls = 32-bit word) |
| 1 | Shift `ui_in` byte into mask register |
| 2 | Set threshold from `ui_in[5:0]` |
| 3 | Write current query word to SRAM, post-increment address |
| 4 | Start search |
| 5 | Advance result selector |

A command fires on the rising edge of `uio_in[0]` (strobe), synchronized through a 2-FF stage. `ui_in[7:0]` carries the data byte.

Status outputs on `uio_out`:

| Bit | Signal |
|---|---|
| 7 | `any_hit & done` |
| 6 | `done` |
| 5 | `busy` |

Result outputs on `uo_out` (muxed by `rsel`, advanced with op 5):

| `rsel` | `uo_out` content |
|---|---|
| 0 | `{4'b0, best_idx[3:0]}` — index of nearest neighbour |
| 1 | `{2'b0, best_dist[5:0]}` — distance of nearest neighbour |
| 2 | `hits[7:0]` — threshold-match bitmap, entries 0–7 |
| 3 | `hits[15:8]` — threshold-match bitmap, entries 8–15 |

### SRAM

`sky130_sram_1rw_tiny` — 16 × 32-bit synchronous single-port SRAM. Inputs captured on posedge, read/write executed on negedge. SRAM control is launched from the negedge of `clk` to meet the setup window. The tapeout uses an empty DRC-clean shell GDS (`sky130_sram_1rw_tiny_shell.gds`) at placement time.

### Reset

Active-low, asynchronous assert, synchronous deassert (`rst_n`). A two-FF synchronizer filters `rst` for the negedge-launched SRAM control stage.

### Clocking

50 MHz target. Worst-case setup slack 11.979 ns at max_ss corner (STA black-boxes the SRAM — no `.lib` available).
