module HH (
    input clk,
    input rst,

    // Event ports
    input       tr,
    input       ve,
    input       vn,
    input       de,
    input       ae,
    input [7:0] IADDR,
    input [7:0] JADDR,

    // Virtual manipulations
    input [15:0] input_current,
    input [15:0] input_volt,

    // Handshake
    output ack,
    output done

);

  // Internal wires
  wire [7:0] I_ADDR;
  wire [7:0] J_ADDR;
  wire       spike;
  wire [7:0] addr_f;
  wire [1:0] t_trfm;
  wire t_ngvS, t_ngvD;
  wire t_vdfS, t_vdfD;
  wire [15:0] t_nVolt, t_nN, t_nM, t_nH;
  wire [15:0] t_ngK, t_ngNa, t_ngL;
  wire [15:0] t_dvdt, t_i_gv;
  wire read_f, write_f, fifo_empty;

  // neuron instance
  neuron hh (
      .clk(clk),
      .rst(rst),
      .tr(tr),
      .ve(ve),
      .vn(vn),
      .de(de),
      .ae(ae),
      .IADDR(IADDR),
      .JADDR(JADDR),
      .I_ADDR(I_ADDR),
      .J_ADDR(J_ADDR),
      .r_f(read_f),
      .w_f(write_f),
      .e_f(fifo_empty),
      .n_f(addr_f),
      .input_current(input_current),
      .input_volt(input_volt),
      .spike(spike),
      .ack(ack),
      .trfm(t_trfm),
      .ngvS(t_ngvS),
      .ngvD(t_ngvD),
      .vdfS(t_vdfS),
      .vdfD(t_vdfD),
      .nVolt(t_nVolt),
      .nN(t_nN),
      .nM(t_nM),
      .nH(t_nH),
      .ngK(t_ngK),
      .ngNa(t_ngNa),
      .ngL(t_ngL),
      .dvdt(t_dvdt),
      .i_gv(t_i_gv),
      .done(done)
  );

  // fifo instance
  fifo fifo_inst (
      .clk  (clk),
      .rst  (rst),
      .din  (I_ADDR),
      .rd_en(read_f),
      .wr_en(write_f),
      .full (fifo_full),
      .empty(fifo_empty),
      .dout (addr_f)
  );

  // ngvUnit instance
  ngvUnit ngv (
      .clk(clk),
      .rst(rst),
      .u_start(t_ngvS),
      .trefm(t_trfm),
      .voltage(t_nVolt),
      .N_bus(t_nN),
      .M_bus(t_nM),
      .H_bus(t_nH),
      .new_gv(t_i_gv),
      .u_done(t_ngvD)
  );

  // vdfUnit instance
  vdfUnit vdf (
      .clk(clk),
      .rst(rst),
      .start(t_vdfS),
      .tref_mode(t_trfm),
      .N_bus(t_nN),
      .M_bus(t_nM),
      .H_bus(t_nH),
      .GK_bus(t_ngK),
      .GNa_bus(t_ngNa),
      .GL_bus(t_ngL),
      .volt(t_nVolt),
      .sumFs(t_dvdt),
      .done(t_vdfD)
  );


endmodule
