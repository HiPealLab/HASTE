`define TWOS_16(val) (((~(val)) + 1'b1) & ((1 << (16)) - 1))
`define TWOS_32(val) (((~(val)) + 1'b1) & ((1 << (32)) - 1))

module leak (
    input clk,
    input rst,
    input start,
    input [31:0] volt,
    input [15:0] conductace,
    output reg [31:0] result,
    output reg done
);


  reg [47:0] ext_res;

  // volt
  reg [31:0] v;

  // conductance
  reg [15:0] c;

  reg sign = 1'b0;

  reg [3:0] IDLE = 4'd0;
  reg [3:0] INIT = 4'd1;
  reg [3:0] MAKE = 4'd2;
  reg [3:0] CONV = 4'd3;
  reg [3:0] DONE = 4'd4;
  reg [3:0] pstate, nstate;

  always @(posedge clk or posedge rst) begin
    if (rst) pstate <= IDLE;
    else pstate <= nstate;
  end

  always_comb begin
    case (pstate)
      IDLE: nstate = (start) ? INIT : IDLE;
      INIT: nstate = MAKE;
      MAKE: nstate = CONV;
      CONV: nstate = DONE;
      DONE: nstate = IDLE;
      default: nstate = IDLE;
    endcase
  end

  always @(posedge clk) begin
    case (pstate)
      IDLE: begin
        done = 1'b0;
      end
      INIT: begin
        sign = volt[31] ^ conductace[15];
        done = 1'b0;
        v = (volt[31]) ? `TWOS_32(volt) : volt;
        c = (conductace[15]) ? `TWOS_16(conductace) : conductace;
      end
      MAKE: begin
        ext_res = v * c;
      end
      CONV: begin
        result = (sign) ? `TWOS_32(ext_res[39:8]) : ext_res[39:8];
      end
      DONE: begin
        done = 1'b1;
      end
    endcase
  end

endmodule
