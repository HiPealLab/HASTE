module layerMem (
    input       clk,
    input       rd_en,
    input [7:0] addr,

    output reg [7:0] offset,
    output reg [7:0] count,
    output reg [7:0] nextstart,
    output reg [7:0] nextlayer
);
  reg [31:0] layers[3] = {
    //offset count   nstart  nend,
    { {8'd0}, {8'd63}, {8'd64}, {8'd127}},
    { {8'd64}, {8'd63}, {8'd128}, {8'd137}},
    { {8'd128}, {8'd9}, {8'd138}, {8'd137}}
  };

  always @(posedge clk) begin
    if (rd_en) begin
      offset <= layers[addr][31:24];
      count <= layers[addr][23:16];
      nextstart <= layers[addr][15:8];
      nextlayer <= layers[addr][7:0];
    end
  end

endmodule
