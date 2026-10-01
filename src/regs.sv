module regs (
    input  var logic          clk     ,
    input  var logic          rst_n   ,
    input  var logic          q_wr_en ,
    input  var logic [32-1:0] q_wr_dat,
    input  var logic          a_wr_en ,
    input  var logic [32-1:0] a_wr_dat,
    input  var logic [4-1:0]  m_wr_en ,
    input  var logic [32-1:0] m_wr_dat,
    output var logic [32-1:0] q       ,
    output var logic [32-1:0] a       ,
    output var logic [32-1:0] mask
);
    logic [32-1:0] q_r   ;
    logic [32-1:0] a_r   ;
    logic [32-1:0] mask_r;

    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            mask_r <= 32'hFFFF_FFFF;
        end else begin
            for (int k = 0; k < 4; k++) begin
                if (m_wr_en[k]) begin
                    mask_r[8 * k+:8] <= m_wr_dat[8 * k+:8];
                end
            end
        end
    end

    always_ff @ (posedge clk) begin
        if (q_wr_en) begin
            q_r <= q_wr_dat;
        end
        if (a_wr_en) begin
            a_r <= a_wr_dat;
        end
    end

    always_comb q    = q_r;
    always_comb a    = a_r;
    always_comb mask = mask_r;
endmodule
