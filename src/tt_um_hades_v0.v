`default_nettype none

module tt_um_hades_v0 (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  wire [3:0]  sram_addr;
  wire        sram_csb;
  wire        sram_web;
  wire [31:0] sram_din;
  wire [31:0] sram_dout;

  hades_v0_core core (
      .clk      (clk),
      .clk_n    (clk),
      .rst_n    (rst_n),
      .ui_in    (ui_in),
      .uio_in   (uio_in),
      .uo_out   (uo_out),
      .uio_out  (uio_out),
      .uio_oe   (uio_oe),
      .sram_addr(sram_addr),
      .sram_csb (sram_csb),
      .sram_web (sram_web),
      .sram_din (sram_din),
      .sram_dout(sram_dout)
  );

  sky130_sram_1rw_tiny SRAM (
      .clk0  (clk),
      .csb0  (sram_csb),
      .web0  (sram_web),
      .wmask0(4'b1111),
      .addr0 (sram_addr),
      .din0  (sram_din),
      .dout0 (sram_dout)
  );

  wire _unused = &{ena, 1'b0};

endmodule
