module vdfUnit (
    input                     clk,
    input                     rst,
    input                     start,
    input              [ 1:0] tref_mode,
    // input              [15:0] gate_1,
    // input              [15:0] gate_2,
    // 
    input              [15:0] N_bus,
    input              [15:0] M_bus,
    input              [15:0] H_bus,
    // 
    input              [15:0] GK_bus,
    input              [15:0] GNa_bus,
    input              [15:0] GL_bus,
    // 
    input              [15:0] volt,
    // input              [15:0] conductace,
    output wire signed [15:0] sumFs,
    output reg                done
);

  wire        wrF;
  wire [15:0] V_Bus;
  voltMux #(
      .WIDTH(16)
  ) Vmux (
      .volt(volt),
      .sel (tref_mode),
      .v_m (V_Bus)
  );


  wire [15:0] NorM, NorH, conductace;
  IImux #(
      .WIDTH(16)
  ) Gmux1 (
      .i_i (N_bus),
      .i_ii(M_bus),
      .sel (tref_mode),
      .o_m (NorM)
  );

  IImux #(
      .WIDTH(16)
  ) Gmux2 (
      .i_i (N_bus),
      .i_ii(H_bus),
      .sel (tref_mode),
      .o_m (NorH)
  );

  IIImux #(
      .WIDTH(16)
  ) conductace_mux (
      .i_i  (GK_bus),
      .i_ii (GNa_bus),
      .i_iii(GL_bus),
      .sel  (tref_mode),
      .o_m  (conductace)
  );


  wire [15:0] F_mul;
  reg signed [15:0] FK, FNa, FL;
  assign sumFs = FK + FNa + FL;
  always @(posedge clk or posedge rst) begin
    if (rst) begin
      FK  <= 16'd1;
      FNa <= 16'd1;
      FL  <= 16'd1;
    end else if (wrF) begin
      if (tref_mode == 2'd0) FK <= F_mul;
      if (tref_mode == 2'd1) FNa <= F_mul;
      if (tref_mode == 2'd2) FL <= F_mul;
    end
  end


  vdfmult DVmult (
      .clk       (clk),
      .rst       (rst),
      .start     (start),
      .gate_1    (NorM),
      .gate_2    (NorH),
      .conductace(conductace),
      .volt      (V_Bus),
      .o_mul     (F_mul),
      .wrF       (wrF),
      .done      (done)
  );

endmodule
