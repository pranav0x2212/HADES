// TT26 pin assignment:
//   uo_out[7:0]  = EMIT data (registered; valid when uio_out[0]=READY)
//   uio_out[0]   = READY   (DUT -> host: byte on uo_out is valid)
//   uio_out[1]   = BUSY    (DUT -> host: executing)
//   uio_out[2]   = HALT    (DUT -> host: halted)
//   uio_in[3]    = STROBE  (host -> DUT: ui_in[7:0] is valid for WAITBYTE)
//   uio_oe       = 8'b0000_0111  (bits 0-2 output; bit 3 input for STROBE)
module hades_top (
    input  var logic         clk    ,
    input  var logic         clk_n  ,
    input  var logic         rst_n  ,
    input  var logic [8-1:0] ui_in  ,
    input  var logic [8-1:0] uio_in ,
    output var logic [8-1:0] uo_out ,
    output var logic [8-1:0] uio_out,
    output var logic [8-1:0] uio_oe ,

    output var logic [32-1:0] rf_w_data ,
    output var logic [5-1:0]  rf_w_addr ,
    output var logic          rf_w_ena  ,
    output var logic [5-1:0]  rf_ra_addr,
    output var logic [5-1:0]  rf_rb_addr,
    input  var logic [32-1:0] rf_ra_data,
    input  var logic [32-1:0] rf_rb_data,
    input  var logic          pm_wr_en  ,
    input  var logic [5-1:0]  pm_wr_addr,
    input  var logic [16-1:0] pm_wr_data,
    input  var logic          exec_req  
);
    logic [5-1:0]  pc              ;
    logic [16-1:0] instr           ;
    logic          rst_init        ;
    logic          upd_en          ;
    logic [4-1:0]  scan_row        ;
    logic [3-1:0]  scan_op         ;
    logic [4-1:0]  use_xor         ;
    logic [32-1:0] dreg            ;
    logic [32-1:0] q               ;
    logic [32-1:0] a               ;
    logic [32-1:0] mask            ;
    logic [6-1:0]  d               ;
    logic          exact_hit       ;
    logic [32-1:0] masked_row      ;
    logic [5-1:0]  min_dist        ;
    logic [4-1:0]  min_idx         ;
    logic [5-1:0]  min2_dist       ;
    logic [4-1:0]  min2_idx        ;
    logic          min_valid       ;
    logic          threshold_hit   ;
    logic [16-1:0] match           ;
    logic [5-1:0]  count_out       ;
    logic [4-1:0]  emit_src        ;
    logic          emit_en         ;
    logic          busy            ;
    logic          halted          ;
    logic          q_wr_en         ;
    logic [32-1:0] q_wr_dat        ;
    logic          a_wr_en         ;
    logic [32-1:0] a_wr_dat        ;
    logic          a_wr2_en        ;
    logic [32-1:0] a_wr2_dat       ;
    logic          m_wr_en         ;
    logic [32-1:0] m_wr_dat        ;
    logic          strobe          ;
    logic          wb_en           ;
    logic [2-1:0]  wb_dst          ;
    logic [2-1:0]  wb_pos          ;
    logic          br_threshold_hit;
    logic          br_min_valid    ;
    logic          br_count_nz     ;
    logic          br_match_nz     ;
    logic          br_a_zero       ;
    logic          q_wr_en_m       ;
    logic [32-1:0] q_wr_dat_m      ;
    logic          a_wr_en_m       ;
    logic [32-1:0] a_wr_dat_m      ;
    logic [4-1:0]  m_wr_en_m       ;
    logic [32-1:0] m_wr_dat_m      ;
    logic [32-1:0] byte_mask       ;
    logic [32-1:0] byte_sft        ;
    logic [4-1:0]  sram_addr       ;
    logic          sram_csb        ;
    logic          sram_web        ;
    logic [32-1:0] sram_din        ;
    logic [5-1:0]  pc_next         ;
    logic          sta_en          ;

    logic [4-1:0]  sw       ;
    logic          init_done;
    logic [16-1:0] lo_buf   ;
    logic [16-1:0] instr_raw;
    logic run    ;
    logic go     ;
    logic rst_n_c; always_comb rst_n_c = rst_n & run;

    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            sw        <= 4'd0;
            init_done <= 1'b0;
        end else if (~init_done) begin
            sw        <= sw + 4'd1;
            if (sw == 4'd15) begin
                init_done <= 1'b1;
            end
        end
    end

    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            run <= 1'b0;
            go  <= 1'b0;
        end else if (exec_req & init_done) begin
            run <= 1'b0;
            go  <= 1'b1;
        end else begin
            go  <= 1'b0;
            if (go) begin
                run <= 1'b1;
            end
        end
    end

    always_ff @ (posedge clk) begin
        if (pm_wr_en & ~pm_wr_addr[0]) begin
            lo_buf <= pm_wr_data;
        end
    end

    always_comb begin
        if (~init_done) begin
            rf_w_ena  = 1'b1;
            rf_w_addr = {1'b1, sw};
            rf_w_data = 32'h8000_8000;
        end else if (pm_wr_en) begin
            rf_w_ena  = 1'b1;
            rf_w_addr = {1'b1, pm_wr_addr[4:1]};
            if (pm_wr_addr[0]) begin
                rf_w_data = {pm_wr_data, lo_buf};
            end else begin
                rf_w_data = {16'h8000, pm_wr_data};
            end
        end else begin
            rf_w_ena  = sta_en;
            rf_w_addr = {1'b0, instr[11:8]};
            rf_w_data = a;
        end
    end

    always_comb rf_ra_addr = {1'b1, pc_next[4:1]};
    always_comb rf_rb_addr = {1'b0, sram_addr};
    always_comb begin
        if (pc[0]) begin
            instr_raw = rf_ra_data[31:16];
        end else begin
            instr_raw = rf_ra_data[15:0];
        end
    end

    always_comb begin
        if (run) begin
            instr = instr_raw;
        end else begin
            instr = {4'h8, instr_raw[11:0]};
        end
    end

    always_comb strobe = uio_in[3];

    always_comb br_threshold_hit = threshold_hit;
    always_comb br_min_valid     = min_valid;
    always_comb begin
        if (count_out == 5'd0) begin
            br_count_nz = 1'b0;
        end else begin
            br_count_nz = 1'b1;
        end
    end
    always_comb begin
        if (match == 16'd0) begin
            br_match_nz = 1'b0;
        end else begin
            br_match_nz = 1'b1;
        end
    end
    always_comb begin
        if (a == 32'd0) begin
            br_a_zero = 1'b1;
        end else begin
            br_a_zero = 1'b0;
        end
    end

    ctrl u_ctrl (
        .clk              (clk             ),
        .clk_n            (clk_n           ),
        .rst_n            (rst_n_c         ),
        .instr            (instr           ),
        .pc               (pc              ),
        .pc_next          (pc_next         ),
        .sta_en           (sta_en          ),
        .rst_init         (rst_init        ),
        .upd_en           (upd_en          ),
        .scan_row         (scan_row        ),
        .scan_op          (scan_op         ),
        .use_xor_o        (use_xor         ),
        .sram_addr        (sram_addr       ),
        .sram_csb         (sram_csb        ),
        .sram_web         (sram_web        ),
        .sram_din         (sram_din        ),
        .dreg             (dreg            ),
        .sram_dout        (rf_rb_data      ),
        .q_wr_en          (q_wr_en         ),
        .q_wr_dat         (q_wr_dat        ),
        .a_wr_en          (a_wr_en         ),
        .a_wr_dat         (a_wr_dat        ),
        .m_wr_en          (m_wr_en         ),
        .m_wr_dat         (m_wr_dat        ),
        .emit_src         (emit_src        ),
        .emit_en          (emit_en         ),
        .strobe           (strobe          ),
        .wb_en            (wb_en           ),
        .wb_dst           (wb_dst          ),
        .wb_pos           (wb_pos          ),
        .br_threshold_hit (br_threshold_hit),
        .br_min_valid     (br_min_valid    ),
        .br_count_nz      (br_count_nz     ),
        .br_match_nz      (br_match_nz     ),
        .br_a_zero        (br_a_zero       ),
        .busy             (busy            ),
        .halted           (halted          )
    );

    always_comb begin
        if (wb_pos == 2'd0) begin
            byte_mask = 32'h000000FF;
            byte_sft  = {24'b0, ui_in};
        end else if (wb_pos == 2'd1) begin
            byte_mask = 32'h0000FF00;
            byte_sft  = {16'b0, ui_in, 8'b0};
        end else if (wb_pos == 2'd2) begin
            byte_mask = 32'h00FF0000;
            byte_sft  = {8'b0, ui_in, 16'b0};
        end else begin
            byte_mask = 32'hFF000000;
            byte_sft  = {ui_in, 24'b0};
        end
    end

    always_comb begin
        if (wb_en & (wb_dst == 2'd0)) begin
            q_wr_en_m  = 1'b1;
            q_wr_dat_m = (q & ~byte_mask) | byte_sft;
        end else begin
            q_wr_en_m  = q_wr_en;
            q_wr_dat_m = q_wr_dat;
        end
    end

    always_comb begin
        if (a_wr2_en) begin
            a_wr_en_m  = 1'b1;
            a_wr_dat_m = a_wr2_dat;
        end else if (wb_en & (wb_dst == 2'd1)) begin
            a_wr_en_m  = 1'b1;
            a_wr_dat_m = (a & ~byte_mask) | byte_sft;
        end else begin
            a_wr_en_m  = a_wr_en;
            a_wr_dat_m = a_wr_dat;
        end
    end

    logic [4-1:0] m_hit;
    always_comb begin
        for (int k = 0; k < 4; k++) begin
            m_hit[k] = wb_en & (wb_dst == 2'd2) & (wb_pos == (2'(k)));
        end
    end
    always_comb begin
        for (int k = 0; k < 4; k++) begin
            m_wr_en_m[k]         = m_hit[k] | m_wr_en;
            if (m_hit[k]) begin
                m_wr_dat_m[8 * k+:8] = ui_in;
            end else begin
                m_wr_dat_m[8 * k+:8] = m_wr_dat[8 * k+:8];
            end
        end
    end

    regs u_regs (
        .clk      (clk       ),
        .rst_n    (rst_n     ),
        .q_wr_en  (q_wr_en_m ),
        .q_wr_dat (q_wr_dat_m),
        .a_wr_en  (a_wr_en_m ),
        .a_wr_dat (a_wr_dat_m),
        .m_wr_en  (m_wr_en_m ),
        .m_wr_dat (m_wr_dat_m),
        .q        (q         ),
        .a        (a         ),
        .mask     (mask      )
    );

    compute u_compute (
        .row_data   (dreg      ),
        .q          (q         ),
        .mask       (mask      ),
        .use_xor    (use_xor   ),
        .d          (d         ),
        .exact_hit  (exact_hit ),
        .masked_row (masked_row)
    );

    result_regs u_result_regs (
        .clk           (clk          ),
        .rst_n         (rst_n        ),
        .rst_init      (rst_init     ),
        .upd_en        (upd_en       ),
        .scan_op       (scan_op      ),
        .d             (d            ),
        .exact_hit     (exact_hit    ),
        .masked_row    (masked_row   ),
        .row           (scan_row     ),
        .a_in          (a            ),
        .min_dist      (min_dist     ),
        .min_idx       (min_idx      ),
        .min2_dist     (min2_dist    ),
        .min2_idx      (min2_idx     ),
        .min_valid     (min_valid    ),
        .threshold_hit (threshold_hit),
        .match         (match        ),
        .count_out     (count_out    ),
        .a_wr2_en      (a_wr2_en     ),
        .a_wr2_dat     (a_wr2_dat    )
    );

    logic [8-1:0] emit_mux;
    always_comb begin
        case (emit_src)
            4'd0   : emit_mux = {4'b0, min_idx};
            4'd1   : emit_mux = {3'b0, min_dist};
            4'd2   : emit_mux = a[7:0];
            4'd3   : emit_mux = a[15:8];
            4'd4   : emit_mux = a[23:16];
            4'd5   : emit_mux = a[31:24];
            4'd6   : emit_mux = match[7:0];
            4'd7   : emit_mux = match[15:8];
            4'd8   : emit_mux = {3'b0, count_out};
            4'd9   : emit_mux = {6'b0, threshold_hit, min_valid};
            4'd10  : emit_mux = {4'b0, min2_idx};
            4'd11  : emit_mux = {3'b0, min2_dist};
            default: emit_mux = 8'hFF;
        endcase
    end

    logic [8-1:0] uo_out_r;
    logic         ready_r ;

    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            uo_out_r <= 8'd0;
            ready_r  <= 1'b0;
        end else begin
            ready_r  <= emit_en;
            if (emit_en) begin
                uo_out_r <= emit_mux;
            end
        end
    end

    always_comb uo_out  = uo_out_r;
    always_comb uio_out = {5'b0, halted, busy, ready_r};
    always_comb uio_oe  = 8'b0000_0111;
endmodule
//# sourceMappingURL=hades_top.sv.map
