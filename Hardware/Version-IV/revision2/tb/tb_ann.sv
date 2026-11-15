// HASTE revision 2 -- testbench of the 8-bit ANN baseline core (rtl/ann_q8.sv).
// Per image: CLEAR, N_IN x LOAD(pixel), RUN.  Writes
//   IMG k LABEL l PRED p CYCLES c SCORES s0 .. s{N_OUT-1}
// plusargs: +INPUTS=<file> +LABELS=<file> +START=<k> +COUNT=<n> +OUT=<file>
`timescale 1ns / 1ps
module tb_ann;
`include "ann_params.svh"
  localparam int MAX_IMG = 1000;
  localparam real CLK_NS = 20.0;

  logic clk = 1'b0, rst = 1'b1;
  always #(CLK_NS / 2) clk = ~clk;

  logic op_valid = 1'b0;
  logic [1:0] op = 2'd0;
  logic [7:0] op_arg = 8'd0;
  logic ready, done, out_valid;
  logic [7:0] out_idx, pred;
  logic signed [31:0] out_score;

  ann_q8 dut (.*);

  logic [7:0] in_mem[MAX_IMG*N_IN];
  logic [7:0] lab_mem[MAX_IMG];
  string inputs_f, labels_f, out_f;
  int start_k, count_k, fd;
  longint cyc;
  bit active = 0;
  int scores[N_OUT];

  always @(posedge clk) if (active) cyc <= cyc + 1;
  always @(negedge clk) if (active && out_valid) scores[out_idx] <= out_score;

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
    if (!$value$plusargs("INPUTS=%s", inputs_f)) inputs_f = "inputs.mem";
    if (!$value$plusargs("LABELS=%s", labels_f)) labels_f = "labels.mem";
    if (!$value$plusargs("OUT=%s", out_f)) out_f = "rtl_results.txt";
    if (!$value$plusargs("START=%d", start_k)) start_k = 0;
    if (!$value$plusargs("COUNT=%d", count_k)) count_k = MAX_IMG;
    if (start_k + count_k > MAX_IMG) count_k = MAX_IMG - start_k;
    $readmemh(inputs_f, in_mem);
    $readmemh(labels_f, lab_mem);
    fd = $fopen(out_f, "w");
    repeat (3) @(negedge clk);
    rst = 1'b0;
    repeat (2) @(negedge clk);
    for (int k = start_k; k < start_k + count_k; k++) begin
      cyc = 0;
      active = 1;
      do_op(2'd3, 8'd0);  // CLEAR
      for (int s = 0; s < N_IN; s++) do_op(2'd1, in_mem[k*N_IN+s]);  // LOAD
      do_op(2'd2, 8'd0);  // RUN
      @(negedge clk);
      active = 0;
      $fwrite(fd, "IMG %0d LABEL %0d PRED %0d CYCLES %0d SCORES", k, lab_mem[k], pred, cyc);
      for (int c = 0; c < N_OUT; c++) $fwrite(fd, " %0d", scores[c]);
      $fwrite(fd, "\n");
      $fflush(fd);
    end
    $fclose(fd);
    $finish;
  end
endmodule
