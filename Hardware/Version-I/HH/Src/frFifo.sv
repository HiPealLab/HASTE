module frFifo (
    // Inputs
    clk,
    rst,
    wr_en,
    rd_en,
    din,

    // Outputs
    dout,
    full,
    empty
);

  //================================================================
  // Port Declarations
  //================================================================
  input clk;
  input rst;
  input wr_en;
  input rd_en;
  input [7:0] din;

  output reg [7:0] dout;
  output full;
  output empty;

  //================================================================
  // Internal Parameters and Signals
  //================================================================
  localparam DEPTH = 256;
  localparam WIDTH = 8;
  localparam ADDR_WIDTH = 8;  // $clog2(DEPTH)

  reg [WIDTH-1:0] mem[DEPTH];

  reg [ADDR_WIDTH:0] wr_ptr;
  reg [ADDR_WIDTH:0] rd_ptr;


  //================================================================
  // Logic Implementation
  //================================================================

  // Write Operation
  always @(posedge clk or posedge rst) begin
    if (rst) begin
      wr_ptr <= 0;
    end else if (wr_en && !full) begin
      mem[wr_ptr[ADDR_WIDTH-1:0]] <= din;
      wr_ptr <= wr_ptr + 1;
      if (din > 64) $display("din = ", din);
    end
  end

  // Read Operation
  always @(posedge clk or posedge rst) begin
    if (rst) begin
      rd_ptr <= 0;
      dout   <= 0;
    end else if (rd_en && !empty) begin
      dout   <= mem[rd_ptr[ADDR_WIDTH-1:0]];
      rd_ptr <= rd_ptr + 1;
    end
  end

  // Full and Empty Logic
  assign full = (wr_ptr[ADDR_WIDTH] != rd_ptr[ADDR_WIDTH]) && (wr_ptr[ADDR_WIDTH-1:0] == rd_ptr[ADDR_WIDTH-1:0]);
  assign empty = (wr_ptr == rd_ptr);

endmodule
