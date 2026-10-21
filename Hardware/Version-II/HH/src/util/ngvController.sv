module ngvController (
    input clk,
    input rst,

    input start,
    input [1:0] cal_gv,

    input mul_done,
    output reg mul_start,

    output reg ack,
    output reg save_gv,
    output reg write_gv,

    output reg [1:0] mode,
    output reg ready
);


  typedef enum logic [3:0] {
    IDLE = 4'd0,
    INIT = 4'd1,
    SAVE = 4'd2,
    RWGV = 4'd3,
    ACKN = 4'd4,
    SMUL = 4'd5,
    WMUL = 4'd6,
    DMUL = 4'd7,
    HOLD = 4'd8,
    DONE = 4'd9
  } state_t;
  state_t pstate, nstate;


  always @(posedge clk or posedge rst) begin
    if (rst) pstate <= IDLE;
    else pstate <= nstate;
  end

  always @(*) begin
    case (pstate)
      IDLE: nstate = INIT;
      INIT: nstate = (start) ? RWGV : INIT;
      RWGV: nstate = ACKN;
      ACKN: nstate = SMUL;
      SMUL: nstate = WMUL;
      WMUL: nstate = (mul_done) ? DMUL : WMUL;
      DMUL: nstate = SAVE;
      SAVE: nstate = HOLD;
      HOLD: nstate = DONE;
      DONE: nstate = INIT;
      default: nstate = IDLE;
    endcase
  end



  always @(pstate) begin
    case (pstate)
      IDLE: begin
        write_gv = 1'd0;
        mul_start = 1'd0;
        save_gv = 1'd0;
        ack = 1'd0;
        mode = 2'd3;
        ready = 1'd0;
      end
      INIT: begin
        mode = 2'd3;
      end
      RWGV: begin
        ready = 1'b0;
        save_gv = 1'd1;
        mode = cal_gv;
      end
      ACKN: begin
        save_gv = 1'd0;
        ack = 1'd1;
      end
      SMUL: begin
        ack = 1'd0;
        mul_start = 1'b1;
      end
      WMUL: begin
        mul_start = 1'd0;
      end
      SAVE: begin
        write_gv = 1'd1;
      end
      HOLD: begin
        write_gv = 1'd0;
        ready = 1'b1;
      end
      DONE: begin
        ready = 1'b1;
      end
    endcase
  end
endmodule
