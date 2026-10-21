module snnController (
    input clk,
    input rst,
    input start,

    input [7:0] AER_IN,

    output reg [7:0] AER_OUT,
    output reg aer_req,

    input [7:0] SPK_NEU,

    input [7:0] LastLayerU,
    input [7:0] LastLayerD,

    input [7:0] NEU_CAP,
    input [7:0] NEU_OFF,
    input [7:0] NEU_NXT,
    input [7:0] NEU_STR,

    output reg spike_rd,
    input spike_full,
    input spike_empty,

    input synEvent,

    input trefEvent,

    input vneuEvent,

    output reg [1:0] tref_mode,
    output reg [7:0] neuron_addr,

    output reg vd_start,
    output reg ngv_start,

    input vd_done,
    input ngv_done,


    input spk,


    output reg wr_n,
    output reg wr_m,
    output reg wr_h,
    output reg wr_v,
    output reg spk_en,

    output reg rd_gv,
    output reg rd_v,
    output reg rd_syn,


    output [7:0] syn_row,
    output [7:0] syn_col,


    output reg exc,
    output reg exc_rst,

    output reg tr,
    output reg se,
    output reg ne,
    output reg vn,

    output reg done
);

  typedef enum logic [5:0] {
    IDLE    = 6'd0,
    WAIT    = 6'd1,
    INIT    = 6'd2,
    TRFI    = 6'd3,
    RDNK    = 6'd4,
    WAITNK  = 6'd5,
    UPNK    = 6'd6,
    WRNK    = 6'd7,
    RDMNa   = 6'd8,
    WAITMNa = 6'd9,
    UPMNa   = 6'd10,
    WRMNa   = 6'd11,
    RDHL    = 6'd12,
    WAITHL  = 6'd13,
    UPHL    = 6'd14,
    WRHL    = 6'd15,
    NEUPAR  = 6'd16,
    HOLD    = 6'd17,
    SYNI    = 6'd18,
    RDSYN   = 6'd19,
    SYNSUM  = 6'd20,
    SETSYN  = 6'd21,
    SYNCHK  = 6'd22,
    SYNUPV  = 6'd23,
    SYNWRV  = 6'd24,
    NEUCAP  = 6'd25,
    REDSPK  = 6'd30,
    CHKSPK  = 6'd26,
    CALSPK  = 6'd27,
    PARSPK  = 6'd28,
    RDVSPK  = 6'd29,
    INCSPK  = 6'd31,
    CAPSPK  = 6'd32,
    WRISPK  = 6'd33,
    VNEUE   = 6'd34,
    GETNV   = 6'd35,
    SETNV   = 6'd36,
    WRINV   = 6'd37,
    SETAER  = 6'd38,
    GIVAER  = 6'd39,
    UNAER   = 6'd40,

    DONE = 6'd63
  } state_t;
  state_t pstate, nstate;

  always @(posedge clk or posedge rst) begin
    if (rst) pstate <= IDLE;
    else pstate <= nstate;
  end
  reg synMode = 1'b1;
  reg aerFlag = 1'b0;
  reg [7:0] synR, synC, neuronA;

  // wire Y;
  // assign Y = (ne & tr) | (ne & se) | (tr & se);
  // wire chngfsc;
  // assign chngfsc = (((synC == 8'd255)&&(synMode == 1'b1))||((synR == 8'd255)&&(synMode == 1'b0)));
  // HOLD:    nstate = DONE;
  // SETSYN:  nstate = RDSYN;

  assign syn_row = synR;
  assign syn_col = synC;
  assign neuron_addr = (vn || ne) ? neuronA : neuronA + NEU_OFF;

  always @(*) begin
    case (pstate)
      IDLE: nstate = WAIT;
      WAIT: nstate = INIT;
      INIT: nstate = (synEvent) ? SYNI : (trefEvent) ? TRFI : (vneuEvent) ? VNEUE : INIT;
      TRFI: nstate = RDNK;
      RDNK: nstate = UPNK;
      UPNK: nstate = WAITNK;
      WAITNK: nstate = (vd_done && ngv_done) ? WRNK : WAITNK;
      WRNK: nstate = RDMNa;
      RDMNa: nstate = UPMNa;
      UPMNa: nstate = WAITMNa;
      WAITMNa: nstate = (vd_done && ngv_done) ? WRMNa : WAITMNa;
      WRMNa: nstate = RDHL;
      RDHL: nstate = UPHL;
      UPHL: nstate = WAITHL;
      WAITHL: nstate = (vd_done && ngv_done) ? WRHL : WAITHL;
      WRHL: nstate = NEUPAR;
      NEUPAR: nstate = (neuronA == NEU_CAP) ? HOLD : NEUCAP;
      NEUCAP: nstate = TRFI;
      REDSPK: nstate = CALSPK;
      CALSPK: nstate = (aerFlag) ? SETAER : PARSPK;

      SETAER: nstate = GIVAER;
      GIVAER: nstate = UNAER;
      UNAER:  nstate = HOLD;

      PARSPK: nstate = RDVSPK;
      RDVSPK: nstate = CAPSPK;

      CAPSPK: nstate = (syn_row == NEU_NXT) ? CHKSPK : WRISPK;
      WRISPK: nstate = INCSPK;
      INCSPK: nstate = PARSPK;
      CHKSPK: nstate = (spk == 1'd1) ? REDSPK : DONE;

      HOLD: nstate = CHKSPK;

      DONE:   nstate = WAIT;
      SYNI:   nstate = RDSYN;
      RDSYN:  nstate = SYNSUM;
      SYNSUM: nstate = SYNCHK;
      SYNCHK: nstate = SYNUPV;
      SYNUPV: nstate = SYNWRV;
      SYNWRV: nstate = HOLD;


      VNEUE: nstate = GETNV;
      GETNV: nstate = SETNV;
      SETNV: nstate = WRINV;
      WRINV: nstate = HOLD;

      default: nstate = IDLE;
    endcase
  end


  always @(pstate) begin
    case (pstate)
      IDLE: begin
        AER_OUT = 8'd0;
        aer_req = 1'd0;
        exc = 1'b0;
        spk_en = 1'b0;
        spike_rd = 1'b0;
        exc_rst = 1'b1;
        synR = 8'd0;
        synC = 8'd0;
        done = 1'b0;
        vd_start = 1'b0;
        ngv_start = 1'b0;
        rd_v = 1'b0;
        wr_n = 1'b0;
        wr_m = 1'b0;
        wr_h = 1'b0;
        wr_v = 1'b0;
        rd_gv = 1'b0;
        tref_mode = 2'd3;
        neuronA = 8'd0;
        vn = 1'b0;
        tr = 1'd0;
        se = 1'd0;
        rd_syn = 1'd0;
      end
      WAIT: begin
      end
      INIT: begin
        tref_mode = 2'd3;
        neuronA = 8'd0;
        tr = 1'd0;
        se = 1'd0;
        ne = 1'd0;
        vn = 1'd0;
        rd_v = 1'b0;
      end
      TRFI: begin
        done = 1'b0;
        tr   = 1'd1;
      end
      RDNK: begin
        rd_gv = 1;
        rd_v = 1;
        tref_mode = 0;
      end
      UPNK: begin
        ngv_start = 1;
        vd_start  = 1;
      end
      WAITNK: begin
        ngv_start = 0;
        vd_start  = 0;
      end
      WRNK: begin
        wr_n = 1;
      end
      RDMNa: begin
        rd_v = 1;
        tref_mode = 1;
        wr_n = 0;
      end
      UPMNa: begin
        ngv_start = 1;
        vd_start  = 1;
      end
      WAITMNa: begin
        ngv_start = 0;
        vd_start  = 0;
      end
      WRMNa: begin
        wr_m = 1;
      end
      RDHL: begin
        rd_v = 1;
        tref_mode = 2;
        wr_m = 0;
      end
      UPHL: begin
        ngv_start = 1;
        vd_start  = 1;
      end
      WAITHL: begin
        ngv_start = 0;
        vd_start  = 0;
      end
      WRHL: begin
        spk_en = 1;
        wr_v   = 1;
        wr_h   = 1;
        rd_gv  = 0;
      end
      NEUPAR: begin
        wr_v   = 0;
        spk_en = 0;
        wr_h   = 0;
      end
      NEUCAP: begin
        neuronA = neuronA + 1'b1;
      end
      REDSPK: begin
        synMode = 1'b0;
        synC = SPK_NEU;
        synR = NEU_STR;
        wr_v = 1'b0;
        spike_rd = 1'b0;
        ne = 1'd1;
      end
      CHKSPK: begin
        spike_rd = 1'b1;
        se = 1'b0;
        wr_v = 1'b0;
        tr = 1'b0;
      end
      CALSPK: begin
        spike_rd = 1'b0;
        if ((synC < LastLayerU) && (synC > LastLayerD)) begin
          aerFlag = 1'b1;
        end
      end
      PARSPK: begin
        neuronA = synR;
      end
      RDVSPK: begin
        rd_v = 1;
      end
      CAPSPK: begin
        wr_v = 1'b1;
      end
      WRISPK: begin
        wr_v = 1'b0;
      end
      INCSPK: begin
        synR = synR + 1'b1;
      end
      SYNI: begin
        done = 1'b0;
        synMode = 1'b1;
        se = 1'b1;
        synC = AER_IN;
        synR = AER_IN;
        neuronA = AER_IN;
      end
      RDSYN: begin
        rd_v   = 1'b1;
        rd_syn = 1'd1;
      end
      SYNSUM: begin
        rd_v   = 1'b0;
        rd_syn = 1'd0;
      end
      SYNCHK: begin
      end
      SETSYN: begin
        synC = synC + 1'b1;
      end
      SYNUPV: begin
        wr_v = 1;
      end
      SYNWRV: begin
        wr_v = 0;
      end
      VNEUE: begin
        done = 1'b0;
        vn = 1'b1;
        spk_en = 1;
        neuronA = AER_IN;
      end
      GETNV: begin
        rd_v = 1'b1;
      end
      SETNV: begin
        rd_v = 1'b0;
        wr_v = 1'b1;
      end
      WRINV: begin
        vn = 1'b0;
        wr_v = 1'b0;
        spk_en = 0;
      end
      DONE: begin
        spike_rd = 1'b0;
        done = 1'b1;
      end
      SETAER: begin
        aerFlag = 1'b0;
        AER_OUT = synC;
      end
      GIVAER: begin
        aer_req = 1'b1;
      end
      UNAER: begin
        aer_req = 1'b0;
      end
    endcase
  end

endmodule
