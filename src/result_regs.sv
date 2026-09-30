// scan_op: 0 = HAMMING 1 = HAMMING2 2 = THRESHOLD 3 = EXACT 4 = R_OR 5 = R_AND 6 = R_POP 7 = R_MAXPOP
// Late predicates (lt, lt2, gt, thresh_ok, exact_hit) gate the enables last, for timing.
module result_regs (
    input  var logic          clk          ,
    input  var logic          rst_n        ,
    input  var logic          rst_init     ,
    input  var logic          upd_en       ,
    input  var logic [3-1:0]  scan_op      ,
    input  var logic [6-1:0]  d            ,
    input  var logic          exact_hit    ,
    input  var logic [32-1:0] masked_row   ,
    input  var logic [4-1:0]  row          ,
    input  var logic [32-1:0] a_in         ,
    output var logic [6-1:0]  min_dist     ,
    output var logic [4-1:0]  min_idx      ,
    output var logic [6-1:0]  min2_dist    ,
    output var logic [4-1:0]  min2_idx     ,
    output var logic          min_valid    ,
    output var logic          threshold_hit,
    output var logic [16-1:0] match        ,
    output var logic [5-1:0]  count_out    ,
    output var logic          a_wr2_en     ,
    output var logic [32-1:0] a_wr2_dat
);
    logic [6-1:0]  min_dist_r     ;
    logic [4-1:0]  min_idx_r      ;
    logic [6-1:0]  min2_dist_r    ;
    logic [4-1:0]  min2_idx_r     ;
    logic          min_valid_r    ;
    logic          threshold_hit_r;
    logic [16-1:0] match_r        ;
    logic [5-1:0]  count_r        ;

    logic op0;
    logic op1;
    logic op2;
    logic op3;
    logic op4;
    logic op5;
    logic op6;
    logic op7;
    logic go ;
    always_comb op0 = (scan_op == 3'd0);
    always_comb op1 = (scan_op == 3'd1);
    always_comb op2 = (scan_op == 3'd2);
    always_comb op3 = (scan_op == 3'd3);
    always_comb op4 = (scan_op == 3'd4);
    always_comb op5 = (scan_op == 3'd5);
    always_comb op6 = (scan_op == 3'd6);
    always_comb op7 = (scan_op == 3'd7);
    always_comb go  = upd_en & ~rst_init;

    logic [16-1:0] match_bit;
    always_comb match_bit = 16'd1 << row;

    logic lt       ;
    logic lt2      ;
    logic gt       ;
    logic thresh_ok;
    always_comb lt        = d < min_dist_r;
    always_comb lt2       = d < min2_dist_r;
    always_comb gt        = d > min_dist_r;
    always_comb thresh_ok = (|a_in[7:6]) | (a_in[5:0] >= d);

    // REDUCE_POP add is a 6-bit late add plus a precomputed (A[31:6] + 1) selected by the carry.
    logic [7-1:0]  lo_sum ;
    logic [26-1:0] hi_inc ;
    logic [26-1:0] pop_hi ;
    logic [32-1:0] pop_sum;
    always_comb lo_sum  = {1'b0, a_in[5:0]} + {1'b0, d};
    always_comb hi_inc  = a_in[31:6] + 26'd1;
    always_comb begin
        if (lo_sum[6]) begin
            pop_hi = hi_inc;
        end else begin
            pop_hi = a_in[31:6];
        end
    end
    always_comb pop_sum = {pop_hi, lo_sum[5:0]};

    always_comb begin
        a_wr2_en  = 1'b0;
        a_wr2_dat = 32'd0;
        if (rst_init) begin
            if (op4) begin
                a_wr2_en  = 1'b1;
                a_wr2_dat = 32'd0;
            end else if (op5) begin
                a_wr2_en  = 1'b1;
                a_wr2_dat = 32'hFFFF_FFFF;
            end else if (op6) begin
                a_wr2_en  = 1'b1;
                a_wr2_dat = 32'd0;
            end
        end else if (upd_en) begin
            if (op4) begin
                a_wr2_en  = 1'b1;
                a_wr2_dat = a_in | masked_row;
            end else if (op5) begin
                a_wr2_en  = 1'b1;
                a_wr2_dat = a_in & masked_row;
            end else if (op6) begin
                a_wr2_en  = 1'b1;
                a_wr2_dat = pop_sum;
            end
        end
    end

    logic init_min_hi;
    logic init_min_lo;
    logic init_min   ;
    logic init_m2    ;
    logic init_mc    ;
    logic init_th    ;
    always_comb init_min_lo = rst_init & (op0 | op1 | op2);
    always_comb init_min_hi = rst_init & op7;
    always_comb init_min    = init_min_lo | init_min_hi;
    always_comb init_m2     = rst_init & op1;
    always_comb init_mc     = rst_init & (op2 | op3);
    always_comb init_th     = rst_init & op2;

    logic min_take   ;
    logic m2_from_min;
    logic m2_from_d  ;
    logic mhit       ;
    logic cnt_inc    ;
    always_comb min_take    = go & (((op0 | op1 | op2) & lt) | (op7 & gt));
    always_comb m2_from_min = go & op1 & lt;
    always_comb m2_from_d   = go & op1 & ~lt & lt2;
    always_comb mhit        = go & ((op2 & thresh_ok) | (op3 & exact_hit));
    always_comb cnt_inc     = mhit & (count_r != 5'd31);

    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            min_dist_r      <= 6'h3F;
            min_idx_r       <= 4'd0;
            min2_dist_r     <= 6'h3F;
            min2_idx_r      <= 4'd0;
            min_valid_r     <= 1'b0;
            threshold_hit_r <= 1'b0;
            match_r         <= 16'd0;
            count_r         <= 5'd0;
        end else begin
            if (init_min) begin
                if (init_min_lo) begin
                    min_dist_r <= 6'h3F;
                end else begin
                    min_dist_r <= 6'd0;
                end
                min_idx_r  <= 4'd0;
            end else if (min_take) begin
                min_dist_r <= d;
                min_idx_r  <= row;
            end
            if (init_m2) begin
                min2_dist_r <= 6'h3F;
                min2_idx_r  <= 4'd0;
            end else if (m2_from_min) begin
                min2_dist_r <= min_dist_r;
                min2_idx_r  <= min_idx_r;
            end else if (m2_from_d) begin
                min2_dist_r <= d;
                min2_idx_r  <= row;
            end
            if (init_min) begin
                min_valid_r <= 1'b0;
            end else if (go & (op0 | op1 | op2 | op7)) begin
                min_valid_r <= 1'b1;
            end
            if (init_th) begin
                threshold_hit_r <= 1'b0;
            end else if (go & op2 & thresh_ok) begin
                threshold_hit_r <= 1'b1;
            end
            if (init_mc) begin
                match_r <= 16'd0;
                count_r <= 5'd0;
            end else if (mhit) begin
                match_r <= match_r | match_bit;
                if (cnt_inc) begin
                    count_r <= count_r + 5'd1;
                end
            end
        end
    end

    always_comb min_dist      = min_dist_r;
    always_comb min_idx       = min_idx_r;
    always_comb min2_dist     = min2_dist_r;
    always_comb min2_idx      = min2_idx_r;
    always_comb min_valid     = min_valid_r;
    always_comb threshold_hit = threshold_hit_r;
    always_comb match         = match_r;
    always_comb count_out     = count_r;
endmodule
//# sourceMappingURL=result_regs.sv.map
