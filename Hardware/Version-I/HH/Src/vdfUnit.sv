module vdfUnit (
    input clk,
    input rst,
    input start,
    input [1:0] tref_mode,
    input [15:0] gate_1,
    input [15:0] gate_2,
    input [15:0] volt,
    input [15:0] conductace,
    output wire signed [17:0] sumFs,
    output wrF,
    output reg done
);
  wire [15:0] F_mul;

  reg signed [15:0] FK, FNa, FL;

  assign sumFs = FK + FNa + FL;

  always @(posedge clk or posedge rst) begin
    if (rst) begin
      FK  <= 16'd1;
      FNa <= 16'd1;
      FL  <= 16'd1;
    end else if (wrF) begin
      if (tref_mode == 2'd0) FK <= F_mul;
      if (tref_mode == 2'd1) FNa <= F_mul;
      if (tref_mode == 2'd2) FL <= F_mul;
    end
  end


  vdfmult DVmult (
      .clk       (clk),
      .rst       (rst),
      .start     (start),
      .gate_1    (gate_1),
      .gate_2    (gate_2),
      .conductace(conductace),
      .volt      (volt),
      .o_mul     (F_mul),
      .wrF       (wrF),
      .done      (done)
  );

endmodule
