// fsm: 0=FETCH 1=SCAN 2=WAIT 3=HALT
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

    output var logic [3-1:0] scan_op  ,
    output var logic [4-1:0] use_xor_o,
    output var logic [4-1:0] emit_src ,
    output var logic         emit_en  ,

    input  var logic         strobe,
    output var logic         wb_en ,
    output var logic [2-1:0] wb_dst, // WAITBYTE destination: 0=Q 1=A 2=MASK
    output var logic [2-1:0] wb_pos, // WAITBYTE byte lane: 0=B0 1=B1 2=B2 3=B3

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
    logic [32-1:0] dreg_r    ;

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
    always_comb in_fetch = ~(fsm[2] | fsm[1] | fsm[0]);
    always_comb in_scan  = ~(fsm[2] | fsm[1]) & fsm[0];
    always_comb in_wait  = ~fsm[2] & fsm[1] & ~fsm[0];
    always_comb in_halt  = ~fsm[2] & fsm[1] & fsm[0];

    logic is_scan    ;
    logic is_ldq     ;
    logic is_lda     ;
    logic is_ldm     ;
    logic is_sta     ;
    logic is_emit    ;
    logic is_waitbyte;
    logic is_branch  ;
    logic is_halt    ;
    logic is_clrmsk  ;
    always_comb is_scan     = in_fetch & (opc == 4'd4);
    always_comb is_ldq      = in_fetch & (opc == 4'd0);
    always_comb is_lda      = in_fetch & (opc == 4'd1);
    always_comb is_ldm      = in_fetch & (opc == 4'd2);
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

    logic scan_last;
    always_comb scan_last = (scan_row_r == scan_end_r);

    logic         sram_rd_en ;
    logic [4-1:0] sram_addr_v;
    always_comb sram_rd_en  = is_scan | (in_scan & ~scan_last);
    always_comb begin
        if (is_scan) begin
            sram_addr_v = fA;
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

    always_ff @ (posedge clk) begin
        dreg_r <= sram_dout;
    end
    always_comb dreg = sram_dout;

    always_comb pc      = pc_r;
    always_comb scan_op = fC[2:0];
    for (genvar i = 0; i < 4; i++) begin :g_ux
        hades_dupff u_ux (
            .clk   (clk         ),
            .rst_n (rst_n       ),
            .en    (is_scan     ),
            .d     (~fC[2]      ),
            .q     (use_xor_o[i])
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

    always_comb q_wr_en  = is_ldq;
    always_comb q_wr_dat = dreg_r;
    always_comb a_wr_en  = is_lda;
    always_comb a_wr_dat = dreg_r;
    always_comb m_wr_en  = is_ldm | is_clrmsk;
    always_comb begin
        if (is_clrmsk) begin
            m_wr_dat = 32'hFFFF_FFFF;
        end else begin
            m_wr_dat = dreg_r;
        end
    end

    // BRANCH target = (PC+1 + {fB,fC}) mod 32
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
            end else if (is_scan) begin
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
        end
    end
    always_comb pc_next = pc_nx;

    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            fsm        <= 3'd0;
            pc_r       <= 5'd0;
            scan_row_r <= 4'd0;
            scan_end_r <= 4'd0;
        end else begin
            pc_r <= pc_nx;
            if (in_fetch) begin
                if (is_halt) begin
                    fsm <= 3'd3;
                end else if (is_scan) begin
                    scan_row_r <= fA;
                    scan_end_r <= scan_end_clamp;
                    fsm        <= 3'd1;
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
                    scan_row_r <= scan_row_r + 4'd1;
                end
            end else if (in_wait) begin
                if (strobe) begin
                    fsm <= 3'd0;
                end
            end
        end
    end
endmodule
//# sourceMappingURL=ctrl.sv.map
