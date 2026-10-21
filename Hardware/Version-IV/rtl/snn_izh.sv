// HASTE Version-IV -- time-multiplexed Izhikevich SNN core (synthesisable).
// Same event engine / memory images as snn_lif.sv (see there).
// Per sub-step (forward Euler, dt = 2^-DT_SHIFT ms), all in signed Q16.16:
//   v' = v + (0.04 v^2 + 5 v + 140 - u) * dt        (0.04 ~= 2621 / 2^16)
//   u' = u + a (b v - u) * dt                         (a = A_Q8/256, b = B_Q8/256)
//   if v' >= VPEAK: v' = c (VRESET), u' += d (DRESET)
// Synaptic input: v += (w * gain_l) >>> 8 (Q16.16 mV jump), same spike rule.
// Products are truncated (arithmetic shifts); registers are 32-bit.
// V is floored at VMIN after every synaptic jump and every Euler sub-step
// (inhibitory floor).  This bounds |V| < 181 mV, so v^2 (Q32.32 -> Q16.16,
// 32-bit) can never wrap; without it strong inhibition drove v^2 past 2^31.
// Fixes vs Version-II: correct signed arithmetic (unsigned*signed mixing),
// correct sign of the Euler update, d = 8 actually applied, u not clobbered
// during synaptic sweeps, rest state v = c, u = b c.
module snn_izh #(
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

  logic [WB-1:0] syn_mem[N_NEU*FANIN];
  initial begin
    $readmemh(SYN_FILE, syn_mem);
  end
  logic signed [31:0] v_mem[N_NEU];
  logic signed [31:0] u_mem[N_NEU];

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

  typedef enum logic [3:0] {IDLE, S_RD, S_EX, POP, T_RD, D0, D1, D2, CLR, FIN} st_t;
  st_t st;
  logic [NW-1:0] i;
  logic [SW-1:0] j;
  logic [LW-1:0] l;
  logic [15:0] sub;
  logic ctx_step;

  logic signed [WB-1:0] syn_q;
  logic signed [31:0] v_q, u_q;
  wire [SA-1:0] saddr = SA'(i) * SA'(FANIN) + SA'(j);
  always_ff @(posedge clk) begin
    if (st == S_RD) syn_q <= syn_mem[saddr];
    if (st == S_RD || st == T_RD) begin
      v_q <= v_mem[i];
      u_q <= u_mem[i];
    end
  end

  // ---- synaptic integrate
  wire signed [WB+32:0] inc = syn_q * $signed({1'b0, l_gain(l)});  // Q.24
  wire signed [31:0] vsum = v_q + 32'(inc >>> 8);  // Q16.16 mV
  wire spk_s = (vsum >= VPEAK);
  wire signed [31:0] vsum_c = (vsum < VMIN) ? VMIN : vsum;

  // ---- dynamics pipeline (D0 -> D1 -> D2)
  logic signed [31:0] q1, t3, bv, t2, du;
  wire signed [63:0] p_vv = v_q * v_q;
  wire signed [39:0] p_bv = v_q * $signed(9'(B_Q8));
  wire signed [47:0] p_t2 = q1 * $signed(13'sd2621);
  wire signed [31:0] bvu = bv - u_q;
  wire signed [40:0] p_du = bvu * $signed(9'(A_Q8));
  always_ff @(posedge clk) begin
    if (st == D0) begin
      q1 <= p_vv[47:16];
      t3 <= v_q * 32'sd5;
      bv <= 32'(p_bv >>> 8);
    end
    if (st == D1) begin
      t2 <= 32'(p_t2 >>> 16);
      du <= 32'(p_du >>> 8);
    end
  end
  wire signed [31:0] dv = t2 + t3 + 32'sd9175040 - u_q;  // 140 << 16
  wire signed [31:0] vn = v_q + (dv >>> DT_SHIFT);
  wire signed [31:0] un = u_q + (du >>> DT_SHIFT);
  wire spk_d = (vn >= VPEAK);
  wire signed [31:0] vn_c = (vn < VMIN) ? VMIN : vn;

  logic f_empty, f_rd, f_wr;
  logic [NW-1:0] f_dout;
  snn_fifo #(.WIDTH(NW), .DEPTH(256)) fifo (
      .clk(clk), .rst(rst), .wr(f_wr), .din(i), .rd(f_rd), .dout(f_dout), .empty(f_empty), .ovf(ovf));

  // layer of neuron i (for spikes emitted during dynamics) and of FIFO head
  logic [LW-1:0] i_lay, f_lay;
  always_comb begin
    i_lay = '0;
    f_lay = '0;
    for (int k = 0; k < N_LAYERS; k++) begin
      if (i >= l_start(LW'(k))) i_lay = LW'(k);
      if (f_dout >= l_start(LW'(k))) f_lay = LW'(k);
    end
  end
  // next layer of the popped neuron
  wire [LW-1:0] f_nxt = f_lay + 1'b1;
  wire [LW-1:0] cur_l = (st == D2) ? i_lay : l;
  wire cur_last = (32'(cur_l) == N_LAYERS - 1);
  wire spike_now = ((st == S_EX) && spk_s) || ((st == D2) && spk_d);

  assign f_wr = spike_now && !cur_last;
  assign f_rd = (st == POP) && !f_empty;
  assign hid_valid = f_wr;
  assign out_valid = spike_now && cur_last;
  assign out_idx = 8'(i - l_start(cur_l));
  assign ready = (st == IDLE);
  assign done = (st == FIN);

  always_ff @(posedge clk) begin
    if (st == S_EX) begin
      v_mem[i] <= spk_s ? VRESET : vsum_c;
      u_mem[i] <= spk_s ? (u_q + DRESET) : u_q;
    end else if (st == D2) begin
      v_mem[i] <= spk_d ? VRESET : vn_c;
      u_mem[i] <= spk_d ? (un + DRESET) : un;
    end else if (st == CLR) begin
      v_mem[i] <= VRESET;
      u_mem[i] <= U_INIT;
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
        T_RD: st <= D0;
        D0: st <= D1;
        D1: st <= D2;
        D2:
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
