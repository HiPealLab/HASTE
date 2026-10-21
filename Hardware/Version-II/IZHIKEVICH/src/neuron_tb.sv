`include "spikes.svh"

module neuron_tbIZH;

  import file_pkg::*;

  logic clk;
  logic rst;


  initial clk = 0;
  always #5 clk = ~clk;

  reg [ 7:0] ADDR_I = 0;
  reg [ 7:0] ADDR_J = 0;
  reg [15:0] input_current = 16'd30;
  reg [15:0] input_volt = 16'd0;
  wire spike, done, ack;

  reg tr = 0;
  reg de = 0;
  reg ae = 0;
  reg ve = 0;
  reg vn = 0;

  wire [7:0] I_ADDR;
  wire [7:0] J_ADDR;

  wire [7:0] addr_f;

  IZH izh (
      .clk(clk),
      .rst(rst),
      .tr(tr),
      .ve(ve),
      .vn(vn),
      .de(de),
      .ae(ae),
      .IADDR(ADDR_I),
      .JADDR(ADDR_J),
      .input_current(input_current),
      .input_volt(input_volt),
      .ack(ack),
      .done(done)
  );


  integer Irow = 0;
  integer Icol = 0;
  reg [7:0] Nneuron = 0;

  initial begin
    spike_file = $fopen("output.txt", "w");
    if (spike_file == 0) begin
      $display("ERROR: Could not open file!");
      $finish;
    end
  end

  initial begin
    #10;
    rst = 1;
    #10;
    rst = 0;
    #10;

    // VIRN(8'd0, {{8'd34}, {8'd0}});
    SIM();

    $stop;
  end

  task automatic TREF(input [7:0] trN, integer t);
    begin
      repeat (t) begin
        ADDR_I = trN;
        tr = 1;
        @(posedge ack);
        tr = 0;
        @(posedge done);
      end
    end
  endtask

  task automatic AXON(input [7:0] trN);
    begin
      ADDR_J = trN;
      @(posedge clk);
      ae = 1;
      @(posedge ack);
      ae = 0;
      @(posedge done);
    end
  endtask

  task automatic VIRN(input [7:0] trN, input [15:0] VOLT);
    begin
      ADDR_I = trN;
      input_volt = VOLT;
      @(posedge clk);
      vn = 1;
      @(posedge ack);
      vn = 0;
      @(posedge done);
    end
  endtask

  task automatic VIRN_range(input int start_trN, input int end_trN, input [15:0] VOLT);
    int k;
    begin
      for (k = start_trN; k <= end_trN; k++) begin
        ADDR_I = k[7:0];
        input_volt = VOLT;
        @(posedge clk);
        vn = 1;
        @(posedge ack);
        vn = 0;
        @(posedge done);
      end
    end
  endtask

  task automatic SIM();
    begin
      for (Irow = 0; Irow < 100; Irow = Irow + 1) begin
        for (Icol = 0; Icol < 64; Icol = Icol + 1) begin
          Nneuron = spikes[Irow][Icol];
          if (Nneuron == 8'd255) begin
            break;
          end else begin
            AXON(Nneuron);
          end
        end
        TREF(8'd0, 2);
        TREF(8'd1, 2);
        TREF(8'd2, 2);
        TREF(8'd3, 2);
        TREF(8'd4, 2);
        TREF(8'd5, 2);
        TREF(8'd6, 2);
        TREF(8'd7, 2);
        TREF(8'd8, 2);
        TREF(8'd9, 2);
      end
      VIRN_range(0, 74, 16'd0);
      $fdisplay(spike_file, "---0---");

    end
  endtask
endmodule

