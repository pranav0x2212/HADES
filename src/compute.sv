module compute (
    input  var logic [32-1:0] row_data  ,
    input  var logic [32-1:0] q         ,
    input  var logic [32-1:0] mask      ,
    input  var logic [4-1:0]  use_xor   ,
    output var logic [6-1:0]  d         ,
    output var logic          exact_hit ,
    output var logic [32-1:0] masked_row
);
    logic [32-1:0] x;
    always_comb begin
        for (int k = 0; k < 4; k++) begin
            if (use_xor[k]) begin
                x[8 * k+:8] = (row_data[8 * k+:8] ^ q[8 * k+:8]) & mask[8 * k+:8];
            end else begin
                x[8 * k+:8] = row_data[8 * k+:8] & mask[8 * k+:8];
            end
        end
    end
    always_comb masked_row = x;
    always_comb exact_hit  = ~|x;

    logic s1 ; always_comb s1  = x[0] ^ x[1] ^ x[2];
    logic c1 ; always_comb c1  = (x[0] & x[1]) | (x[0] & x[2]) | (x[1] & x[2]);
    logic s2 ; always_comb s2  = x[3] ^ x[4] ^ x[5];
    logic c2 ; always_comb c2  = (x[3] & x[4]) | (x[3] & x[5]) | (x[4] & x[5]);
    logic s3 ; always_comb s3  = x[6] ^ x[7] ^ x[8];
    logic c3 ; always_comb c3  = (x[6] & x[7]) | (x[6] & x[8]) | (x[7] & x[8]);
    logic s4 ; always_comb s4  = x[9] ^ x[10] ^ x[11];
    logic c4 ; always_comb c4  = (x[9] & x[10]) | (x[9] & x[11]) | (x[10] & x[11]);
    logic s5 ; always_comb s5  = x[12] ^ x[13] ^ x[14];
    logic c5 ; always_comb c5  = (x[12] & x[13]) | (x[12] & x[14]) | (x[13] & x[14]);
    logic s6 ; always_comb s6  = x[15] ^ x[16] ^ x[17];
    logic c6 ; always_comb c6  = (x[15] & x[16]) | (x[15] & x[17]) | (x[16] & x[17]);
    logic s7 ; always_comb s7  = x[18] ^ x[19] ^ x[20];
    logic c7 ; always_comb c7  = (x[18] & x[19]) | (x[18] & x[20]) | (x[19] & x[20]);
    logic s8 ; always_comb s8  = x[21] ^ x[22] ^ x[23];
    logic c8 ; always_comb c8  = (x[21] & x[22]) | (x[21] & x[23]) | (x[22] & x[23]);
    logic s9 ; always_comb s9  = x[24] ^ x[25] ^ x[26];
    logic c9 ; always_comb c9  = (x[24] & x[25]) | (x[24] & x[26]) | (x[25] & x[26]);
    logic s10; always_comb s10 = x[27] ^ x[28] ^ x[29];
    logic c10; always_comb c10 = (x[27] & x[28]) | (x[27] & x[29]) | (x[28] & x[29]);
    logic s11; always_comb s11 = x[30] ^ x[31];
    logic c11; always_comb c11 = x[30] & x[31];
    logic s12; always_comb s12 = s1 ^ s2 ^ s3;
    logic c12; always_comb c12 = (s1 & s2) | (s1 & s3) | (s2 & s3);
    logic s13; always_comb s13 = s4 ^ s5 ^ s6;
    logic c13; always_comb c13 = (s4 & s5) | (s4 & s6) | (s5 & s6);
    logic s14; always_comb s14 = s7 ^ s8 ^ s9;
    logic c14; always_comb c14 = (s7 & s8) | (s7 & s9) | (s8 & s9);
    logic s15; always_comb s15 = s10 ^ s11;
    logic c15; always_comb c15 = s10 & s11;
    logic s16; always_comb s16 = c1 ^ c2 ^ c3;
    logic c16; always_comb c16 = (c1 & c2) | (c1 & c3) | (c2 & c3);
    logic s17; always_comb s17 = c4 ^ c5 ^ c6;
    logic c17; always_comb c17 = (c4 & c5) | (c4 & c6) | (c5 & c6);
    logic s18; always_comb s18 = c7 ^ c8 ^ c9;
    logic c18; always_comb c18 = (c7 & c8) | (c7 & c9) | (c8 & c9);
    logic s19; always_comb s19 = c10 ^ c11;
    logic c19; always_comb c19 = c10 & c11;
    logic s20; always_comb s20 = s12 ^ s13 ^ s14;
    logic c20; always_comb c20 = (s12 & s13) | (s12 & s14) | (s13 & s14);
    logic s21; always_comb s21 = c12 ^ c13 ^ c14;
    logic c21; always_comb c21 = (c12 & c13) | (c12 & c14) | (c13 & c14);
    logic s22; always_comb s22 = c15 ^ s16 ^ s17;
    logic c22; always_comb c22 = (c15 & s16) | (c15 & s17) | (s16 & s17);
    logic s23; always_comb s23 = s18 ^ s19;
    logic c23; always_comb c23 = s18 & s19;
    logic s24; always_comb s24 = c16 ^ c17 ^ c18;
    logic c24; always_comb c24 = (c16 & c17) | (c16 & c18) | (c17 & c18);
    logic s25; always_comb s25 = s20 ^ s15;
    logic c25; always_comb c25 = s20 & s15;
    logic s26; always_comb s26 = c20 ^ s21 ^ s22;
    logic c26; always_comb c26 = (c20 & s21) | (c20 & s22) | (s21 & s22);
    logic s27; always_comb s27 = c21 ^ c22 ^ c23;
    logic c27; always_comb c27 = (c21 & c22) | (c21 & c23) | (c22 & c23);
    logic s28; always_comb s28 = s24 ^ c19;
    logic c28; always_comb c28 = s24 & c19;
    logic s29; always_comb s29 = c25 ^ s26 ^ s23;
    logic c29; always_comb c29 = (c25 & s26) | (c25 & s23) | (s26 & s23);
    logic s30; always_comb s30 = c26 ^ s27 ^ s28;
    logic c30; always_comb c30 = (c26 & s27) | (c26 & s28) | (s27 & s28);
    logic s31; always_comb s31 = c27 ^ c28 ^ c24;
    logic c31; always_comb c31 = (c27 & c28) | (c27 & c24) | (c28 & c24);
    logic s32; always_comb s32 = c29 ^ s30;
    logic c32; always_comb c32 = c29 & s30;
    logic s33; always_comb s33 = c30 ^ s31;
    logic c33; always_comb c33 = c30 & s31;
    logic s34; always_comb s34 = c32 ^ s33;
    logic c34; always_comb c34 = c32 & s33;
    logic s35; always_comb s35 = c33 ^ c31;
    logic c35; always_comb c35 = c33 & c31;
    logic s36; always_comb s36 = c34 ^ s35;
    logic c36; always_comb c36 = c34 & s35;
    logic s37; always_comb s37 = c36 ^ c35;
    logic c37; always_comb c37 = c36 & c35;
    always_comb d   = {s37, s36, s34, s32, s29, s25};
endmodule
