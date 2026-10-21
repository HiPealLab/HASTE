// HASTE Version-IV -- time-multiplexed Hodgkin-Huxley SNN core (synthesisable).
// Same event engine / memory images as snn_lif.sv (see there).
//
// Number formats: V signed Q9.7 mV (rest = 0 mV, HH-1952 convention),
// gates n, m, h signed Q2.14, conductances Q8.8 mS/cm^2.
// Gating rates: six 204-entry x 16-bit ROMs (lut_{a,b}{n,m,h}.mem), indexed
// by the integer part of V (floor, 1 mV resolution), clamped to [-72, 131] mV;
// entry = rate(1/ms) * 256.  One forward-Euler sub-step, dt = 1/128 ms:
//   x' = x + a/2 - sat(|x| (a+b) >> 15)                 (x in n, m, h)
//   I  = gK n^4 (V+12) + gNa m^3 h (V-120) + gL (V-10.5) (5 truncating mults)
//   V' = V - I
// V is floored at VMIN (default -72 mV = lower edge of the rate LUTs) after
// every synaptic jump and every sub-step, so the Q9.7 register cannot wrap.
// Spikes: hysteresis detector (V >= UPPER while armed, re-arm at V <= LOWER).
// Synaptic input: V += ((w * gain_l) >>> 8) >>> 9 (mV jump, Q8.24 gain).
// One shared 16x16 multiplier; 21 cycles per neuron sub-step.
module snn_hh #(
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
  logic [15:0] lut_an[204], lut_bn[204], lut_am[204], lut_bm[204], lut_ah[204], lut_bh[204];
  initial begin
    $readmemh(SYN_FILE, syn_mem);
    $readmemh("lut_an.mem", lut_an);
    $readmemh("lut_bn.mem", lut_bn);
    $readmemh("lut_am.mem", lut_am);
    $readmemh("lut_bm.mem", lut_bm);
    $readmemh("lut_ah.mem", lut_ah);
    $readmemh("lut_bh.mem", lut_bh);
  end
  logic signed [15:0] v_mem[N_NEU], n_mem[N_NEU], m_mem[N_NEU], h_mem[N_NEU];
  logic spk_mem[N_NEU];

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
  function automatic logic [15:0] absu16(input logic [15:0] x);
    return x[15] ? (~x + 16'd1) : x;
  endfunction

  typedef enum logic [3:0] {IDLE, S_RD, S_EX, POP, T_RD, H_LUT, H_MUL, H_WB, CLR, FIN} st_t;
  st_t st;
  logic [NW-1:0] i;
  logic [SW-1:0] j;
  logic [LW-1:0] l;
  logic [15:0] sub;
  logic ctx_step;
  logic [4:0] uc;  // micro-step 0..17 : phase k = uc/6, step s = uc%6

  logic signed [WB-1:0] syn_q;
  logic signed [15:0] v_q, n_q, m_q, h_q;
  logic spk_q;
  wire [SA-1:0] saddr = SA'(i) * SA'(FANIN) + SA'(j);
  always_ff @(posedge clk) begin
    if (st == S_RD) syn_q <= syn_mem[saddr];
    if (st == S_RD || st == T_RD) begin
      v_q <= v_mem[i];
      n_q <= n_mem[i];
      m_q <= m_mem[i];
      h_q <= h_mem[i];
      spk_q <= spk_mem[i];
    end
  end

  // ---- LUT read (address = clamp(floor(V)) + 72), registered ROM outputs
  wire signed [8:0] vi = v_q[15:7];
  wire [7:0] lut_addr = (vi < -9'sd72) ? 8'd0 : (vi > 9'sd131) ? 8'd203 : 8'(vi + 9'sd72);
  logic [15:0] an_q, bn_q, am_q, bm_q, ah_q, bh_q;
  always_ff @(posedge clk) begin
    if (st == H_LUT) begin
      an_q <= lut_an[lut_addr];
      bn_q <= lut_bn[lut_addr];
      am_q <= lut_am[lut_addr];
      bm_q <= lut_bm[lut_addr];
      ah_q <= lut_ah[lut_addr];
      bh_q <= lut_bh[lut_addr];
    end
  end

  // ---- micro-coded datapath, one 16x16 unsigned multiplier
  logic [1:0] k;
  logic [2:0] s;
  always_comb begin
    k = (uc < 5'd6) ? 2'd0 : (uc < 5'd12) ? 2'd1 : 2'd2;
    s = 3'(uc - 5'(k) * 5'd6);
  end
  logic signed [15:0] g_old, g1, g2, vk;
  logic [15:0] a_k, b_k, cond;
  always_comb begin
    case (k)
      2'd0: begin
        g_old = n_q; a_k = an_q; b_k = bn_q; g1 = n_q; g2 = n_q; cond = GK; vk = v_q + 16'sd1536;
      end
      2'd1: begin
        g_old = m_q; a_k = am_q; b_k = bm_q; g1 = m_q; g2 = h_q; cond = GNA; vk = v_q - 16'sd15360;
      end
      default: begin
        g_old = h_q; a_k = ah_q; b_k = bh_q; g1 = 16'sd16384; g2 = 16'sd16384; cond = GL; vk = v_q - 16'sd1344;
      end
    endcase
  end
  logic [15:0] t_reg;
  logic [15:0] mul_a, mul_b;
  always_comb begin
    case (s)
      3'd0: begin mul_a = absu16(g_old); mul_b = a_k + b_k; end
      3'd1: begin mul_a = absu16(vk);    mul_b = absu16(g1); end
      3'd2: begin mul_a = t_reg;         mul_b = absu16(g1); end
      3'd3: begin mul_a = t_reg;         mul_b = absu16(cond); end
      3'd4: begin mul_a = t_reg;         mul_b = absu16(g1); end
      default: begin mul_a = t_reg;      mul_b = absu16(g2); end
    endcase
  end
  wire [31:0] prod = mul_a * mul_b;
  logic [15:0] slice;
  always_comb begin
    case (s)
      3'd0, 3'd3, 3'd5: slice = prod[30:15];
      3'd1: slice = prod[28:13];
      default: slice = prod[29:14];
    endcase
  end
  wire [15:0] sat = slice[15] ? 16'h7FFF : slice;
  // gate update (s == 0)
  wire signed [15:0] alpha_half = $signed(a_k) >>> 1;
  wire signed [15:0] mres = g_old[15] ? -$signed(sat) : $signed(sat);
  wire signed [15:0] g_new = alpha_half - mres + g_old;
  // current term (s == 5)
  wire vdf_sign = vk[15] ^ g1[15] ^ g2[15];
  wire signed [15:0] f_new = vdf_sign ? -$signed(sat) : $signed(sat);

  logic signed [15:0] ng[3], F[3];
  always_ff @(posedge clk) begin
    if (st == H_MUL) begin
      if (s == 3'd0) ng[k] <= g_new;
      else if (s == 3'd5) F[k] <= f_new;
      else t_reg <= slice;
    end
  end

  // ---- write-back / spike detection
  wire signed [15:0] sumF = F[0] + F[1] + F[2];
  wire signed [15:0] vdyn = v_q - sumF;
  wire signed [WB+32:0] inc = syn_q * $signed({1'b0, l_gain(l)});  // Q.24
  wire signed [WB+32:0] inc16 = inc >>> 8;  // Q16.16 mV
  wire signed [15:0] vsyn = v_q + 16'(inc16 >>> 9);  // Q9.7 mV
  wire signed [15:0] vraw = (st == H_WB) ? vdyn : vsyn;
  wire signed [15:0] vnew = (vraw < VMIN) ? VMIN : vraw;
  wire fire = (vnew >= UPPER) && !spk_q;
  wire rearm = (vnew <= LOWER) && spk_q;
  wire spk_next = fire ? 1'b1 : (rearm ? 1'b0 : spk_q);

  logic f_empty, f_rd, f_wr;
  logic [NW-1:0] f_dout;
  snn_fifo #(.WIDTH(NW), .DEPTH(256)) fifo (
      .clk(clk), .rst(rst), .wr(f_wr), .din(i), .rd(f_rd), .dout(f_dout), .empty(f_empty), .ovf(ovf));

  logic [LW-1:0] i_lay, f_lay;
  always_comb begin
    i_lay = '0;
    f_lay = '0;
    for (int q = 0; q < N_LAYERS; q++) begin
      if (i >= l_start(LW'(q))) i_lay = LW'(q);
      if (f_dout >= l_start(LW'(q))) f_lay = LW'(q);
    end
  end
  // next layer of the popped neuron
  wire [LW-1:0] f_nxt = f_lay + 1'b1;
  wire [LW-1:0] cur_l = (st == H_WB) ? i_lay : l;
  wire cur_last = (32'(cur_l) == N_LAYERS - 1);
  wire spike_now = ((st == S_EX) || (st == H_WB)) && fire;

  assign f_wr = spike_now && !cur_last;
  assign f_rd = (st == POP) && !f_empty;
  assign hid_valid = f_wr;
  assign out_valid = spike_now && cur_last;
  assign out_idx = 8'(i - l_start(cur_l));
  assign ready = (st == IDLE);
  assign done = (st == FIN);

  always_ff @(posedge clk) begin
    if (st == S_EX || st == H_WB) begin
      v_mem[i] <= vnew;
      spk_mem[i] <= spk_next;
    end else if (st == CLR) begin
      v_mem[i] <= 16'sd0;
      spk_mem[i] <= 1'b0;
    end
    if (st == H_WB) begin
      n_mem[i] <= ng[0];
      m_mem[i] <= ng[1];
      h_mem[i] <= ng[2];
    end else if (st == CLR) begin
      n_mem[i] <= N_INIT;
      m_mem[i] <= M_INIT;
      h_mem[i] <= H_INIT;
    end
  end

  always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
      st <= IDLE;
      i <= '0;
      j <= '0;
      l <= '0;
      sub <= '0;
      uc <= '0;
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
        T_RD: st <= H_LUT;
        H_LUT: begin
          uc <= '0;
          st <= H_MUL;
        end
        H_MUL:
        if (uc == 5'd17) st <= H_WB;
        else uc <= uc + 1'b1;
        H_WB:
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
