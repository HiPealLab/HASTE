`include "spikes.svh"

module tb;

  /*
  vsim -gui work.tb -voptargs=+acc
  */

  reg clk = 1'b0;
  reg rst = 1'b0;
  reg start = 1'b0;
  reg tr = 1'b0;
  reg se = 1'b0;
  reg vn = 1'b0;
  reg [7:0] gpb = 8'd0;
  reg [15:0] extb = 16'd0;
  always #5 clk = ~clk;

  SNN lif (
      .clk(clk),
      .rst(rst),
      .GPB(gpb),
      .EXTB(extb),
      .trefEvent(tr),
      .synEvent(se),
      .vneuEvent(vn),
      .DONE(d)
  );
  integer Irow = 0;
  integer Icol = 0;
  reg [7:0] Nneuron = 0;


  initial begin
    #10;
    #10;
    rst = 1;
    #10;
    #10;
    rst = 0;
    #10;
    #10;
    simulate();

    $stop;
  end
  task automatic simulate();
    begin
      // TREF(8'd0, 1);
      for (Irow = 0; Irow < 100; Irow = Irow + 1) begin
        for (Icol = 0; Icol < 64; Icol = Icol + 1) begin
          Nneuron = img_6_7[Irow][Icol];
          if (Nneuron == 8'd255) begin
            break;
          end else begin
            setVolt(.neuron(Nneuron), .voltage({{8'd90}, {8'd0}}));
          end
        end
        TREF(8'd1, 10);
        TREF(8'd0, 1);
      end
    end
  endtask


  task automatic TREF(input [7:0] LAYER, times);
    begin
      repeat (times) begin
        gpb = LAYER;
        tr  = 1'b1;
        #15;
        @(posedge d);
        tr = 1'b0;
        #15;
      end
    end
  endtask

  // task automatic SETLAYER(input [7:0] LAYER, times);
  //   begin
  //       gpb = LAYER;
  //       tr  = 1'b1;
  //       #15;
  //       @(posedge d);
  //       tr = 1'b0;
  //       #15;
  //   end
  // endtask


  task automatic setVolt(input [7:0] neuron, input [15:0] voltage);
    begin
      gpb  = neuron;
      extb = voltage;
      #15;
      vn = 1;
      #15;
      @(posedge d);
      #15;
      vn = 0;
    end
  endtask


endmodule
