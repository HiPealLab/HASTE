// HASTE Version-IV generic testbench (LIF / IZH / HH selected with
// +define+MODEL_LIF / MODEL_IZH / MODEL_HH).
//
// Replays the pre-encoded spike trains from data/spikes.mem (the same file
// the Python reference model reads), counts clock cycles per image and
// writes one result file:
//   IMG k LABEL l HID h OVF o CYCLES c COUNTS c0 .. c9
//   SPK k t class            (every output-layer spike, in order)
// plusargs: +SPIKES=<file> +LABELS=<file> +START=<k> +COUNT=<n> +OUT=<file>
//           +TDATA=<rows per image in SPIKES, default 100, max T_MAX>
//           +T=<time steps simulated per image, default TDATA>  (T sweep: prefix of the encoding)
`timescale 1ns / 1ps
module tb_snn;
`include "params.svh"
  localparam int T_MAX = 200;
  localparam int MAX_IMG = 1000;
  localparam real CLK_NS = 20.0;  // 50 MHz reporting clock

  logic clk = 1'b0, rst = 1'b1;
  always #(CLK_NS / 2) clk = ~clk;

  logic op_valid = 1'b0;
  logic [1:0] op = 2'd0;
  logic [7:0] op_arg = 8'd0;
  logic ready, done, out_valid, hid_valid, ovf;
  logic [7:0] out_idx;

`ifdef MODEL_IZH
  snn_izh dut (.*);
`elsif MODEL_HH
  snn_hh dut (.*);
`else
  snn_lif dut (.*);
`endif

  logic [7:0] spk_mem[MAX_IMG*T_MAX*N_IN];
  logic [7:0] lab_mem[MAX_IMG];
  string spikes_f, labels_f, out_f;
  int start_k, count_k, fd, T, TDATA;
  int t_cur, img_cur;
  longint cyc;
  bit active = 0;
  int counts[N_OUT];
  int hid;

  always @(posedge clk) if (active) cyc <= cyc + 1;

  always @(negedge clk) begin
    if (active && out_valid) begin
      counts[out_idx] <= counts[out_idx] + 1;
      $fdisplay(fd, "SPK %0d %0d %0d", img_cur, t_cur, out_idx);
      $fflush(fd);  // so a time-limited gate-level run (netlist_sim.tcl T_PREFIX) keeps its lines
    end
    if (active && hid_valid) hid <= hid + 1;
  end

  task automatic do_op(input logic [1:0] o, input logic [7:0] a);
    @(negedge clk);
    op_valid = 1'b1;
    op = o;
    op_arg = a;
    @(negedge clk);
    op_valid = 1'b0;
    while (!done) @(negedge clk);
  endtask

  initial begin
    if (!$value$plusargs("SPIKES=%s", spikes_f)) spikes_f = "spikes.mem";
    if (!$value$plusargs("LABELS=%s", labels_f)) labels_f = "labels.mem";
    if (!$value$plusargs("OUT=%s", out_f)) out_f = "rtl_results.txt";
    if (!$value$plusargs("START=%d", start_k)) start_k = 0;
    if (!$value$plusargs("COUNT=%d", count_k)) count_k = MAX_IMG;
    if (!$value$plusargs("TDATA=%d", TDATA)) TDATA = 100;
    if (!$value$plusargs("T=%d", T)) T = TDATA;
    if (TDATA > T_MAX || T > TDATA) $fatal(1, "need T <= TDATA <= %0d", T_MAX);
    if (start_k + count_k > MAX_IMG) count_k = MAX_IMG - start_k;
    $readmemh(spikes_f, spk_mem);
    $readmemh(labels_f, lab_mem);
    fd = $fopen(out_f, "w");
    repeat (3) @(negedge clk);
    rst = 1'b0;
    repeat (2) @(negedge clk);
    for (int k = start_k; k < start_k + count_k; k++) begin
      img_cur = k;
      for (int c = 0; c < N_OUT; c++) counts[c] = 0;
      hid = 0;
      t_cur = 0;
      cyc = 0;
      active = 1;
      do_op(2'd3, 8'd0);  // CLEAR
      for (int t = 0; t < T; t++) begin
        t_cur = t;
        for (int s = 0; s < N_IN; s++) begin
          automatic logic [7:0] jj = spk_mem[(k*TDATA+t)*N_IN+s];
          if (jj == 8'hFF) break;
          do_op(2'd1, jj);  // AXON
        end
        do_op(2'd2, 8'd0);  // STEP
      end
      @(negedge clk);
      active = 0;
      $fwrite(fd, "IMG %0d LABEL %0d HID %0d OVF %0d CYCLES %0d COUNTS", k, lab_mem[k], hid, ovf, cyc);
      for (int c = 0; c < N_OUT; c++) $fwrite(fd, " %0d", counts[c]);
      $fwrite(fd, "\n");
      $fflush(fd);
    end
    $fclose(fd);
    $finish;
  end
endmodule
