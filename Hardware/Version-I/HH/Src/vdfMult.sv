`define TWOS_COMP(val) (((~(val)) + 1'b1) & ((1 << (16)) - 1))
module vdfmult (
    input clk,
    input rst,
    input start,
    input [15:0] gate_1,
    input [15:0] gate_2,
    input [15:0] volt,
    input [15:0] conductace,
    output reg [15:0] o_mul,
    output reg wrF,
    output reg done
);

  reg [31:0] ext_res;
  reg [15:0] temp_res;
  reg [15:0] res;

  // volt
  reg [15:0] a;

  // first gate
  reg [15:0] b;

  // second gate
  reg [15:0] c;

  // conductance
  reg [15:0] d;

  reg sign = 1'b0;
  reg clamp = 1'b0;

  reg [3:0] IDLE = 4'd0;
  reg [3:0] INIT = 4'd1;
  reg [3:0] GTV1 = 4'd2;
  reg [3:0] GTV1R = 4'd3;
  reg [3:0] GTV2 = 4'd4;
  reg [3:0] GTV2R = 4'd5;
  reg [3:0] GTVC = 4'd6;
  reg [3:0] GTVCR = 4'd7;
  reg [3:0] VCG3 = 4'd8;
  reg [3:0] VCG3R = 4'd9;
  reg [3:0] VCG4 = 4'd10;
  reg [3:0] VCG4R = 4'd11;
  reg [3:0] MAKE = 4'd12;
  reg [3:0] CHNG = 4'd13;
  reg [3:0] CONV = 4'd14;
  reg [3:0] DONE = 4'd15;
  reg [3:0] pstate, nstate;

  always @(posedge clk or posedge rst) begin
    if (rst) pstate <= IDLE;
    else pstate <= nstate;
  end

  always @(*) begin
    case (pstate)
      IDLE: nstate = (start) ? INIT : IDLE;
      INIT: nstate = GTV1;
      GTV1: nstate = GTV1R;
      GTV1R: nstate = GTV2;
      GTV2: nstate = GTV2R;
      GTV2R: nstate = GTVC;
      GTVC: nstate = GTVCR;
      GTVCR: nstate = VCG3;
      VCG3: nstate = VCG3R;
      VCG3R: nstate = VCG4;
      VCG4: nstate = VCG4R;
      VCG4R: nstate = MAKE;
      MAKE: nstate = CHNG;
      CHNG: nstate = CONV;
      CONV: nstate = DONE;
      DONE: nstate = IDLE;
      default: nstate = IDLE;
    endcase
  end

  always @(posedge clk) begin
    case (pstate)
      IDLE: begin
        wrF  = 1'b0;
        done = 1'b0;
      end
      INIT: begin
        done = 1'b0;
        sign = gate_1[15] ^ gate_2[15] ^ volt[15];
        a = (volt[15]) ? `TWOS_COMP(volt) : volt;
        b = (gate_1[15]) ? `TWOS_COMP(gate_1) : gate_1;
        c = (gate_2[15]) ? `TWOS_COMP(gate_2) : gate_2;
        d = (conductace[15]) ? `TWOS_COMP(conductace) : conductace;
      end
      GTV1: begin
        ext_res = (a * b);
      end
      GTV1R: begin
        temp_res = ext_res[28:13];
      end
      GTV2: begin
        ext_res = (temp_res * b);
      end
      GTV2R: begin
        temp_res = ext_res[29:14];
      end
      GTVC: begin
        ext_res = (temp_res * d);
      end
      GTVCR: begin
        temp_res = ext_res[30:15];
      end
      VCG3: begin
        ext_res = (temp_res * b);
      end
      VCG3R: begin
        temp_res = ext_res[29:14];
      end
      VCG4: begin
        ext_res = (temp_res * c);
      end
      VCG4R: begin
        temp_res = ext_res[30:15];
      end
      MAKE: begin
        clamp = ((temp_res[15] == 1'b1));
      end
      CHNG: begin
        res = (clamp) ? {{1'b0}, {15{1'b1}}} : temp_res;
      end
      CONV: begin
        o_mul = (sign) ? `TWOS_COMP(res) : res;
      end
      DONE: begin
        wrF  = 1'b1;
        done = 1'b1;
      end
    endcase
  end

endmodule
