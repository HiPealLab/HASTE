// HASTE Version-IV -- on-board measurement wrapper (PL side).
//
// Wraps the UNCHANGED core (snn_lif by default; MODEL_IZH / MODEL_HH select
// the other cores) with
//   * a 32-bit AXI4-Lite slave for the Zynq PS (register map: board/README.md),
//   * a spike-row buffer (inferred BRAM, T_MAX rows x N_IN bytes, written by
//     the PS in exactly the layout of data/spikes.mem),
//   * a hardware sequencer that issues CLEAR, {AXON...,STEP} x T to the core
//     with the same handshake timing as tb/tb_snn.sv:do_op, and
//   * a cycle counter with the same definition as tb_snn.sv:`cyc`, per-class
//     output-spike counters, a hidden-spike counter, an output-spike log
//     (t, class) and a free-running 64-bit wall-clock counter.
//
// Timing equivalence with tb_snn.sv (all edges are rising clock edges):
//   tb: `active` is set at a falling edge N0, op_valid=1 at N1, so the core
//       accepts CLEAR at the 2nd counted edge.  After an op ends (core in FIN,
//       `done`=1, seen at falling edge Nd) the next op_valid is set at Nd+1
//       and accepted at the first edge on which the core is back in IDLE.
//       After the final STEP's FIN the tb waits one more falling edge before
//       clearing `active`, so the edge that leaves FIN is counted too.
//   here: the START write edge is counted as cycle 1 and registers
//       op_valid=1 (CLEAR) -> accepted at cycle 2.  On every edge with
//       done=1 the next op is registered -> accepted on the next edge (core
//       IDLE).  The edge with done=1 of the final STEP is the last counted.
//   => CYCLES here == `cyc` of tb_snn.sv, exactly (verified with Verilator,
//      board/tb/tb_board.sv).
//
// The core is reset only by the AXI reset or by CTRL.CORE_RST, never between
// images, so the sticky FIFO overflow flag behaves as in the testbench.
// Synthesisable, no vendor IP; single clock domain (s_axi_aclk).
module snn_board #(
    parameter int    T_MAX      = 200,        // max. time steps (rows) per image
    parameter int    LOG_DEPTH  = 1024,       // output-spike log entries
    parameter string SYN_FILE   = "syn.mem",
    parameter string LAYER_FILE = "layer.mem"
) (
    input  logic        clk,
    input  logic        aresetn,
    // AXI4-Lite slave (byte addresses, 64 KiB window)
    input  logic [15:0] s_axi_awaddr,
    input  logic        s_axi_awvalid,
    output logic        s_axi_awready,
    input  logic [31:0] s_axi_wdata,
    input  logic [ 3:0] s_axi_wstrb,
    input  logic        s_axi_wvalid,
    output logic        s_axi_wready,
    output logic [ 1:0] s_axi_bresp,
    output logic        s_axi_bvalid,
    input  logic        s_axi_bready,
    input  logic [15:0] s_axi_araddr,
    input  logic        s_axi_arvalid,
    output logic        s_axi_arready,
    output logic [31:0] s_axi_rdata,
    output logic [ 1:0] s_axi_rresp,
    output logic        s_axi_rvalid,
    input  logic        s_axi_rready
);
`include "params.svh"

  localparam logic [31:0] ID_VALUE = 32'h534E_4E01;  // "SNN", wrapper version 1
  localparam int WPR = N_IN / 4;  // 32-bit words per spike row (N_IN multiple of 4)
  localparam int SB_WORDS = T_MAX * WPR;
  localparam int SBA = $clog2(SB_WORDS);
  localparam int LGA = $clog2(LOG_DEPTH);
  localparam int SW = $clog2(N_IN + 1);  // slot pointer 0..N_IN
  localparam int CW = (N_OUT > 1) ? $clog2(N_OUT) : 1;
  localparam logic [1:0] OP_AXON = 2'd1, OP_STEP = 2'd2, OP_CLEAR = 2'd3;

  // register offsets (byte address [15:0])
  localparam logic [15:0] A_ID = 16'h0000, A_CTRL = 16'h0004, A_STAT = 16'h0008, A_T = 16'h000C,
                          A_CYC = 16'h0010, A_HID = 16'h0014, A_NSPK = 16'h0018, A_INFO = 16'h001C,
                          A_WLO = 16'h0020, A_WHI = 16'h0024, A_RUNS = 16'h0028;
  // 0x0040 + 4*c : COUNT[c]      0x1000 + 4*e : SPKLOG[e]      0x4000 + 4*w : spike buffer (WO)

  // ------------------------------------------------------------------ core
  logic core_rst, ctrl_rst;
  logic op_valid_q;
  logic [1:0] op_q;
  logic [7:0] arg_q;
  logic ready, done, out_valid, hid_valid, ovf;
  logic [7:0] out_idx;

  always_ff @(posedge clk) core_rst <= !aresetn || ctrl_rst;

`ifdef MODEL_IZH
  snn_izh #(.SYN_FILE(SYN_FILE), .LAYER_FILE(LAYER_FILE)) u_core (
`elsif MODEL_HH
  snn_hh #(.SYN_FILE(SYN_FILE), .LAYER_FILE(LAYER_FILE)) u_core (
`else
  snn_lif #(.SYN_FILE(SYN_FILE), .LAYER_FILE(LAYER_FILE)) u_core (
`endif
      .clk(clk), .rst(core_rst), .op_valid(op_valid_q), .op(op_q), .op_arg(arg_q),
      .ready(ready), .done(done), .out_valid(out_valid), .out_idx(out_idx),
      .hid_valid(hid_valid), .ovf(ovf));

  // ------------------------------------------------------------------ AXI write channel
  // AW and W are accepted together (one outstanding write).
  wire wr_hs = s_axi_awvalid && s_axi_wvalid && !s_axi_bvalid;
  assign s_axi_awready = wr_hs;
  assign s_axi_wready  = wr_hs;
  assign s_axi_bresp   = 2'b00;
  wire [15:0] waddr = {s_axi_awaddr[15:2], 2'b00};
  wire wr_reg = wr_hs && (waddr[15:14] == 2'b00);
  wire wr_sb  = wr_hs && (waddr[15:14] == 2'b01);
  wire [13:0] sb_widx = waddr[15:2] - 14'h1000;  // word index in the spike buffer

  always_ff @(posedge clk) begin
    if (!aresetn) s_axi_bvalid <= 1'b0;
    else if (wr_hs) s_axi_bvalid <= 1'b1;
    else if (s_axi_bready) s_axi_bvalid <= 1'b0;
  end

  // ------------------------------------------------------------------ spike-row buffer (BRAM)
  // word w = row*WPR + (slot/4), byte (slot%4) at bits [8*(slot%4) +: 8]
  // (= the byte order of spikes.mem / spikes.bin read as little-endian words)
  logic [31:0] sbuf[SB_WORDS];
  logic [31:0] sb_q;
  logic [SBA-1:0] sb_raddr;
  always_ff @(posedge clk) begin
    if (wr_sb && (32'(sb_widx) < SB_WORDS)) sbuf[sb_widx[SBA-1:0]] <= s_axi_wdata;
    sb_q <= sbuf[sb_raddr];
  end

  // ------------------------------------------------------------------ control registers
  logic [7:0] t_reg;  // time steps per image, 1..T_MAX
  logic start_req;
  always_ff @(posedge clk) begin
    if (!aresetn) begin
      ctrl_rst <= 1'b0;
      t_reg <= 8'(T_MAX < 100 ? T_MAX : 100);
    end else if (wr_reg && waddr == A_CTRL) begin
      ctrl_rst <= s_axi_wdata[1];
    end else if (wr_reg && waddr == A_T) begin
      if (s_axi_wdata == 0) t_reg <= 8'd1;
      else if (s_axi_wdata > T_MAX) t_reg <= 8'(T_MAX);
      else t_reg <= s_axi_wdata[7:0];
    end
  end
  assign start_req = wr_reg && (waddr == A_CTRL) && s_axi_wdata[0] && !s_axi_wdata[1];

  // ------------------------------------------------------------------ sequencer
  typedef enum logic [1:0] {PF_IDLE, PF_RD, PF_DEC} pf_t;
  pf_t pf;
  logic run, cur_last, nxt_rdy, nxt_last, done_flag, err;
  logic [1:0] nxt_op;
  logic [7:0] nxt_arg, nxt_t, t_exec, t_p;
  logic [SW-1:0] s_p;
  logic [31:0] cyc, runs;

  assign sb_raddr = SBA'(32'(t_p) * WPR + 32'(s_p >> 2));
  wire [7:0] sb_byte = sb_q[8*s_p[1:0]+:8];
  wire start = start_req && !run && !core_rst;

  always_ff @(posedge clk) begin
    if (core_rst) begin
      pf <= PF_IDLE;
      run <= 1'b0;
      op_valid_q <= 1'b0;
      op_q <= 2'd0;
      arg_q <= 8'd0;
      cur_last <= 1'b0;
      nxt_rdy <= 1'b0;
      nxt_last <= 1'b0;
      nxt_op <= 2'd0;
      nxt_arg <= 8'd0;
      nxt_t <= 8'd0;
      t_exec <= 8'd0;
      t_p <= 8'd0;
      s_p <= '0;
      cyc <= 32'd0;
      runs <= 32'd0;
      done_flag <= 1'b0;
      err <= 1'b0;
    end else begin
      op_valid_q <= 1'b0;
      // prefetch of the next op from the spike buffer (2 cycles; every core
      // op lasts far longer, so the next op is always ready when `done` rises)
      case (pf)
        PF_RD: pf <= PF_DEC;  // sb_q <= sbuf[(t_p, s_p)]
        PF_DEC: begin
          pf <= PF_IDLE;
          nxt_rdy <= 1'b1;
          nxt_t <= t_p;
          if ((32'(s_p) < N_IN) && (sb_byte != 8'hFF)) begin
            nxt_op <= OP_AXON;
            nxt_arg <= sb_byte;
            nxt_last <= 1'b0;
            s_p <= s_p + 1'b1;
          end else begin
            nxt_op <= OP_STEP;
            nxt_arg <= 8'd0;
            nxt_last <= (t_p == t_reg - 8'd1);
            t_p <= t_p + 8'd1;
            s_p <= '0;
          end
        end
        default: ;
      endcase
      if (start) begin  // counted cycle 1; CLEAR is accepted on cycle 2
        run <= 1'b1;
        cyc <= 32'd1;
        op_valid_q <= 1'b1;
        op_q <= OP_CLEAR;
        arg_q <= 8'd0;
        cur_last <= 1'b0;
        t_exec <= 8'd0;
        t_p <= 8'd0;
        s_p <= '0;
        nxt_rdy <= 1'b0;
        pf <= PF_RD;
        done_flag <= 1'b0;
        err <= 1'b0;
      end else if (run) begin
        cyc <= cyc + 32'd1;
        if (done) begin
          if (cur_last) begin  // last counted cycle (tb: final @(negedge))
            run <= 1'b0;
            done_flag <= 1'b1;
            runs <= runs + 32'd1;
          end else if (nxt_rdy) begin
            op_valid_q <= 1'b1;
            op_q <= nxt_op;
            arg_q <= nxt_arg;
            cur_last <= nxt_last;
            t_exec <= nxt_t;
            nxt_rdy <= 1'b0;
            if (!nxt_last) pf <= PF_RD;
          end else begin  // cannot happen (prefetch underrun): abort, flag
            run <= 1'b0;
            done_flag <= 1'b1;
            err <= 1'b1;
          end
        end
      end
    end
  end

  // ------------------------------------------------------------------ spike counters / log
  // core outputs are registered once (off the core's critical path); the
  // counts are complete long before the PS can read them.
  logic ov_q, hv_q;
  logic [7:0] oi_q, ot_q;
  logic [31:0] cnt_c[N_OUT];
  logic [31:0] hid_c, nspk;
  logic [15:0] log_mem[LOG_DEPTH];
  logic [15:0] log_q;
  always_ff @(posedge clk) begin
    ov_q <= run && out_valid;
    hv_q <= run && hid_valid;
    oi_q <= out_idx;
    ot_q <= t_exec;
    if (core_rst || start) begin
      for (int c = 0; c < N_OUT; c++) cnt_c[c] <= 32'd0;
      hid_c <= 32'd0;
      nspk <= 32'd0;
    end else begin
      if (ov_q) begin
        if (32'(oi_q) < N_OUT) cnt_c[CW'(oi_q)] <= cnt_c[CW'(oi_q)] + 32'd1;
        nspk <= nspk + 32'd1;
      end
      if (hv_q) hid_c <= hid_c + 32'd1;
    end
  end
  always_ff @(posedge clk) begin
    if (ov_q && !core_rst && !start && (nspk < LOG_DEPTH)) log_mem[nspk[LGA-1:0]] <= {ot_q, oi_q};
    if (s_axi_arvalid && s_axi_arready) log_q <= log_mem[s_axi_araddr[LGA+1:2]];
  end

  // ------------------------------------------------------------------ free-running wall clock
  logic [63:0] wall;
  logic [31:0] wall_hi_snap;
  always_ff @(posedge clk) begin
    if (!aresetn) wall <= 64'd0;
    else wall <= wall + 64'd1;
  end

  // ------------------------------------------------------------------ AXI read channel
  logic rd_pend;
  logic [15:0] raddr_q;
  assign s_axi_arready = !s_axi_rvalid && !rd_pend;
  assign s_axi_rresp   = 2'b00;

  logic [31:0] rmux;
  always_comb begin
    rmux = 32'd0;
    if (raddr_q[15:12] == 4'h1) rmux = {16'd0, log_q};
    else if (raddr_q[15:6] == 10'h001) begin  // 0x0040..0x007F
      if (32'(raddr_q[5:2]) < N_OUT) rmux = cnt_c[CW'(raddr_q[5:2])];
    end else
      case (raddr_q)
        A_ID:   rmux = ID_VALUE;
        A_CTRL: rmux = {30'd0, ctrl_rst, 1'b0};
        A_STAT: rmux = {26'd0, (nspk > LOG_DEPTH), err, ready, ovf, done_flag, run};
        A_T:    rmux = {24'd0, t_reg};
        A_CYC:  rmux = cyc;
        A_HID:  rmux = hid_c;
        A_NSPK: rmux = nspk;
        A_INFO: rmux = {8'(N_OUT), 8'(N_IN), 16'(T_MAX)};
        A_WLO:  rmux = wall[31:0];
        A_WHI:  rmux = wall_hi_snap;
        A_RUNS: rmux = runs;
        default: rmux = 32'hDEAD_BEEF;
      endcase
  end

  always_ff @(posedge clk) begin
    if (!aresetn) begin
      rd_pend <= 1'b0;
      s_axi_rvalid <= 1'b0;
      raddr_q <= 16'd0;
      s_axi_rdata <= 32'd0;
      wall_hi_snap <= 32'd0;
    end else if (s_axi_arvalid && s_axi_arready) begin
      rd_pend <= 1'b1;
      raddr_q <= {s_axi_araddr[15:2], 2'b00};
    end else if (rd_pend) begin  // log_q is valid now
      rd_pend <= 1'b0;
      s_axi_rvalid <= 1'b1;
      s_axi_rdata <= rmux;
      if (raddr_q == A_WLO) wall_hi_snap <= wall[63:32];
    end else if (s_axi_rvalid && s_axi_rready) s_axi_rvalid <= 1'b0;
  end

  // unused
  logic unused_ok;
  assign unused_ok = &{1'b0, s_axi_wstrb};
endmodule
