module ivmux #(
    parameter WIDTH = 16
) (
    input [WIDTH-1:0] i_i,
    input [WIDTH-1:0] i_ii,
    input [WIDTH-1:0] i_iii,
    input [WIDTH-1:0] i_iv,
    input [1:0] sel,
    output [WIDTH-1:0] o_m
);
  assign o_m = sel[1] ? (sel[0] ? i_iv : i_iii) : (sel[0] ? i_ii : i_i);
endmodule

module IImux #(
    parameter WIDTH = 16
) (
    input [WIDTH-1:0] i_i,
    input [WIDTH-1:0] i_ii,
    input [1:0] sel,
    output [WIDTH-1:0] o_m
);
  assign o_m = (sel == 2'd0) ? i_i : (sel == 2'd1) ? i_ii : {{2'd1}, {14'd0}};
endmodule


module IIImux #(
    parameter WIDTH = 16
) (
    input [WIDTH-1:0] i_i,
    input [WIDTH-1:0] i_ii,
    input [WIDTH-1:0] i_iii,
    input [1:0] sel,
    output [WIDTH-1:0] o_m
);
  assign o_m = (sel == 2'd0) ? i_i : (sel == 2'd1) ? i_ii : (sel == 2'd2) ? i_iii : 16'd1;
endmodule

module voltMux #(
    parameter WIDTH = 16
) (
    input [WIDTH-1:0] volt,
    input [1:0] sel,
    output [WIDTH-1:0] v_m
);
  assign v_m = sel[1] ? (sel[0] ? (volt - {{9'd0},{7'd0}}) :(volt - {{9'd10},{1'd1},{6'd0}})) :
                        (sel[0] ? (volt - {{9'd120},{7'd0}}) :(volt + {{9'd12},{7'd0}}));
endmodule

