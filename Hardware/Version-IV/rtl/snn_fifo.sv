// First-word-fall-through spike FIFO (neuron indices of hidden-layer spikes).
// A push while full is dropped and latches `ovf` (sticky until reset).
module snn_fifo #(
    parameter int WIDTH = 8,
    parameter int DEPTH = 256
) (
    input  logic             clk,
    input  logic             rst,
    input  logic             wr,
    input  logic [WIDTH-1:0] din,
    input  logic             rd,
    output logic [WIDTH-1:0] dout,
    output logic             empty,
    output logic             ovf
);
  localparam int AW = $clog2(DEPTH);
  logic [WIDTH-1:0] mem[DEPTH];
  logic [AW-1:0] wp, rp;
  logic [AW:0] cnt;

  assign empty = (cnt == 0);
  assign dout  = mem[rp];

  always_ff @(posedge clk) begin
    if (wr && (cnt != DEPTH)) mem[wp] <= din;
  end

  always_ff @(posedge clk or posedge rst) begin
    if (rst) begin
      wp <= '0;
      rp <= '0;
      cnt <= '0;
      ovf <= 1'b0;
    end else begin
      if (wr) begin
        if (cnt != DEPTH) wp <= wp + 1'b1;
        else ovf <= 1'b1;
      end
      if (rd && !empty) rp <= rp + 1'b1;
      cnt <= cnt + ((wr && (cnt != DEPTH)) ? 1 : 0) - ((rd && !empty) ? 1 : 0);
    end
  end
endmodule
