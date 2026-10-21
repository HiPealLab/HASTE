module controller (
    input clk,
    input rst,

    input [7:0] GPB,

    input f_empty,

    input tr_i,
    input se_i,
    input vn_i,

    output reg r_v,
    w_v,

    output reg r_g,
    w_g,

    output reg r_r,
    w_r,

    output reg r_f,
    w_f,

    output reg s_l,
    input d_l,

    output [7:0] addr,

    output reg [7:0] synC,
    synR,
    output reg r_s,

    input spike,

    input [7:0] spike_neuron,

    input [7:0] ref_old_neuron,
    output reg [7:0] ref_new_neuron,

    output reg tr,
    output reg se,
    output reg vn,
    output reg done
  );

  reg [7:0] layerMem[2][4] = '{'{8'd0, 8'd64, 8'd128, 8'd138}, '{8'd63, 8'd73, 8'd137, 8'd139}};

  reg [7:0] neu_s = 8'd0;
  reg [7:0] neu_f = 8'd63;
  reg [7:0] mReg = 8'd0;
  reg [7:0] neuron;

  wire lay1, lay2, lay3;
  assign lay1 = ((spike_neuron >= 8'd0) && (spike_neuron <= 8'd63));
  assign lay2 = ((spike_neuron >= 8'd64) && (spike_neuron <= 8'd73));
  assign lay3 = ((spike_neuron >= 8'd128) && (spike_neuron <= 8'd138));

  assign addr = neuron;

  typedef enum logic [5:0] {
            IDLE   = 6'd0,
            WAIT   = 6'd1,
            INIT   = 6'd2,
            ACKN   = 6'd3,
            // Time Reference
            TREF   = 6'd4,
            SETLAY = 6'd5,
            SETLK  = 6'd6,
            OFFL   = 6'd7,
            TWRV   = 6'd8,
            TNWV   = 6'd9,
            NCAP   = 6'd10,
            NINC   = 6'd11,
            TRDV   = 6'd12,

            // Virtual Neuron
            VNEU = 6'd13,
            VWRV = 6'd16,
            VNWV = 6'd17,


            CHKSPK = 6'd18,
            REDSPK = 6'd19,
            SETSPK = 6'd20,
            PARSPK = 6'd21,
            RDVSPK = 6'd22,
            CAPSPK = 6'd23,
            WRISPK = 6'd24,
            INCSPK = 6'd25,

            REFRAC  = 6'd26,
            SETREFR = 6'd27,
            SPKVSET = 6'd28,

            HOLD = 6'd62,
            DONE = 6'd63
          } state_t;
  state_t pstate, nstate;


  always @(posedge clk or posedge rst)
  begin
    if (rst)
      pstate <= IDLE;
    else
      pstate <= nstate;
  end

  always @(*)
  begin
    case (pstate)
      IDLE:
        nstate = WAIT;
      WAIT:
        nstate = INIT;
      INIT:
        nstate = (tr_i) ? TREF : (vn_i) ? VNEU : INIT;
      TREF:
        nstate = SETLAY;
      SETLAY:
        nstate = TRDV;
      TRDV:
        nstate = SETLK;
      SETLK:
        nstate = (ref_old_neuron != 8'd0) ? REFRAC : OFFL;
      REFRAC:
        nstate = TNWV;
      OFFL:
        nstate = (d_l) ? TWRV : OFFL;
      TWRV:
        nstate = TNWV;
      TNWV:
        nstate = NCAP;
      NCAP:
        nstate = (neuron == neu_f) ? HOLD : NINC;
      NINC:
        nstate = TRDV;


      VNEU:
        nstate = VWRV;
      VWRV:
        nstate = VNWV;
      VNWV:
        nstate = HOLD;


      HOLD:
        nstate = CHKSPK;
      CHKSPK:
        nstate = (f_empty != 1'b1) ? REDSPK : DONE;
      REDSPK:
        nstate = SETSPK;
      SETSPK:
        nstate = PARSPK;

      PARSPK:
        nstate = RDVSPK;
      RDVSPK:
        nstate = (ref_old_neuron == 8'd0) ? SPKVSET : CAPSPK;

      SPKVSET:
        nstate = (spike == 1'b1) ? SETREFR : CAPSPK;
      SETREFR:
        nstate = CAPSPK;

      CAPSPK:
        nstate = (synR == neu_f) ? CHKSPK : WRISPK;
      WRISPK:
        nstate = INCSPK;
      INCSPK:
        nstate = PARSPK;

      DONE:
        nstate = WAIT;
      default:
        nstate = IDLE;
    endcase
  end


  always @(pstate)
  begin
    case (pstate)

      IDLE:
      begin
        done = 1'd0;
        r_v = 1'd0;
        w_r = 1'd0;
        w_v = 1'd0;
        r_f = 1'd0;
        w_f = 1'd0;
        neuron = 8'd0;
        ref_new_neuron = 8'd0;
        synC = 8'd0;
        synR = 8'd0;
        tr = 1'd0;
        se = 1'd0;
        vn = 1'd0;
        r_s = 1'd0;
        s_l = 1'd0;
        r_g = 1'd0;
        w_g = 1'd0;
        r_r = 1'd0;
      end
      WAIT:
      begin

      end
      INIT:
      begin
        tr = 1'd0;
        se = 1'd0;
        vn = 1'd0;
      end

      TREF:
      begin
        done = 1'd0;
        mReg = GPB;
        tr   = 1'd1;
      end

      SETLAY:
      begin
        neu_s  = layerMem[8'd0][mReg];
        neu_f  = layerMem[8'd1][mReg];
        neuron = layerMem[8'd0][mReg];
      end
      TRDV:
      begin
        r_v = 1'd1;
        r_r = 1'd1;
        r_g = 1'd1;
      end

      SETLK:
      begin
        r_r = 1'd0;
        s_l = 1'd1;

        r_v = 1'd0;
        r_g = 1'd0;
      end
      REFRAC:
      begin
        ref_new_neuron = (ref_old_neuron == 8'd0) ? 8'd0 : (ref_old_neuron - 8'd1);
        w_r = 1'd1;
      end
      OFFL:
      begin
        s_l = 1'd0;
      end

      TWRV:
      begin
        w_v = 1'd1;
        w_f = 1'd1;
      end

      TNWV:
      begin
        w_r = 1'd0;
        w_v = 1'd0;
        w_f = 1'd0;
      end

      NINC:
      begin
        neuron = neuron + 8'd1;
      end



      VNEU:
      begin
        done = 1'd0;
        vn = 1'd1;
        neuron = GPB;
        r_v = 1'd1;
      end

      VWRV:
      begin
        r_v = 1'd0;
        w_v = 1'd1;
      end

      VNWV:
      begin
        w_v = 1'd0;
        vn  = 1'd0;
      end



      CHKSPK:
      begin
        w_v = 1'd0;
        r_f = 1'b1;
        se  = 1'b0;
        w_r = 1'd0;
        tr  = 1'b0;
      end
      REDSPK:
      begin
        se = 1'd1;
        neu_s = (lay1)? layerMem[8'd0][8'd1]: (lay2)?layerMem[8'd0][8'd2]:layerMem[8'd0][8'd3];
        neu_f = (lay1)? layerMem[8'd1][8'd1]: (lay2)?layerMem[8'd1][8'd2]:layerMem[8'd1][8'd3];
        synR = (lay1) ? layerMem[8'd0][8'd1] : (lay2) ? layerMem[8'd0][8'd2] : layerMem[8'd0][8'd3];
        synC = spike_neuron;
        w_v = 1'b0;
        r_f = 1'b0;
      end
      SETSPK:
      begin
        r_f = 1'b0;
      end
      PARSPK:
      begin
        neuron = synR;
        r_v = 1'd1;
        r_r = 1'd1;
      end
      RDVSPK:
      begin
        r_v = 1'd0;
        r_r = 1'd0;
        r_s = 1'd1;
      end
      SPKVSET:
      begin
        r_s = 1'd0;
        w_v = 1'd1;
        // w_r = (ref_old_neuron == 8'd0) ? 1'd1 : 1'd0;
        // ref_new_neuron = (ref_old_neuron == 8'd0) ? 1'd1 : 1'd0;
      end

      SETREFR:
      begin
        w_v = 1'd0;
        w_r = 1'd1;
        ref_new_neuron = 8'd20;
      end

      CAPSPK:
      begin
        w_v = 1'd0;
        w_r = 1'd0;
      end

      WRISPK:
      begin
        w_v = 1'd0;
        w_r = 1'd0;
      end
      INCSPK:
      begin
        w_r  = 1'd0;
        synR = synR + 1'b1;
      end








      HOLD:
      begin

      end
      DONE:
      begin
        r_f  = 1'b0;
        done = 1'd1;
      end

    endcase
  end

endmodule
