// HASTE Version-IV -- Verilator testbench of the on-board wrapper.
//
// Drives board/rtl/snn_board_top.v through a small AXI4-Lite master BFM
// doing exactly the register accesses of board/sw/main.c (run_image()), and
// writes the same result format as tb/tb_snn.sv:
//   SPK k t class            (from the wrapper's output-spike log)
//   IMG k LABEL l HID h OVF o CYCLES c COUNTS c0 .. c9
// The BFM randomises valid/ready delays (AW before W, late BREADY/RREADY) to
// exercise the slave; the measured CYCLES do not depend on them.
// plusargs: +SPIKES=<file> +LABELS=<file> +START=<k> +COUNT=<n> +OUT=<file>
//           +TDATA=<rows per image in SPIKES, default 100> +T=<steps, default TDATA>
//           +SEED=<n>
`timescale 1ns / 1ps
module tb_board;
`include "params.svh"
  localparam int T_MAX = 200;
  localparam int MAX_IMG = 1000;
  localparam int WPR = N_IN / 4;
  // register map (board/README.md)
  localparam logic [15:0] R_ID = 16'h0000, R_CTRL = 16'h0004, R_STAT = 16'h0008, R_T = 16'h000C,
                          R_CYC = 16'h0010, R_HID = 16'h0014, R_NSPK = 16'h0018, R_INFO = 16'h001C,
                          R_WLO = 16'h0020, R_WHI = 16'h0024, R_RUNS = 16'h0028,
                          R_COUNT = 16'h0040, R_LOG = 16'h1000, R_SBUF = 16'h4000;

  logic clk = 1'b0, aresetn = 1'b0;
  always #10 clk = ~clk;  // 50 MHz

  logic [15:0] awaddr = 0, araddr = 0;
  logic [31:0] wdata = 0, rdata;
  logic awvalid = 0, wvalid = 0, bready = 0, arvalid = 0, rready = 0;
  logic awready, wready, bvalid, arready, rvalid;
  logic [1:0] bresp, rresp;

  snn_board_top dut (
      .s_axi_aclk(clk), .s_axi_aresetn(aresetn),
      .s_axi_awaddr(awaddr), .s_axi_awprot(3'd0), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
      .s_axi_wdata(wdata), .s_axi_wstrb(4'hF), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
      .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
      .s_axi_araddr(araddr), .s_axi_arprot(3'd0), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
      .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready));

  // ---------------------------------------------------------------- AXI4-Lite master BFM
  // All signals change on falling edges; a handshake happens on the rising
  // edge after a falling edge at which valid && ready (sampled 1 ns after
  // the falling edge, because AWREADY/WREADY depend combinationally on the
  // valids).
  task automatic axi_write(input logic [15:0] a, input logic [31:0] d);
    int dly;
    @(negedge clk);
    awaddr = a;
    awvalid = 1'b1;
    dly = $urandom_range(0, 2);
    repeat (dly) @(negedge clk);
    wdata = d;
    wvalid = 1'b1;
    #1;  // let the slave's (combinational) ready settle
    while (!(awready && wready)) begin
      @(negedge clk);
      #1;
    end
    @(negedge clk);  // handshake on the rising edge in between
    awvalid = 1'b0;
    wvalid = 1'b0;
    dly = $urandom_range(0, 2);
    repeat (dly) @(negedge clk);
    bready = 1'b1;
    while (!bvalid) @(negedge clk);
    if (bresp != 2'b00) $fatal(1, "BRESP %0d at %h", bresp, a);
    @(negedge clk);
    bready = 1'b0;
  endtask

  task automatic axi_read(input logic [15:0] a, output logic [31:0] d);
    int dly;
    @(negedge clk);
    araddr = a;
    arvalid = 1'b1;
    #1;
    while (!arready) begin
      @(negedge clk);
      #1;
    end
    @(negedge clk);
    arvalid = 1'b0;
    dly = $urandom_range(0, 2);
    repeat (dly) @(negedge clk);
    rready = 1'b1;
    while (!rvalid) @(negedge clk);
    d = rdata;
    if (rresp != 2'b00) $fatal(1, "RRESP %0d at %h", rresp, a);
    @(negedge clk);
    rready = 1'b0;
  endtask

  // ---------------------------------------------------------------- stimulus (= sw/main.c)
  logic [7:0] spk_mem[MAX_IMG*T_MAX*N_IN];
  logic [7:0] lab_mem[MAX_IMG];
  string spikes_f, labels_f, out_f;
  int start_k, count_k, fd, T, TDATA, seed;
  logic [31:0] r, cyc, hid, stat, nspk, info, w0, w1;

  initial begin
    if (!$value$plusargs("SPIKES=%s", spikes_f)) spikes_f = "spikes.mem";
    if (!$value$plusargs("LABELS=%s", labels_f)) labels_f = "labels.mem";
    if (!$value$plusargs("OUT=%s", out_f)) out_f = "board_results.txt";
    if (!$value$plusargs("START=%d", start_k)) start_k = 0;
    if (!$value$plusargs("COUNT=%d", count_k)) count_k = 50;
    if (!$value$plusargs("TDATA=%d", TDATA)) TDATA = 100;
    if (!$value$plusargs("T=%d", T)) T = TDATA;
    if ($value$plusargs("SEED=%d", seed)) void'($urandom(seed));
    if (TDATA > T_MAX || T > TDATA) $fatal(1, "need T <= TDATA <= %0d", T_MAX);
    if (start_k + count_k > MAX_IMG) count_k = MAX_IMG - start_k;
    $readmemh(spikes_f, spk_mem);
    $readmemh(labels_f, lab_mem);
    fd = $fopen(out_f, "w");
    repeat (5) @(negedge clk);
    aresetn = 1'b1;
    repeat (20) @(negedge clk);

    // board_init(): identify, idle/reset cycle of the core, set T
    axi_read(R_ID, r);
    if (r != 32'h534E_4E01) $fatal(1, "bad ID %h", r);
    axi_read(R_INFO, info);
    if (info[31:24] != N_OUT || info[23:16] != N_IN || info[15:0] < T) $fatal(1, "bad INFO %h", info);
    axi_write(R_CTRL, 32'h2);  // CORE_RST = 1 (idle mode)
    repeat (10) @(negedge clk);
    axi_read(R_CTRL, r);
    axi_read(R_STAT, stat);
    if (r != 32'h2 || stat[0]) $fatal(1, "core not held in reset: CTRL %h STATUS %h", r, stat);
    axi_write(R_CTRL, 32'h0);  // release
    axi_write(R_T, T);
    axi_read(R_T, r);
    if (r != T) $fatal(1, "T readback %0d != %0d", r, T);
    axi_read(R_WLO, w0);
    axi_read(R_WHI, w1);

    for (int k = start_k; k < start_k + count_k; k++) begin
      // load_image(): row-major, only up to the word that holds the 0xFF terminator
      for (int t = 0; t < T; t++) begin
        for (int w = 0; w < WPR; w++) begin
          automatic int base = (k * TDATA + t) * N_IN + 4 * w;
          automatic logic [31:0] word = {spk_mem[base+3], spk_mem[base+2], spk_mem[base+1], spk_mem[base]};
          axi_write(R_SBUF + 16'(4 * (t * WPR + w)), word);
          if (word[7:0] == 8'hFF || word[15:8] == 8'hFF || word[23:16] == 8'hFF || word[31:24] == 8'hFF) break;
        end
      end
      // run_image()
      axi_write(R_CTRL, 32'h1);  // START
      do axi_read(R_STAT, stat); while (!stat[1]);
      if (stat[4]) $fatal(1, "sequencer ERR on image %0d", k);
      if (stat[5]) $fatal(1, "spike log overflow on image %0d", k);
      axi_read(R_CYC, cyc);
      axi_read(R_HID, hid);
      axi_read(R_NSPK, nspk);
      for (int e = 0; e < nspk; e++) begin
        axi_read(R_LOG + 16'(4 * e), r);
        $fdisplay(fd, "SPK %0d %0d %0d", k, r[15:8], r[7:0]);
      end
      $fwrite(fd, "IMG %0d LABEL %0d HID %0d OVF %0d CYCLES %0d COUNTS", k, lab_mem[k], hid, stat[2], cyc);
      for (int c = 0; c < N_OUT; c++) begin
        axi_read(R_COUNT + 16'(4 * c), r);
        $fwrite(fd, " %0d", r);
      end
      $fwrite(fd, "\n");
      $fflush(fd);
    end
    axi_read(R_RUNS, r);
    if (r != count_k) $fatal(1, "RUNS %0d != %0d", r, count_k);
    axi_read(R_WLO, r);
    $display("tb_board: %0d images, wall-clock counter advanced %0d cycles", count_k, r - w0);
    $fclose(fd);
    $finish;
  end
endmodule
