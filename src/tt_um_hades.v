`default_nettype none

module tt_um_hades (
`ifdef GL_TEST
    input  wire       VPWR,
    input  wire       VGND,
`endif
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

  wire [31:0] rf_w_data, rf_ra_data, rf_rb_data;
  wire [4:0]  rf_w_addr, rf_ra_addr, rf_rb_addr;
  wire        rf_w_ena;

  reg        ld_q, ph;
  reg [7:0]  hi_r;
  reg [4:0]  slot;
  wire       ld_rise = uio_in[4] & ~ld_q;
  wire       pm_wr_en = ld_rise & ph;

  reg        exec_q;
  wire       exec_req = uio_in[5] & ~exec_q & ~ph & ~ld_rise;

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      ld_q <= 1'b0; ph <= 1'b0; hi_r <= 8'd0; slot <= 5'd0; exec_q <= 1'b0;
    end else begin
      ld_q <= uio_in[4];
      exec_q <= uio_in[5];
      if (ld_rise) begin
        ph <= ~ph;
        if (!ph) hi_r <= ui_in;
        else     slot <= slot + 5'd1;
      end
    end
  end

  hades_top u_core (
      .clk        (clk),
      .clk_n      (~clk),
      .rst_n      (rst_n),
      .ui_in      (ui_in),
      .uio_in     (uio_in),
      .uo_out     (uo_out),
      .uio_out    (uio_out),
      .uio_oe     (uio_oe),
      .rf_w_data  (rf_w_data),
      .rf_w_addr  (rf_w_addr),
      .rf_w_ena   (rf_w_ena),
      .rf_ra_addr (rf_ra_addr),
      .rf_rb_addr (rf_rb_addr),
      .rf_ra_data (rf_ra_data),
      .rf_rb_data (rf_rb_data),
      .pm_wr_en   (pm_wr_en),
      .pm_wr_addr (slot),
      .pm_wr_data ({hi_r, ui_in}),
      .exec_req   (exec_req)
  );

  rf_top i_rf (
`ifdef GL_TEST
      .VDPWR   (VPWR),
      .VGND    (VGND),
`endif
      .w_data  (rf_w_data),
      .w_addr  (rf_w_addr),
      .w_ena   (rf_w_ena),
      .ra_addr (rf_ra_addr),
      .ra_data (rf_ra_data),
      .rb_addr (rf_rb_addr),
      .rb_data (rf_rb_data),
      .clk     (clk)
  );

  wire _unused = &{ena, uio_in[7:6], uio_in[2:0], 1'b0};

endmodule
