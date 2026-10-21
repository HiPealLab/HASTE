module ngvUnit (
    input clk,
    input rst,
    input u_start,
    input [1:0] u_cal_gv,
    input [15:0] voltage,
    input [15:0] old_gv,

    output reg [15:0] new_gv,

    output u_ack,
    output u_done
);


  reg [8:0] volt;



  //    8 - 8
  wire [15:0] alpha;
  wire [15:0] alpha_beta;


  //    2 - 14
  wire signed [15:0] new_ch;
  reg signed [15:0] o_gv;

  //    9 - 7
  wire signed [15:0] p_sum;
  wire signed [15:0] Alpha;
  wire signed [15:0] mul_result;



  assign Alpha  = {{alpha[15]}, {alpha[15:1]}};
  assign p_sum  = Alpha - mul_result;
  assign new_ch = p_sum + o_gv;



  wire mul_start, mul_done;

  wire sv_gv, wr_gv;
  wire [1:0] mode_gv;

  lut LookUp (
      .clk (clk),
      .rst (rst),
      .s_a (mode_gv),
      .s_ab(mode_gv),
      .volt(volt),

      .alpha     (alpha),
      .alpha_beta(alpha_beta)
  );


  ngvController controller (
      .clk(clk),
      .rst(rst),
      .start(u_start),
      .cal_gv(u_cal_gv),
      .mul_done(mul_done),

      .mul_start(mul_start),
      .ack(u_ack),
      .save_gv(sv_gv),
      .write_gv(wr_gv),
      .mode(mode_gv),
      .ready(u_done)
  );

  ngvMult mult (
      .clk  (clk),
      .rst  (rst),
      .start(mul_start),
      .gate (o_gv),
      .rate (alpha_beta),

      .o_mul(mul_result),
      .done (mul_done)
  );

  always @(posedge clk or posedge rst) begin
    if (rst) begin
      o_gv <= 16'd0;
      volt <= 9'd0;
    end else if (sv_gv) begin
      o_gv <= old_gv;
      volt <= voltage[15:7];
    end
  end

  always @(posedge clk or posedge rst) begin
    if (rst) new_gv <= 16'd0;
    else if (wr_gv) new_gv <= new_ch;
  end


endmodule
