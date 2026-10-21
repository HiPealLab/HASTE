
package file_pkg;
  integer spike_file;
endpackage

module neuron_tb;

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

  LIF lif (
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
  reg [7:0] NeuronNum = 0;

  integer fd;
  integer i_row, i_col;
  integer value;
  int testid;
  logic [7:0] tests[1000][100][64];
  int label[1000];

  initial begin
    // Tests
    fd = $fopen("spikes.dat", "r");
    if (fd == 0) begin
      $display("Error: cannot open spikes file!");
      $finish;
    end
    for (testid = 0; testid < 1000; testid++) begin
      for (i_row = 0; i_row < 100; i_row++) begin
        for (i_col = 0; i_col < 64; i_col++) begin
          $fscanf(fd, "%d", value);
          tests[testid][i_row][i_col] = value;
        end
      end
    end
    $fclose(fd);

    // Labels
    fd = $fopen("labels.dat", "r");
    if (fd == 0) begin
      $display("Error: cannot open labels file!");
      $finish;
    end

    for (testid = 0; testid < 1000; testid++) begin
      $fscanf(fd, "%d", value);
      label[testid] = value;
    end
    $fclose(fd);

  end


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
    // SIMN(1000);
    $fclose(spike_file);
    // $display("SIM DONE!");
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

  task automatic TREF_range(input int start_trN, input int end_trN, input int times);
    int k;
    begin
      repeat (times) begin
        for (k = start_trN; k <= end_trN; k++) begin
          ADDR_I = k[7:0];
          @(posedge clk);
          tr = 1;
          @(posedge ack);
          tr = 0;
          @(posedge done);
        end
      end
    end
  endtask

  task automatic SIM(input int round);
    begin
      for (Irow = 0; Irow < 100; Irow = Irow + 1) begin
        for (Icol = 0; Icol < 64; Icol = Icol + 1) begin
          NeuronNum = tests[round][Irow][Icol];
          if (NeuronNum == 8'd255) begin
            break;
          end else begin
            AXON(NeuronNum);
          end
        end
        TREF_range(0, 9, 2);
      end
      VIRN_range(0, 74, 16'd0);
      $fdisplay(spike_file, "---", label[round], "---");

    end
  endtask

  task automatic SIMN(input int count);
    begin
      for (i_row = 0; i_row < count; i_row = i_row + 1) begin
        SIM(i_row);
      end
    end
  endtask




endmodule

