
module synUnit (
    input             clk,
    input             rd_en,
    input             exc_rst,
    input             exc,
    input      [ 7:0] addr_x,   // Row
    input      [ 7:0] addr_y,   // Col
    output     [7:0] synW,
    output reg [15:0] excite
);

  wire [7:0] syn_w_out;
  assign synW = syn_w_out;
  syn_memory synapse_memory (
      .clk     (clk),
      .rd_en   (rd_en),
      .addr_x  (addr_y),
      .addr_y  (addr_x),
      .data_out(syn_w_out)
  );


  always @(posedge clk or posedge exc_rst) begin
    if (exc_rst) begin
      excite <= 16'd0;
    end else if (exc) begin
      excite <= excite + syn_w_out;
    end
  end
endmodule
