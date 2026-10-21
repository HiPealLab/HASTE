module SNN (
    input clk,
    input rst,
    input start,

    input [7:0] AER_IN,

    output [7:0] AER_OUT,
    output aer_req,

    input synEvent,

    input trefEvent,

    input [15:0] nueVolt,
    input vneuEvent,

    input setLayer,

    input [7:0] layer,
    output done,

    output DONE
);


  wire signed [15:0] new_V, V_Bus, excite, r_synapse;
  wire [15:0] new_gv, H_bus, M_bus, N_bus, GL_bus, GNa_bus, GK_bus, oldgv, vM, NorM, NorH, Gch;



  wire signed [17:0] sumFs;
  wire [7:0] s_synapse,neuron_addr, syn_addrx, syn_addry, spik_neu, SPK_NEURON, offset, count, nlayer, nstart;
  wire [1:0] tref_mode;
  wire spike, spk_rec;
  wire vd_start, ngv_start, vd_done, ngv_done, wr_N, wr_M, wr_H, wr_V, gv_rd, rd_v;
  wire exc, exc_rst, wrF, tr, se, ne, vn, spkEn;

  wire spike_rd, spike_full, spike_empty;


  wire [15:0] neVbus, exSynapse;
  assign exSynapse = {{5{s_synapse[7]}}, s_synapse, {3'd0}};

  assign neVbus = V_Bus + exSynapse;

  assign oldgv = (tref_mode == 2'd0) ? N_bus : (tref_mode == 2'd1) ? M_bus : (tref_mode == 2'd2) ? H_bus : 16'd0;
  assign new_V = (tr == 1'b1) ? (V_Bus - sumFs) :
                 (se == 1'b1) ? V_Bus + {{1{s_synapse[7]}},s_synapse,{7'd0}} :
                 (ne == 1'b1) ? neVbus :
                 (vn == 1'b1) ? nueVolt :
                 {16{1'd1}};

  layerMem LayerMem (
      .clk   (clk),
      .rd_en (setLayer),
      .addr  (layer),
      .offset(offset),
      .count (count),
      .nextstart(nstart),
      .nextlayer(nlayer)
  );



  snnController controller (
      .clk(clk),
      .rst(rst),
      .start(start),
      .AER_IN(AER_IN),
      .AER_OUT(AER_OUT),
      .aer_req(aer_req),
      .SPK_NEU(SPK_NEURON),
      .NEU_CAP(count),
      .NEU_OFF(offset),
      .NEU_NXT(nlayer),
      .NEU_STR(nstart),
      .LastLayerD(8'd128),
      .LastLayerU(8'd138),
      .spike_rd(spike_rd),
      .spike_full(spike_full),
      .spike_empty(spike_empty),
      .synEvent(synEvent),
      .trefEvent(trefEvent),
      .vneuEvent(vneuEvent),
      .tref_mode(tref_mode),
      .neuron_addr(neuron_addr),
      .vd_start(vd_start),
      .ngv_start(ngv_start),
      .vd_done(vd_done),
      .ngv_done(ngv_done),
      .spk((~spk_rec)),
      .wr_n(wr_N),
      .wr_m(wr_M),
      .wr_h(wr_H),
      .wr_v(wr_V),
      .spk_en(spkEn),
      .rd_gv(gv_rd),
      .rd_v(rd_v),
      .rd_syn(rd_syn),
      .syn_row(syn_addrx),
      .syn_col(syn_addry),
      .tr(tr),
      .se(se),
      .ne(ne),
      .vn(vn),
      .exc(exc),
      .exc_rst(exc_rst),
      .done(done)
  );


  ngvUnit NGVUnit (
      .clk     (clk),
      .rst     (rst),
      .u_start (ngv_start),
      .u_cal_gv(tref_mode),
      .voltage (V_Bus),
      .old_gv  (oldgv),
      .new_gv  (new_gv),
      .u_ack   (ack),
      .u_done  (ngv_done)
  );


  volt_memory Vmem (
      .clk(clk),
      .wr_en(wr_V),
      .rd_en(rd_v),
      .addr(neuron_addr),
      .data_in(new_V),
      .EN(spkEn),
      .data_out(V_Bus),
      .spk_neu(spik_neu),
      .spk(spike),
      .done(DONE)
  );

  NgK_memory NgK (
      .clk(clk),
      .wr_en(wr_N),
      .rd_en(gv_rd),
      .addr(neuron_addr),
      .data_in(new_gv),
      .Ndata_out(N_bus),
      .GKdata_out(GK_bus)
  );

  MgNa_memory MgNa (
      .clk(clk),
      .wr_en(wr_M),
      .rd_en(gv_rd),
      .addr(neuron_addr),
      .data_in(new_gv),
      .Mdata_out(M_bus),
      .GNadata_out(GNa_bus)
  );

  HgL_memory HgL (
      .clk(clk),
      .wr_en(wr_H),
      .rd_en(gv_rd),
      .addr(neuron_addr),
      .data_in(new_gv),
      .Hdata_out(H_bus),
      .GLdata_out(GL_bus)
  );



  voltMux #(
      .WIDTH(16)
  ) Vmux (
      .volt(V_Bus),
      .sel (tref_mode),
      .v_m (vM)
  );

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
      .o_m  (Gch)
  );



  vdfUnit DVunit (
      .clk      (clk),
      .rst      (rst),
      .start    (vd_start),
      .tref_mode(tref_mode),

      .gate_1    (NorM),
      .gate_2    (NorH),
      .conductace(Gch),
      .volt      (vM),
      .wrF       (wrF),
      .sumFs     (sumFs),
      .done      (vd_done)
  );


  synUnit SYNunit (
      .clk    (clk),
      .rd_en  (1'b1),
      .exc_rst(exc_rst),
      .exc    (exc),
      .addr_x (syn_addrx),
      .addr_y (syn_addry),
      .synW   (s_synapse),
      .excite (r_synapse)
  );

  frFifo FRfifo (
      .clk  (clk),
      .rst  (rst),
      .wr_en(spike),
      .din  (spik_neu),
      .rd_en(spike_rd),
      .full (spike_full),
      .empty(spk_rec),
      .dout (SPK_NEURON)
  );


endmodule
