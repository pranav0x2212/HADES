module hades_v0_core (
    input  var logic          clk      ,
    input  var logic          clk_n    ,
    input  var logic          rst_n    ,
    input  var logic [8-1:0]  ui_in    ,
    input  var logic [8-1:0]  uio_in   ,
    output var logic [8-1:0]  uo_out   ,
    output var logic [8-1:0]  uio_out  ,
    output var logic [8-1:0]  uio_oe   ,
    output var logic [4-1:0]  sram_addr,
    output var logic          sram_csb ,
    output var logic          sram_web ,
    output var logic [32-1:0] sram_din ,
    input  var logic [32-1:0] sram_dout
);
    logic r1;
    logic r2;
    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            r1 <= 0;
            r2 <= 0;
        end else begin
            r1 <= 1;
            r2 <= r1;
        end
    end
    logic rst;
    always_comb rst = ~r2;

    logic s1;
    logic s2;
    logic s3;
    always_ff @ (posedge clk) begin
        s1 <= uio_in[0];
        s2 <= s1;
        s3 <= s2;
    end
    logic         pulse;
    logic [3-1:0] op   ;
    always_comb pulse = s2 & ~s3;
    always_comb op    = uio_in[3:1];

    logic         busy  ;
    logic         done  ;
    logic         wr_req;
    logic [5-1:0] cnt   ;
    logic [2-1:0] rsel  ;

    logic op_v    ;
    logic do_shq  ;
    logic do_shm  ;
    logic do_thr  ;
    logic do_wr   ;
    logic do_run  ;
    logic do_rdout;

    always_comb op_v     = pulse & ~busy;
    always_comb do_shq   = op_v & (op == 3'd0);
    always_comb do_shm   = op_v & (op == 3'd1);
    always_comb do_thr   = op_v & (op == 3'd2);
    always_comb do_wr    = op_v & (op == 3'd3);
    always_comb do_run   = op_v & (op == 3'd4);
    always_comb do_rdout = op_v & (op == 3'd5);

    logic [32-1:0] q  ;
    logic [32-1:0] m  ;
    logic [6-1:0]  thr;
    always_ff @ (posedge clk) begin
        if (do_shq) begin
            q   <= {q[23:0], ui_in};
        end
        if (do_shm) begin
            m   <= {m[23:0], ui_in};
        end
        if (do_thr) begin
            thr <= ui_in[5:0];
        end
    end
    always_comb sram_din = q;

    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            busy   <= 0;
            done   <= 0;
            wr_req <= 0;
            cnt    <= 0;
            rsel   <= 0;
        end else begin
            wr_req <= do_wr;
            if (wr_req) begin
                cnt    <= {1'b0, cnt[3:0] + 4'd1};
            end
            if (do_run) begin
                busy <= 1;
                done <= 0;
                cnt  <= 0;
                rsel <= 0;
            end else if (busy) begin
                if (cnt == 5'd17) begin
                    busy <= 0;
                    done <= 1;
                    cnt  <= 0;
                end else begin
                    cnt <= cnt + 5'd1;
                end
            end
            if (do_rdout) begin
                rsel <= rsel + 2'd1;
            end
        end
    end

    logic [4-1:0] n_addr;
    logic         n_csb ;
    logic         n_web ;
    always_ff @ (negedge clk_n) begin
        n_addr <= cnt[3:0];
        if (rst) begin
            n_csb <= 1;
            n_web <= 1;
        end else begin
            n_csb <= ~(wr_req | (busy & ~cnt[4]));
            n_web <= ~wr_req;
        end
    end
    always_comb sram_addr = n_addr;
    always_comb sram_csb  = n_csb;
    always_comb sram_web  = n_web;

    logic [32-1:0] dreg;
    always_ff @ (posedge clk) begin
        dreg <= sram_dout;
    end

    logic [32-1:0] x;
    always_comb x = (dreg ^ q) & m;

    logic [2-1:0] l1 [16];
    logic [3-1:0] l2 [8] ;
    logic [4-1:0] l3 [4] ;
    logic [5-1:0] l4 [2] ;
    logic [6-1:0] d      ;

    always_comb l1[0]  = {1'b0, x[1]} + {1'b0, x[0]};
    always_comb l1[1]  = {1'b0, x[3]} + {1'b0, x[2]};
    always_comb l1[2]  = {1'b0, x[5]} + {1'b0, x[4]};
    always_comb l1[3]  = {1'b0, x[7]} + {1'b0, x[6]};
    always_comb l1[4]  = {1'b0, x[9]} + {1'b0, x[8]};
    always_comb l1[5]  = {1'b0, x[11]} + {1'b0, x[10]};
    always_comb l1[6]  = {1'b0, x[13]} + {1'b0, x[12]};
    always_comb l1[7]  = {1'b0, x[15]} + {1'b0, x[14]};
    always_comb l1[8]  = {1'b0, x[17]} + {1'b0, x[16]};
    always_comb l1[9]  = {1'b0, x[19]} + {1'b0, x[18]};
    always_comb l1[10] = {1'b0, x[21]} + {1'b0, x[20]};
    always_comb l1[11] = {1'b0, x[23]} + {1'b0, x[22]};
    always_comb l1[12] = {1'b0, x[25]} + {1'b0, x[24]};
    always_comb l1[13] = {1'b0, x[27]} + {1'b0, x[26]};
    always_comb l1[14] = {1'b0, x[29]} + {1'b0, x[28]};
    always_comb l1[15] = {1'b0, x[31]} + {1'b0, x[30]};

    always_comb l2[0] = {1'b0, l1[1]} + {1'b0, l1[0]};
    always_comb l2[1] = {1'b0, l1[3]} + {1'b0, l1[2]};
    always_comb l2[2] = {1'b0, l1[5]} + {1'b0, l1[4]};
    always_comb l2[3] = {1'b0, l1[7]} + {1'b0, l1[6]};
    always_comb l2[4] = {1'b0, l1[9]} + {1'b0, l1[8]};
    always_comb l2[5] = {1'b0, l1[11]} + {1'b0, l1[10]};
    always_comb l2[6] = {1'b0, l1[13]} + {1'b0, l1[12]};
    always_comb l2[7] = {1'b0, l1[15]} + {1'b0, l1[14]};

    always_comb l3[0] = {1'b0, l2[1]} + {1'b0, l2[0]};
    always_comb l3[1] = {1'b0, l2[3]} + {1'b0, l2[2]};
    always_comb l3[2] = {1'b0, l2[5]} + {1'b0, l2[4]};
    always_comb l3[3] = {1'b0, l2[7]} + {1'b0, l2[6]};

    always_comb l4[0] = {1'b0, l3[1]} + {1'b0, l3[0]};
    always_comb l4[1] = {1'b0, l3[3]} + {1'b0, l3[2]};

    always_comb d = {1'b0, l4[1]} + {1'b0, l4[0]};

    logic [6-1:0]  best_dist;
    logic [4-1:0]  best_idx ;
    logic [16-1:0] hits     ;
    logic          any_hit  ;

    logic         cmp_v;
    logic [4-1:0] idx  ;
    logic         lt   ;
    logic         hit  ;

    always_comb cmp_v = busy & (cnt[4] | cnt[3] | cnt[2] | cnt[1]);
    always_comb idx   = cnt[3:0] - 4'd2;
    always_comb lt    = ~(d >= best_dist);
    always_comb hit   = d <= thr;

    always_ff @ (posedge clk) begin
        if (do_run) begin
            best_dist <= 6'd63;
            any_hit   <= 0;
        end else if (cmp_v) begin
            if (lt) begin
                best_dist <= d;
                best_idx  <= idx;
            end
            hits      <= {hit, hits[15:1]};
            if (hit) begin
                any_hit   <= 1;
            end
        end
    end

    logic [8-1:0] res;
    always_comb begin
        case (rsel)
            2'd0   : res = {4'b0, best_idx};
            2'd1   : res = {2'b0, best_dist};
            2'd2   : res = hits[7:0];
            default: res = hits[15:8];
        endcase
    end
    always_comb uo_out  = res;
    always_comb uio_out = {any_hit & done, done, busy, 5'b0};
    always_comb uio_oe  = 8'b11100000;
endmodule