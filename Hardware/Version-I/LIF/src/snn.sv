`define TWOS_32(val) (((~(val)) + 1'b1) & ((1 << (32)) - 1))

module SNN (
    input clk,
    input rst,
    input [7:0] GPB,
    input [15:0] EXTB,
    input trefEvent,
    input synEvent,
    input vneuEvent,

    output DONE
);
  // WIRES
  wire signed [31:0] old_volt, leak_volt, next_volt, new_volt;
  reg [31:0] thr_volt = {{16'hffbf}, {16'd0}};
  wire [31:0] tr_volt, next_tr_volt, vn_volt, next_vn_volt, se_volt, next_se_volt;
  wire [15:0] conductance;
  wire [7:0] old_refractory, new_refractory, next_refractory;
  wire [7:0] addr_n, addr_f, synapse_c, synapse_r, syn_w_out, ref_n;
  wire read_v, read_g, read_r, read_f, read_s;
  wire write_v, write_g, write_r, write_f;
  wire start_l;
  wire done_l;
  wire SPIKE;
  wire tr, se, vn;
  // MODULES

  controller controller (
      .clk(clk),
      .rst(rst),
      .GPB(GPB),
      .tr_i(trefEvent),
      .se_i(synEvent),
      .vn_i(vneuEvent),
      .r_v(read_v),
      .w_v(write_v),
      .r_g(read_g),
      .w_g(write_g),
      .r_r(read_r),
      .w_r(write_r),
      .r_f(read_f),
      .w_f(write_f),
      .s_l(start_l),
      .d_l(done_l),
      .tr(tr),
      .se(se),
      .vn(vn),
      .addr(addr_n),
      .f_empty(fifo_empty),
      .spike_neuron(addr_f),
      .ref_old_neuron(old_refractory),
      .ref_new_neuron(next_refractory),
      .spike(write_v && SPIKE),
      .synC(synapse_c),
      .synR(synapse_r),
      .r_s(read_s),
      .done(DONE)
  );

  assign new_refractory = (write_v && SPIKE) ? 8'd20 : next_refractory;

  memR memr (
      .clk  (clk),
      .re   (read_r),
      .we   (write_r),
      .addr (addr_n),
      .rdata(old_refractory),
      .wdata(new_refractory)
  );

  memG memg (
      .clk(clk),
      .re(read_g),
      .we(write_g),
      .addr(addr_n),
      .rdata(conductance)
  );

  assign tr_volt = old_volt - leak_volt;
  assign next_tr_volt = (SPIKE) ? {{16'hffbf}, {16'd0}} : tr_volt;

  assign vn_volt = {{8{EXTB[15]}}, {EXTB}, {8'd0}};
  assign next_vn_volt = (SPIKE) ? {{16'hffbf}, {16'd0}} : vn_volt;

  assign se_volt = old_volt + {{12{syn_w_out[7]}}, {syn_w_out}, {12'd0}};
  assign next_se_volt = (SPIKE) ? {{16'hffbf}, {16'd0}} : se_volt;

  assign next_volt = (tr) ? tr_volt : (vn) ? vn_volt : (se) ? se_volt : 16'd1;
  assign SPIKE = ((next_volt[31] == 1'd1 && (
      `TWOS_32(next_volt)
      <= {{16'd50}, {16'd0}})) || (next_volt[31] == 1'd0));

  assign new_volt = (tr) ? next_tr_volt : (vn) ? next_vn_volt : (se) ? next_se_volt : 16'd1;

  memV memv (
      .clk(clk),
      .re(read_v),
      .we(write_v),
      .addr(addr_n),
      .rdata(old_volt),
      .wdata(new_volt)
  );


  leak leak (
      .clk(clk),
      .rst(rst),
      .start(start_l),
      .volt((old_volt + {{16'd65}, {16'd0}})),
      .conductace(conductance),
      .result(leak_volt),
      .done(done_l)
  );

  syn_memory synapsemem (
      .clk     (clk),
      .rd_en   (read_s),
      .addr_x  (synapse_c),
      .addr_y  (synapse_r),
      .data_out(syn_w_out)
  );


  fifo fifo (
      .clk  (clk),
      .rst  (rst),
      .din  (addr_n),
      .rd_en(read_f),
      .wr_en((write_v && SPIKE)),
      .full (fifo_full),
      .empty(fifo_empty),
      .dout (addr_f)
  );

endmodule
