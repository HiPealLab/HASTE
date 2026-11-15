// HASTE revision 2 -- quantized 8-bit ANN baseline core (synthesisable).
//
// Same-device baseline for the SNN cores: same weight memory
// (syn.mem, int8, addr = neuron*FANIN + slot, the image used by the SNN
// builds), same time-multiplexed style (one MAC shared by all neurons),
// same op/ready/done interface.  Integer-only inference (Jacob et al. 2018):
//   acc_i  = sum_j w[i,j] * a[j]              (int8 x uint8, 32-bit acc)
//   hidden : a'_i = clamp((acc_i * RQ_M + 2^(RQ_SH-1)) >>> RQ_SH, 0, 255)
//            (ReLU + requantisation; acc <= 0 gives 0)
//   output : prediction = argmax_i acc_i (lowest index on ties)
// Operations (ready high in IDLE, done pulses at the end of each op):
//   OP_LOAD  (arg = uint8 input value): write the next input, auto-increment
//   OP_RUN   : evaluate all layers; out_valid/out_idx/out_score stream the
//              output-layer scores, pred holds the argmax after done
//   OP_CLEAR : reset the input pointer
// Cycles: LOAD/CLEAR 2 each (incl. FIN), RUN = 2 + sum_l size_l*(fanin_l+3) (hidden)
//         / (fanin_l+2) (output).  Layer table = compile-time constants
//         (ann_params.svh), never $readmemh (Vivado 2022.2 layer-table bug).
module ann_q8 #(
    parameter string SYN_FILE = "syn.mem"
) (
    input  logic        clk,
    input  logic        rst,
    input  logic        op_valid,
    input  logic [1:0]  op,
    input  logic [7:0]  op_arg,
    output logic        ready,
    output logic        done,
    output logic        out_valid,
    output logic [7:0]  out_idx,
    output logic signed [31:0] out_score,
    output logic [7:0]  pred
);
`include "ann_params.svh"
  // from ann_params.svh: N_IN, N_NEU, N_LAYERS, FANIN, ABUF, L_START, L_SIZE, L_FANIN, RQ_M, RQ_SH

  localparam int SA = $clog2(N_NEU * FANIN);
  localparam int AB = (ABUF > 1) ? $clog2(ABUF) : 1;
  localparam int LW = (N_LAYERS > 1) ? $clog2(N_LAYERS) : 1;
  localparam logic [1:0] OP_LOAD = 2'd1, OP_RUN = 2'd2, OP_CLEAR = 2'd3;

  // ------------------------------------------------------------ memories
  logic [7:0] syn_mem[N_NEU*FANIN];
  initial $readmemh(SYN_FILE, syn_mem);
  logic [7:0] act_a[ABUF];
  logic [7:0] act_b[ABUF];

  // ------------------------------------------------------------ FSM
  typedef enum logic [2:0] {IDLE, ACC, RQ1, RQ2, OUTS, FIN} st_t;
  st_t st;
  logic [LW-1:0] l;
  logic [15:0] i;    // neuron within layer
  logic [15:0] j;    // slot counter 0..fanin
  logic [AB-1:0] ptr;
  logic signed [31:0] acc;
  logic signed [31:0] best;
  logic [7:0] bidx;

  wire [15:0] fan  = 16'(L_FANIN[l]);
  wire [15:0] size = 16'(L_SIZE[l]);
  wire last_layer = (32'(l) == N_LAYERS - 1);
  wire src_b = l[0];  // layer l reads buffer A for even l, B for odd l

  // synchronous reads, issued in ACC while j < fanin
  logic signed [7:0] w_q;
  logic [7:0] a_q;
  wire [SA-1:0] saddr = SA'(32'(L_START[l]) + 32'(i)) * SA'(FANIN) + SA'(j);
  always_ff @(posedge clk) begin
    if (st == ACC && j < fan) begin
      w_q <= syn_mem[saddr];
      a_q <= src_b ? act_b[AB'(j)] : act_a[AB'(j)];
    end
  end
  wire signed [16:0] prod = w_q * $signed({1'b0, a_q});

  // requantisation (two stages: registered product, then round/shift/clamp)
  logic signed [55:0] rq_p;
  wire signed [55:0] rq_r = (rq_p + (56'sd1 <<< (RQ_SH[l] - 1))) >>> RQ_SH[l];
  wire [7:0] a_new = (rq_r <= 0) ? 8'd0 : (rq_r >= 255) ? 8'd255 : rq_r[7:0];

  assign ready = (st == IDLE);
  assign done = (st == FIN);
  assign out_valid = (st == OUTS);
  assign out_idx = i[7:0];
  assign out_score = acc;

  // activation writes
  always_ff @(posedge clk) begin
    if (st == IDLE && op_valid && op == OP_LOAD) act_a[ptr] <= op_arg;
    if (st == RQ2) begin
      if (src_b) act_a[AB'(i)] <= a_new;
      else act_b[AB'(i)] <= a_new;
    end
  end

  always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
      st <= IDLE;
      l <= '0;
      i <= '0;
      j <= '0;
      ptr <= '0;
      acc <= '0;
      rq_p <= '0;
      best <= '0;
      bidx <= '0;
      pred <= '0;
    end else begin
      case (st)
        IDLE:
        if (op_valid) begin
          case (op)
            OP_LOAD: begin
              ptr <= ptr + 1'b1;
              st <= FIN;
            end
            OP_CLEAR: begin
              ptr <= '0;
              st <= FIN;
            end
            OP_RUN: begin
              l <= '0;
              i <= '0;
              j <= '0;
              st <= ACC;
            end
            default: st <= FIN;
          endcase
        end
        // cycle j: issue read j (j < fan); accumulate read j-1 (j >= 1)
        ACC: begin
          acc <= (j == 0) ? 32'sd0 : acc + 32'(prod);
          if (j == fan) st <= last_layer ? OUTS : RQ1;
          else j <= j + 1'b1;
        end
        RQ1: begin
          rq_p <= 56'(acc) * $signed({1'b0, 32'(RQ_M[l])});
          st <= RQ2;
        end
        RQ2, OUTS: begin
          if (st == OUTS && (i == 0 || acc > best)) begin
            best <= acc;
            bidx <= i[7:0];
          end
          j <= '0;
          if (i == size - 1) begin
            i <= '0;
            if (last_layer) begin
              pred <= (i == 0 || acc > best) ? i[7:0] : bidx;
              st <= FIN;
            end else begin
              l <= l + 1'b1;
              st <= ACC;
            end
          end else begin
            i <= i + 1'b1;
            st <= ACC;
          end
        end
        FIN: st <= IDLE;
        default: st <= IDLE;
      endcase
    end
  end
endmodule
