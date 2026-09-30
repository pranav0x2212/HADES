// keep_hierarchy stops synthesis merging the four use_xor copies back into one high-fanout flop.
(* keep_hierarchy *)
module hades_dupff (
    input  var logic clk  ,
    input  var logic rst_n,
    input  var logic en   ,
    input  var logic d    ,
    output var logic q
);
    always_ff @ (posedge clk, negedge rst_n) begin
        if (!rst_n) begin
            q <= 1'b1;
        end else if (en) begin
            q <= d;
        end
    end
endmodule
//# sourceMappingURL=hades_dupff.sv.map
