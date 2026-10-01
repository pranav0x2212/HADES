module ctrl (
    input var logic clk  ,
    input var logic clk_n,
    input var logic rst_n,

    input  var logic [16-1:0] instr  ,
    output var logic [5-1:0]  pc     ,
    output var logic [5-1:0]  pc_next,
    output var logic          sta_en ,

    output var logic         rst_init,
    output var logic         upd_en  ,
    output var logic [4-1:0] scan_row,
    output var logic         pair2   ,
    output var logic         ra_sel  ,
    output var logic [4-1:0] ra_row  ,

    input  var logic [16-1:0] match    ,
    output var logic [4-1:0]  sram_addr,
    output var logic          sram_csb ,
    output var logic          sram_web ,
    output var logic [32-1:0] sram_din ,
    output var logic [32-1:0] dreg     ,

    input var logic [32-1:0] sram_dout,

    output var logic          q_wr_en ,
    output var logic [32-1:0] q_wr_dat,
    output var logic          a_wr_en ,
    output var logic [32-1:0] a_wr_dat,
    output var logic          m_wr_en ,
    output var logic [32-1:0] m_wr_dat,

    output var logic [3-1:0] scan_op   ,
    output var logic [4-1:0] use_xor_o ,
    output var logic [4-1:0] use_xor2_o,
    output var logic [4-1:0] emit_src  ,
    output var logic         emit_en   ,

    input  var logic         strobe,
    output var logic         wb_en ,
    output var logic [2-1:0] wb_dst,
    output var logic [2-1:0] wb_pos,

    input var logic br_threshold_hit,
    input var logic br_min_valid    ,
    input var logic br_count_nz     ,
    input var logic br_match_nz     ,
    input var logic br_a_zero       ,

    output var logic busy  ,
    output var logic halted
);
    logic [3-1:0]  fsm       ;
    logic [5-1:0]  pc_r      ;
    logic [4-1:0]  scan_row_r;
    logic [4-1:0]  scan_end_r;
    logic          dual_r    ;
    logic [3-1:0]  scan_op_r ;
    logic          sel_m_r   ;
    logic [16-1:0] sel_r     ;

    logic [4-1:0] opc;
    logic [4-1:0] fA ;
    logic [4-1:0] fB ;
    logic [4-1:0] fC ;
    always_comb opc = instr[15:12];
    always_comb fA  = instr[11:8];
    always_comb fB  = instr[7:4];
    always_comb fC  = instr[3:0];

    logic in_fetch;
    logic in_scan ;
    logic in_wait ;
    logic in_halt ;
    logic in_ld   ;
    always_comb in_fetch = ~(fsm[2] | fsm[1] | fsm[0]);
    always_comb in_scan  = ~(fsm[2] | fsm[1]) & fsm[0];
    always_comb in_wait  = ~fsm[2] & fsm[1] & ~fsm[0];
    always_comb in_halt  = ~fsm[2] & fsm[1] & fsm[0];
    always_comb in_ld    = fsm[2] & ~fsm[1] & ~fsm[0];

    logic is_scan    ;
    logic is_scanm   ;
    logic scan_start ;
    logic dual_issue ;
    logic ld_issue   ;
    logic ld_q       ;
    logic ld_a       ;
    logic ld_m       ;
    logic is_sta     ;
    logic is_emit    ;
    logic is_waitbyte;
    logic is_branch  ;
    logic is_halt    ;
    logic is_clrmsk  ;
    always_comb is_scan     = in_fetch & ((opc == 4'd4) | (opc == 4'd10) | (opc == 4'd11));
    always_comb is_scanm    = in_fetch & (opc == 4'd11);
    always_comb dual_issue  = in_fetch & (opc == 4'd10) & ((fC[2:0] == 3'd3) | (fC[2:0] == 3'd4) | (fC[2:0] == 3'd5));
    always_comb ld_issue    = in_fetch & ((opc == 4'd0) | (opc == 4'd1) | (opc == 4'd2));
    always_comb ld_q        = in_ld & (opc == 4'd0);
    always_comb ld_a        = in_ld & (opc == 4'd1);
    always_comb ld_m        = in_ld & (opc == 4'd2);
    always_comb is_sta      = in_fetch & (opc == 4'd3);
    always_comb is_emit     = in_fetch & (opc == 4'd6);
    always_comb is_waitbyte = in_fetch & (opc == 4'd5);
    always_comb is_branch   = in_fetch & (opc == 4'd7);
    always_comb is_halt     = in_fetch & (opc == 4'd8);
    always_comb is_clrmsk   = in_fetch & (opc == 4'd9);

    logic [5-1:0] scan_end_raw  ;
    logic [4-1:0] scan_end_clamp;
    always_comb scan_end_raw   = {1'b0, fA} + {1'b0, fB};
    always_comb begin
        if (scan_end_raw[4]) begin
            scan_end_clamp = 4'd15;
        end else begin
            scan_end_clamp = scan_end_raw[3:0];
        end
    end

    logic [16-1:0] ffs_in ;
    logic [16-1:0] ffs_pfx;
    logic [16-1:0] ffs_low;
    logic          ffs_any;
    logic [4-1:0]  sel_row;
    logic          sel_use;
    always_comb begin
        if (in_fetch) begin
            ffs_in = match;
        end else begin
            ffs_in = sel_r;
        end
    end
    always_comb begin
        ffs_pfx[0] = 1'b0;
        for (int i = 1; i < 16; i++) begin
            ffs_pfx[i] = ffs_pfx[i - 1] | ffs_in[i - 1];
        end
    end
    always_comb ffs_low    = ffs_in & ~ffs_pfx;
    always_comb ffs_any    = ffs_pfx[15] | ffs_in[15];
    always_comb sel_row    = {
        |(ffs_low & 16'hFF00), |(ffs_low & 16'hF0F0), |(ffs_low & 16'hCCCC), |(ffs_low & 16'hAAAA)
    };
    always_comb sel_use    = is_scanm | (in_scan & sel_m_r);
    always_comb scan_start = is_scan & (~is_scanm | ffs_any);

    logic scan_last;
    always_comb begin
        if (sel_m_r) begin
            scan_last = ~ffs_any;
        end else begin
            scan_last = (scan_row_r == scan_end_r) | (dual_r & (scan_row_r + 4'd1 == scan_end_r));
        end
    end
    always_comb pair2  = in_scan & dual_r & (scan_row_r != scan_end_r);
    always_comb ra_sel = dual_issue | (in_scan & dual_r & ~scan_last);
    always_comb begin
        if (dual_issue) begin
            ra_row = fA + 4'd1;
        end else begin
            ra_row = scan_row_r + 4'd3;
        end
    end

    logic         sram_rd_en ;
    logic [4-1:0] sram_addr_v;
    always_comb sram_rd_en  = scan_start | ld_issue | (in_scan & ~scan_last);
    always_comb begin
        if (sel_use) begin
            sram_addr_v = sel_row;
        end else if (is_scan | ld_issue) begin
            sram_addr_v = fA;
        end else if (dual_r) begin
            sram_addr_v = scan_row_r + 4'd2;
        end else begin
            sram_addr_v = scan_row_r + 4'd1;
        end
    end
    always_comb begin
        if (sram_rd_en) begin
            sram_addr = sram_addr_v;
        end else begin
            sram_addr = 4'd0;
        end
    end
    always_comb sram_csb = ~sram_rd_en;
    always_comb sram_web = 1'b1;
    always_comb sram_din = 32'd0;

    always_comb dreg = sram_dout;

    always_comb pc = pc_r;
    always_comb begin
        if (in_fetch) begin
            scan_op = fC[2:0];
        end else begin
            scan_op = scan_op_r;
        end
    end
    for (genvar i = 0; i < 4; i++) begin :g_ux
        hades_dupff u_ux (
            .clk   (clk         ),
            .rst_n (rst_n       ),
            .en    (is_scan     ),
            .d     (~fC[2]      ),
            .q     (use_xor_o[i])
        );
    end
    for (genvar i = 0; i < 4; i++) begin :g_ux2
        hades_dupff u_ux2 (
            .clk   (clk          ),
            .rst_n (rst_n        ),
            .en    (is_scan      ),
            .d     (~fC[2]       ),
            .q     (use_xor2_o[i])
        );
    end
    always_comb sta_en   = is_sta;
    always_comb rst_init = is_scan & ~fC[3];
    always_comb upd_en   = in_scan;
    always_comb scan_row = scan_row_r;
    always_comb emit_src = fA;
    always_comb emit_en  = is_emit;
    always_comb busy     = ~in_fetch & ~in_halt;
    always_comb halted   = in_halt;

    always_comb wb_en  = (is_waitbyte | in_wait) & strobe;
    always_comb wb_dst = fA[3:2];
    always_comb wb_pos = fA[1:0];

    always_comb q_wr_en  = ld_q;
    always_comb q_wr_dat = dreg;
    always_comb a_wr_en  = ld_a;
    always_comb a_wr_dat = dreg;
    always_comb m_wr_en  = ld_m | is_clrmsk;
    always_comb begin
        if (is_clrmsk) begin
            m_wr_dat = 32'hFFFF_FFFF;
        end else begin
            m_wr_dat = dreg;
        end
    end

    logic [8-1:0] off8        ;
    logic [5-1:0] b_target    ;
    logic         branch_taken;
    always_comb off8         = {fB, fC};
    always_comb b_target     = pc_r + 5'd1 + off8[4:0];
    always_comb begin
        case (fA)
            4'd0   : branch_taken = 1'b1;
            4'd1   : branch_taken = br_threshold_hit;
            4'd2   : branch_taken = ~br_threshold_hit;
            4'd3   : branch_taken = br_min_valid;
            4'd4   : branch_taken = br_count_nz;
            4'd5   : branch_taken = br_match_nz;
            4'd6   : branch_taken = br_a_zero;
            4'd7   : branch_taken = ~br_a_zero;
            default: branch_taken = 1'b0;
        endcase
    end

    logic [5-1:0] pc_nx;
    always_comb begin
        pc_nx = pc_r;
        if (in_fetch) begin
            if (is_halt) begin
                pc_nx = pc_r;
            end else if (scan_start | ld_issue) begin
                pc_nx = pc_r;
            end else if (is_waitbyte) begin
                if (strobe) begin
                    pc_nx = pc_r + 5'd1;
                end
            end else if (is_branch) begin
                if (branch_taken) begin
                    pc_nx = b_target;
                end else begin
                    pc_nx = pc_r + 5'd1;
                end
            end else begin
                pc_nx = pc_r + 5'd1;
            end
        end else if (in_scan) begin
            if (scan_last) begin
                pc_nx = pc_r + 5'd1;
            end
        end else if (in_wait) begin
            if (strobe) begin
                pc_nx = pc_r + 5'd1;
            end
        end else if (in_ld) begin
            pc_nx = pc_r + 5'd1;
        end
    end
    always_comb pc_next = pc_nx;

    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            fsm        <= 3'd0;
            pc_r       <= 5'd0;
            scan_row_r <= 4'd0;
            scan_end_r <= 4'd0;
            dual_r     <= 1'b0;
            scan_op_r  <= 3'd0;
            sel_m_r    <= 1'b0;
            sel_r      <= 16'd0;
        end else begin
            sel_r <= ffs_in & ffs_pfx;
            pc_r  <= pc_nx;
            if (in_fetch) begin
                if (is_halt) begin
                    fsm <= 3'd3;
                end else if (scan_start) begin
                    if (is_scanm) begin
                        scan_row_r <= sel_row;
                    end else begin
                        scan_row_r <= fA;
                    end
                    scan_end_r <= scan_end_clamp;
                    dual_r     <= dual_issue;
                    sel_m_r    <= is_scanm;
                    scan_op_r  <= fC[2:0];
                    fsm        <= 3'd1;
                end else if (ld_issue) begin
                    fsm <= 3'd4;
                end else if (is_waitbyte) begin
                    if (strobe) begin
                    end else begin
                        fsm <= 3'd2;
                    end
                end else if (is_branch) begin
                    if (branch_taken) begin
                    end else begin
                    end
                end else begin
                end
            end else if (in_scan) begin
                if (scan_last) begin
                    fsm <= 3'd0;
                end else begin
                    if (sel_m_r) begin
                        scan_row_r <= sel_row;
                    end else if (dual_r) begin
                        scan_row_r <= scan_row_r + 4'd2;
                    end else begin
                        scan_row_r <= scan_row_r + 4'd1;
                    end
                end
            end else if (in_wait) begin
                if (strobe) begin
                    fsm <= 3'd0;
                end
            end else if (in_ld) begin
                fsm <= 3'd0;
            end
        end
    end
endmodule
