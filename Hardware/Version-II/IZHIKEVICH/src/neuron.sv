`include "dendrites.svh"
package file_pkg;
  integer spike_file;
endpackage
module neuron (
    input  logic               clk,
    input  logic               rst,
    input  logic               tr,
    input  logic               ve,
    input  logic               vn,
    input  logic               de,
    input  logic               ae,
    input  logic        [ 7:0] IADDR,
    input  logic        [ 7:0] JADDR,
    output reg unsigned [ 7:0] I_ADDR,
    output reg unsigned [ 7:0] J_ADDR,
    output reg                 r_f,
    output reg                 w_f,
    input                      e_f,
    input               [ 7:0] n_f,
    input  logic        [15:0] input_current,
    input  logic        [15:0] input_volt,
    output logic               spike,
    output logic               ack,
    output logic               done
);

  typedef enum logic [4:0] {
    INIT  = 5'd0,
    IDLE  = 5'd1,
    PREP  = 5'd2,
    LEAK  = 5'd3,
    NORM  = 5'd4,
    REFR  = 5'd5,
    CAL1  = 5'd6,
    CAL2  = 5'd7,
    CAL3  = 5'd8,
    CAL4  = 5'd9,
    CAL5  = 5'd10,
    DVDT  = 5'd11,
    CAL6  = 5'd12,
    CAL7  = 5'd13,
    IINJ  = 5'd14,
    VSET  = 5'd15,
    EVAL  = 5'd16,
    DENT  = 5'd17,
    GETV  = 5'd18,
    INCN  = 5'd19,
    NEWV  = 5'd20,
    SPIK  = 5'd21,
    DCAP  = 5'd22,
    VCAP  = 5'd23,
    SPK1  = 5'd24,
    SPK2  = 5'd25,
    SPK3  = 5'd26,
    SPK4  = 5'd27,
    SPK5  = 5'd28,
    READ  = 5'd29,
    NVSET = 5'd30,
    DONE  = 5'd31
  } state_t;
  state_t pstate, nstate, fstate, hstate;

  always @(posedge clk or posedge rst) begin
    if (rst) pstate <= IDLE;
    else pstate <= nstate;
  end

  import file_pkg::*;




  reg [7:0] STARTN;
  reg [7:0] FINISHN;
  reg [7:0] spikeN;

//dynass
  wire lay1, lay2, lay3;
  assign lay1 = ((spikeN >= SL1) && (spikeN <= FL1));
  assign lay2 = ((spikeN >= SL2) && (spikeN <= FL2));
  assign lay3 = ((spikeN >= SL3) && (spikeN <= FL3));
//dynass

  reg signed [63:0] firstTermTemp;
  reg signed [63:0] secondTermTemp;

  reg signed [15:0] firstTerm;
  reg signed [15:0] secondTerm;

  reg signed [39:0] recoTemp;
  reg signed [31:0] secondRec;

  reg signed [31:0] V2coeff = 32'd2621;
  reg signed [31:0] V1coeff = 32'd327680;
  reg signed [31:0] V2val;
  reg signed [31:0] V1val;

  reg signed [31:0] nVolt;
  reg signed [31:0] dvdt;
  reg signed [7:0] nDendrite;

  reg [7:0] nRefractory;

  reg signed [31:0] nreco;
  reg signed [31:0] nvreset;
  reg unsigned [7:0] ntau;
  reg unsigned [7:0] ngain;
  reg unsigned [7:0] nurest;

  always @(*) begin
    case (pstate)
      IDLE: begin
        nstate = (tr) ? INIT : (ve) ? INIT : (de) ? INIT : (ae) ? INIT : (vn) ? INIT : IDLE;
        fstate = (tr) ? CAL1 : (ve) ? IINJ : (de) ? DENT : (ae) ? READ : (vn) ? NVSET : IDLE;
      end
      INIT: nstate = PREP;
      PREP: nstate = fstate;
      NVSET: nstate = DONE;
      CAL1: nstate = CAL2;
      CAL2: nstate = CAL3;
      CAL3: nstate = CAL4;
      CAL4: nstate = CAL5;
      CAL5: nstate = DVDT;
      DVDT: nstate = CAL6;
      CAL6: nstate = CAL7;
      CAL7: nstate = VSET;
      IINJ: nstate = VSET;
      VSET: nstate = SPK1;
      SPK1: nstate = (e_f == 1'd1) ? DONE : SPK2;
      SPK2: nstate = SPK3;
      SPK3: nstate = SPK4;
      SPK4: nstate = NEWV;
      DENT: nstate = VSET;
      READ: nstate = GETV;
      GETV: nstate = NEWV;
      INCN: nstate = NEWV;
      NEWV: nstate = SPIK;
      SPIK: nstate = DCAP;
      DCAP: nstate = (I_ADDR == FINISHN) ? SPK1 : VCAP;
      VCAP: nstate = INCN;
      DONE: nstate = IDLE;
      default: nstate = IDLE;
    endcase
  end

  always @(pstate) begin
    spike <= 1'd0;
    done  <= 1'd0;
    ack   <= 1'd0;
    r_f   <= 1'd0;
    w_f   <= 1'd0;
    case (pstate)
      IDLE: begin
        I_ADDR <= IADDR;
        J_ADDR <= JADDR;
      end
      INIT: begin
        I_ADDR <= IADDR;
        J_ADDR <= JADDR;
      end
      PREP: begin
        ack <= 1'd1;
        nVolt <= neuron_reg[I_ADDR].volt;
        nDendrite <= neuron_reg[I_ADDR].dendrite[J_ADDR];
        nvreset <= neuron_reg[I_ADDR].vreset;
        ntau <= neuron_reg[I_ADDR].tau;
        ngain <= neuron_reg[I_ADDR].gain;
        nurest <= neuron_reg[I_ADDR].urest;
        nreco <= neuron_reg[I_ADDR].reco;
      end
      NVSET: begin
        neuron_reg[I_ADDR].volt <= {{8{input_volt[15]}}, {input_volt}, {8'd0}};
      end
      CAL1: begin
        firstTermTemp  <= nVolt * nVolt;
        secondTermTemp <= nVolt * V1coeff;
        recoTemp       <= ngain * nVolt;
      end
      CAL2: begin
        secondRec <= recoTemp[39:8];
        firstTermTemp <= firstTermTemp[47:16];
      end
      CAL3: begin
        recoTemp <= ntau * (secondRec - nreco);
        firstTermTemp <= firstTermTemp * V2coeff;
      end
      CAL4: begin
        V2val <= firstTermTemp[47:16];
        V1val <= secondTermTemp[47:16];
        secondRec <= recoTemp[39:8];
      end
      CAL5: begin
        dvdt <= V2val + V1val + {{16'd140}, {16'd0}} - nreco;
      end
      CAL6: begin
        secondRec <= {{7{secondRec[31]}}, {secondRec[31:7]}};
        dvdt <= {{7{dvdt[31]}}, {dvdt[31:7]}};
      end
      CAL7: begin
        nVolt <= (nVolt - dvdt);
        nreco <= (nreco - secondRec);
      end
      IINJ: begin
        nVolt <= nVolt + {{input_current}, {16'd0}};
      end
      DENT: begin
        nVolt <= nVolt + {{12{nDendrite[7]}}, {nDendrite}, {12'd0}};
      end
      READ: begin
        I_ADDR  <= 8'd0;
        FINISHN <= FL1;
      end
      GETV: begin
        nDendrite <= neuron_reg[I_ADDR].dendrite[J_ADDR];
        nVolt <= neuron_reg[I_ADDR].volt;
        nRefractory <= neuron_reg[I_ADDR].refractory;
      end
      INCN: begin
        I_ADDR <= I_ADDR + 8'd1;
      end
      NEWV: begin
        nVolt <=(nRefractory != 8'd0)? (nVolt):(nVolt + {{12{nDendrite[7]}}, {nDendrite}, {12'd0}});
      end
      SPIK: begin
        neuron_reg[I_ADDR].volt <= (nVolt >= THRESHOLD) ? nvreset : nVolt;
        neuron_reg[I_ADDR].reco <=(nVolt >= THRESHOLD) ? (nreco + {{12{nurest[7]}}, {nurest}, {12'd0}}):nreco;
        spike <= (nVolt >= THRESHOLD) ? 1'd1 : 1'd0;
        if (nVolt >= THRESHOLD) begin
          if (I_ADDR < SLAST) w_f <= 1'd1;
          if (I_ADDR >= SLAST) $fdisplay(spike_file, "din = %0d", (I_ADDR - SLAST));
        end
      end
      VSET: begin
        neuron_reg[I_ADDR].volt <= (nVolt >= THRESHOLD) ? nvreset : nVolt;
        neuron_reg[I_ADDR].reco <=(nVolt >= THRESHOLD) ? (nreco + {{12{nurest[7]}}, {nurest}, {12'd0}}):nreco;
        spike <= (nVolt >= THRESHOLD) ? 1'd1 : 1'd0;
        if (nVolt >= THRESHOLD) begin
          if (I_ADDR < SLAST) w_f <= 1'd1;
          if (I_ADDR >= SLAST) $fdisplay(spike_file, "din = %0d", (I_ADDR - SLAST));
        end
      end
      VCAP: begin
        nDendrite <= neuron_reg[I_ADDR+8'd1].dendrite[J_ADDR];
        nVolt <= neuron_reg[I_ADDR+8'd1].volt;
        nRefractory <= neuron_reg[I_ADDR+8'd1].refractory;
      end
      SPK1: begin
        r_f <= 1'd1;
      end
      SPK2: begin
        spikeN <= n_f;
      end
      SPK3: begin
//dynlay
        J_ADDR  <= (lay1) ? (spikeN - SL1) : (lay2) ? (spikeN - SL2) : 8'd255;
        I_ADDR  <= (lay1) ? SL2 : (lay2) ? SL3 : 8'd255;
        FINISHN <= (lay1) ? FL2 : (lay2) ? FL3 : 8'd255;
//dynlay
      end
      SPK4: begin
        nDendrite <= neuron_reg[I_ADDR].dendrite[J_ADDR];
        nVolt <= neuron_reg[I_ADDR].volt;
        nRefractory <= neuron_reg[I_ADDR].refractory;
      end
      SPK5: begin
      end
      DONE: begin
        done <= 1'd1;
      end
    endcase
  end
endmodule


module fifo (
    // Inputs
    clk,
    rst,
    wr_en,
    rd_en,
    din,

    // Outputs
    dout,
    full,
    empty
);

  //================================================================
  // Port Declarations
  //================================================================
  input clk;
  input rst;
  input wr_en;
  input rd_en;
  input [7:0] din;

  output reg [7:0] dout;
  output full;
  output empty;

  //================================================================
  // Internal Parameters and Signals
  //================================================================
  localparam DEPTH = 256;
  localparam WIDTH = 8;
  localparam ADDR_WIDTH = 8;  // $clog2(DEPTH)

  reg [WIDTH-1:0] mem[DEPTH];

  reg [ADDR_WIDTH:0] wr_ptr;
  reg [ADDR_WIDTH:0] rd_ptr;


  //================================================================
  // Logic Implementation
  //================================================================

  // Write Operation
  integer spike_file;

  initial begin
    // Open file for writing (overwrite each run). Use "a" for append.
    spike_file = $fopen("output.txt", "w");
    if (spike_file == 0) begin
      $display("ERROR: Could not open file!");
      $finish;
    end
  end

  always @(posedge clk or posedge rst) begin
    if (rst) begin
      wr_ptr <= 0;
    end else if (wr_en && !full) begin
      mem[wr_ptr[ADDR_WIDTH-1:0]] <= din;
      wr_ptr <= wr_ptr + 1;
      if (din >= 64) begin
        // Write into file instead of console
        $fdisplay(spike_file, "din = %0d", (din - 64));
      end
    end
  end


  // Read Operation
  always @(posedge clk or posedge rst) begin
    if (rst) begin
      rd_ptr <= 0;
      dout   <= 0;
    end else if (rd_en && !empty) begin
      dout   <= mem[rd_ptr[ADDR_WIDTH-1:0]];
      rd_ptr <= rd_ptr + 1;
    end
  end

  // Full and Empty Logic
  assign full = (wr_ptr[ADDR_WIDTH] != rd_ptr[ADDR_WIDTH]) && (wr_ptr[ADDR_WIDTH-1:0] == rd_ptr[ADDR_WIDTH-1:0]);
  assign empty = (wr_ptr == rd_ptr);

endmodule
