`define TWOS_COMP(val) (((~(val)) + 1'b1) & ((1 << (16)) - 1))


module ngvMult (
    input clk,
    input rst,
    input start,
    input [15:0] gate,
    input [15:0] rate,
    output [15:0] o_mul,
    output reg done
);
  reg [15:0] r_mul = 16'd0;
  assign o_mul = r_mul;
  reg [31:0] ext_res;
  reg [15:0] temp_res;
  reg [15:0] res;

  reg [15:0] a = 16'd0;
  reg [15:0] b = 16'd0;

  reg sign = 1'b0;
  reg clamp = 1'b0;

  reg [2:0] IDLE = 3'd0;
  reg [2:0] INIT = 3'd1;
  reg [2:0] PLC1 = 3'd2;
  reg [2:0] CHNG = 3'd3;
  reg [2:0] CALC = 3'd4;
  reg [2:0] MAKE = 3'd5;
  reg [2:0] CONV = 3'd6;
  reg [2:0] DONE = 3'd7;
  reg [2:0] pstate, nstate;

  always @(posedge clk or posedge rst) begin
    if (rst) pstate <= IDLE;
    else pstate <= nstate;
  end

  always @(*) begin
    case (pstate)
      IDLE: nstate = (start) ? INIT : IDLE;
      INIT: nstate = PLC1;
      PLC1: nstate = CALC;
      CALC: nstate = MAKE;
      MAKE: nstate = CHNG;
      CHNG: nstate = CONV;
      CONV: nstate = DONE;
      DONE: nstate = IDLE;
      default: nstate = IDLE;
    endcase
  end

  always @(pstate) begin
    case (pstate)
      IDLE: begin
        done = 1'b0;
      end
      INIT: begin
        sign = gate[15];
        a = (gate[15]) ? `TWOS_COMP(gate) : gate;
        b = rate;
      end
      CALC: begin
        ext_res = (a * b);
      end
      MAKE: begin
        temp_res = (ext_res[30:15]);
        clamp = (temp_res[15] == 1'b1);
      end
      CHNG: begin
        res = (clamp) ? {{1'b0}, {15{1'b1}}} : temp_res;
      end
      CONV: begin
        r_mul = (sign) ? `TWOS_COMP(res) : res;
      end
      DONE: begin
        done = 1'b1;
      end
    endcase
  end
endmodule
