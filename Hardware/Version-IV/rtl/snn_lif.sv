// HASTE Version-IV -- time-multiplexed LIF SNN core (synthesisable).
//
// One datapath is shared by all neurons.  Network size/topology live only in
// the generated images: params.svh (sizes), syn.mem (synMem, WB-bit weights,
// addr = neuron*FANIN + slot) and layer.mem (layerMem, {start,end,gain}).
//
// Operations (one at a time, `ready` high in IDLE, `done` pulses at the end):
//   OP_AXON  (arg = input index j): sweep layer 0 with slot j, then drain FIFO
//   OP_STEP : SUBSTEPS x { leak all neurons, drain FIFO }
//   OP_CLEAR: reset all membrane/refractory state
// Fixed point: V signed Q16.16 mV; dV = (w(WB-bit) * gain_l(Q8.24)) >>> 8.
// Leak: V -= V >>> LEAK_SHIFT (arithmetic, truncating).  No saturation: V is
// bounded by THRESH above and by the leak below (checked by the ref model).
module snn_lif #(
    parameter string SYN_FILE   = "syn.mem",
    parameter string LAYER_FILE = "layer.mem"
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       op_valid,
    input  logic [1:0] op,
    input  logic [7:0] op_arg,
    output logic       ready,
    output logic       done,
    output logic       out_valid,
    output logic [7:0] out_idx,
    output logic       hid_valid,
    output logic       ovf
);
`include "params.svh"

  localparam int SW = (FANIN > 1) ? $clog2(FANIN) : 1;
  localparam int SA = $clog2(N_NEU * FANIN);
  localparam int LW = (N_LAYERS > 1) ? $clog2(N_LAYERS) : 1;
  localparam int LMW = 2 * NW + 32;
  localparam logic [1:0] OP_AXON = 2'd1, OP_STEP = 2'd2, OP_CLEAR = 2'd3;

  // ------------------------------------------------------------ memories
  logic [WB-1:0] syn_mem[N_NEU*FANIN];
  initial begin
    $readmemh(SYN_FILE, syn_mem);
  end
  logic signed [31:0] v_mem[N_NEU];
  logic [7:0] r_mem[N_NEU];

  // layer table = LAYER_TAB from params.svh (LAYER_FILE stays only so instantiations are unchanged)
  // because Vivado 2022.2 mis-synthesised the next-layer start read from $readmemh registers
  function automatic logic [NW-1:0] l_start(input logic [LW-1:0] x);
    return LAYER_TAB[x][LMW-1-:NW];
  endfunction
  function automatic logic [NW-1:0] l_end(input logic [LW-1:0] x);
    return LAYER_TAB[x][NW+31-:NW];
  endfunction
  function automatic logic [31:0] l_gain(input logic [LW-1:0] x);
    return LAYER_TAB[x][31:0];
  endfunction

  // ------------------------------------------------------------ FSM
  typedef enum logic [2:0] {IDLE, S_RD, S_EX, POP, T_RD, T_EX, CLR, FIN} st_t;
  st_t st;
  logic [NW-1:0] i;
  logic [SW-1:0] j;
  logic [LW-1:0] l;
  logic [15:0] sub;
  logic ctx_step;

  // synchronous reads (BRAM/LUTRAM friendly)
  logic signed [WB-1:0] syn_q;
  logic signed [31:0] v_q;
  logic [7:0] r_q;
  wire [SA-1:0] saddr = SA'(i) * SA'(FANIN) + SA'(j);
  always_ff @(posedge clk) begin
    if (st == S_RD) syn_q <= syn_mem[saddr];
    if (st == S_RD || st == T_RD) begin
      v_q <= v_mem[i];
      r_q <= r_mem[i];
    end
  end

  // integrate (sweep execute)
  wire signed [WB+32:0] inc = syn_q * $signed({1'b0, l_gain(l)});  // Q.24
  wire signed [31:0] vsum = v_q + 32'(inc >>> 8);  // Q16.16 mV
  wire ok = (r_q == 8'd0);
  wire signed [31:0] vint = ok ? vsum : v_q;
  wire spk = ok && (vint >= THRESH);
  // leak (step execute)
  wire signed [31:0] vleak = ok ? (v_q - (v_q >>> LEAK_SHIFT)) : v_q;
  wire [7:0] rleak = ok ? 8'd0 : (r_q - 8'd1);

  // FIFO
  logic f_empty, f_rd, f_wr;
  logic [NW-1:0] f_dout;
  snn_fifo #(.WIDTH(NW), .DEPTH(256)) fifo (
      .clk(clk), .rst(rst), .wr(f_wr), .din(i), .rd(f_rd), .dout(f_dout), .empty(f_empty), .ovf(ovf));

  wire last_layer = (32'(l) == N_LAYERS - 1);
  assign f_wr = (st == S_EX) && spk && !last_layer;
  assign f_rd = (st == POP) && !f_empty;
  assign hid_valid = f_wr;
  assign out_valid = (st == S_EX) && spk && last_layer;
  assign out_idx = 8'(i - l_start(l));
  assign ready = (st == IDLE);
  assign done = (st == FIN);

  // layer of the popped neuron (layers are contiguous and ascending)
  logic [LW-1:0] f_lay;
  always_comb begin
    f_lay = '0;
    for (int k = 0; k < N_LAYERS; k++) if (f_dout >= l_start(LW'(k))) f_lay = LW'(k);
  end
  // next layer of the popped neuron
  wire [LW-1:0] f_nxt = f_lay + 1'b1;

  // state writes
  always_ff @(posedge clk) begin
    if (st == S_EX) begin
      v_mem[i] <= spk ? 32'sd0 : vint;
      r_mem[i] <= spk ? 8'(REFR_STEPS) : r_q;
    end else if (st == T_EX) begin
      v_mem[i] <= vleak;
      r_mem[i] <= rleak;
    end else if (st == CLR) begin
      v_mem[i] <= 32'sd0;
      r_mem[i] <= 8'd0;
    end
  end

  always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
      st <= IDLE;
      i <= '0;
      j <= '0;
      l <= '0;
      sub <= '0;
      ctx_step <= 1'b0;
    end else begin
      case (st)
        IDLE:
        if (op_valid) begin
          case (op)
            OP_AXON: begin
              l <= '0;
              j <= SW'(op_arg);
              i <= l_start('0);
              ctx_step <= 1'b0;
              st <= S_RD;
            end
            OP_STEP: begin
              i <= '0;
              sub <= '0;
              ctx_step <= 1'b1;
              st <= T_RD;
            end
            OP_CLEAR: begin
              i <= '0;
              st <= CLR;
            end
            default: st <= FIN;
          endcase
        end
        S_RD: st <= S_EX;
        S_EX:
        if (i == l_end(l)) st <= POP;
        else begin
          i <= i + 1'b1;
          st <= S_RD;
        end
        POP:
        if (!f_empty) begin
          l <= f_nxt;
          j <= SW'(f_dout - l_start(f_lay));
          i <= l_start(f_nxt);
          st <= S_RD;
        end else if (!ctx_step) st <= FIN;
        else if (32'(sub) == SUBSTEPS - 1) st <= FIN;
        else begin
          sub <= sub + 1'b1;
          i <= '0;
          st <= T_RD;
        end
        T_RD: st <= T_EX;
        T_EX:
        if (32'(i) == N_NEU - 1) st <= POP;
        else begin
          i <= i + 1'b1;
          st <= T_RD;
        end
        CLR:
        if (32'(i) == N_NEU - 1) st <= FIN;
        else i <= i + 1'b1;
        FIN: st <= IDLE;
        default: st <= IDLE;
      endcase
    end
  end
endmodule
