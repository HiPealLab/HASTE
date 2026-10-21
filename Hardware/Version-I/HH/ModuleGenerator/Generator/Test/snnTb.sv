`include "spikes.svh"

module snnTb ();

  reg clk = 0;
  reg rst = 0;
  reg start = 0;
  always #5 clk = ~clk;

  integer Irow = 0;
  integer Icol = 0;
  reg [7:0] Nneuron = 0;


  reg [15:0] neuvolt = 16'd0;
  wire printDone;
  reg [7:0] AERI = 0;
  wire [7:0] AERO;
  wire aerQ;
  reg [7:0] lay = 0;
  reg setlay = 0;
  reg synEvent = 0;
  reg trefEvent = 0;
  reg vneuEvent = 0;



  SNN HH (
      .clk  (clk),
      .rst  (rst),
      .start(start),

      .AER_IN(AERI),

      .AER_OUT(AERO),
      .aer_req(aerQ),

      .synEvent(synEvent),

      .trefEvent(trefEvent),

      .nueVolt  (neuvolt),
      .vneuEvent(vneuEvent),

      .setLayer(setlay),
      .layer(lay),

      .done(hhdone),

      .DONE(printDone)
  );

  /*
vsim -gui work.snnTb -voptargs=+acc
*/


  initial begin

    INIT();

    // TREF(8'd0, 1);
    // TREF(8'd1, 1);
    // TREF(8'd2, 1);

    // stim();

    // TREF(8'd1, 1);
    // SETLAYER(8'd0);

    simulate();

    // SETLAYER(8'd1);
    $stop;
  end

  task automatic stim();
    begin
      for (Irow = 0; Irow < 20; Irow = Irow + 1) begin
        spikeNeuron(.neuron(8'd1));
      end
    end
  endtask


  task automatic simulate();
    begin
      for (Irow = 0; Irow < 50; Irow = Irow + 1) begin
        for (Icol = 0; Icol < 64; Icol = Icol + 1) begin
          Nneuron = img_0_0[Irow][Icol];
          if (Nneuron == 8'd255) begin
            break;
          end else begin
            spikeNeuron(.neuron(Nneuron));
          end
        end
        TREF(8'd1, 20);
        TREF(8'd2, 100);
        TREF(8'd1, 20);
        TREF(8'd2, 100);
      end
    end
  endtask

  // Icol = 64;
  // TREF(8'd2, 200);
  // TREF(8'd1, 1);
  // RESET();

  task automatic INIT();
    begin
      rst = 1;
      #10;
      rst = 0;
      #10;
      lay = 8'd0;
      #10;
      setlay = 1;
      #10;
      setlay = 0;
      #10;
    end
  endtask


  task automatic setVolt(input [7:0] neuron, input [15:0] voltage);
    begin
      AERI = neuron;
      neuvolt = voltage;
      #15;
      vneuEvent = 1;
      #15;
      @(posedge hhdone);
      #15;
      vneuEvent = 0;
    end
  endtask

  task automatic spikeNeuron(input [7:0] neuron);
    begin
      #15;
      setVolt(.neuron(neuron), .voltage({{9'h1B2}, {7'd0}}));
      #15;
      setVolt(.neuron(neuron), .voltage({{9'd120}, {7'd0}}));
      #15;
    end
  endtask


  task automatic TREF(input [7:0] LAYER, times);
    begin
      repeat (times) begin
        SETLAYER(LAYER);
        trefEvent = 1'b1;
        #15;
        @(posedge hhdone);
        trefEvent = 1'b0;
        #15;
        SETLAYER(8'd0);
      end
    end
  endtask

  task automatic SETLAYER(input [7:0] LAYER);
    begin
      #20;
      lay = LAYER;
      #20;
      setlay = 1;
      #20;
      setlay = 0;
      #15;
    end
  endtask

  task automatic RESET();
    begin
      for (Irow = 64; Irow < 74; Irow = Irow + 1) begin
        setVolt(.neuron(Irow), .voltage({{9'h1B2}, {7'd0}}));
      end
    end
  endtask



endmodule





