module ngvtb ();

  reg clk = 0;
  reg rst = 0;
  reg start = 0;
  always #5 clk = ~clk;

  /*
  vsim -gui work.ngvtb -voptargs=+acc
*/

  wire [15:0] new_gv;
  wire ack, done;
  // ngvUnit u_ngvUnit (
  //     .clk     (clk),
  //     .rst     (rst),
  //     .u_start (start),
  //     .u_cal_gv(2'd1),
  //     .voltage ({{9'd20}, {7'd0}}),
  //     .old_gv  ({{2'd1}, {4'd0}, {10'd0}}),
  //     .new_gv  (new_gv),
  //     .u_ack   (ack),
  //     .u_done  (done)
  // );

  vdfmult DVmult (
      .clk       (clk),
      .rst       (rst),
      .start     (start),
      .gate_1    ({{2'd1}, {4'd6}, {10'd0}}),
      // .gate_1    ({{2'd1}, {4'd0}, {10'd0}}),
      .gate_2    ({{2'd1}, {4'd6}, {10'd0}}),
      .conductace({{8'd1}, {8'd0}}),
      .volt      ({{9'd1}, {7'd0}}),
      .o_mul     (F_mul),
      .wrF       (wrF),
      .done      (done)
  );



  initial begin
    rst = 1;
    #10;
    rst = 0;
    #10;
    start = 1;
    #200;
    $stop;
  end

endmodule

// reg [15:0] volt = {{9'd132}, {7'd0}};
// reg [15:0] first_gate = {{2'd1}, {8'd40}, {6'd0}};
// reg [15:0] second_gate = {{2'd1}, {8'd40}, {6'd0}};
// reg [15:0] conductance = {{8'd120}, {8'd0}};

// wire [15:0] mul_r;
// wire mul_d;

// vdfmult mut (
//     .clk(clk),
//     .rst(rst),
//     .start(start),
//     .volt(volt),
//     .gate_1(first_gate),
//     .gate_2(second_gate),
//     .conductace(conductance),
//     .o_mul(mul_r),
//     .done(mul_d)
// );


// initial begin
//   rst = 1;
//   #10;
//   rst = 0;
//   #20;
//   start = 1;
//   #10;
//   start = 0;
//   @(posedge mul_d);
//   #20;
//   $stop;
// end
