module LIF (
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
  wire read_f, write_f, fifo_empty;

  // neuron instance
  neuron lif (
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

endmodule
