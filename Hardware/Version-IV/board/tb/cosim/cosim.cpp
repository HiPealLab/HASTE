// HASTE Version-IV -- host co-simulation of the bare-metal application.
//
// Compiles board/sw/main.c UNCHANGED for the host (mock BSP headers in
// mock/) and runs it against the Verilated PL wrapper snn_board_top: every
// Xil_Out32/Xil_In32 becomes an AXI4-Lite transaction, XTime counts 6.5
// ticks per 50 MHz PL cycle, and the DDR holds spikes.bin / labels.bin at
// SPIKES_ADDR / LABELS_ADDR as after "dow -data".  stdout = the UART log.
// usage: Vsnn_board_top spikes.bin labels.bin   (env COSIM_AXI_LAT = extra
//        cycles per register access, default 8, a rough GP0 interconnect delay)
#include <cstdio>
#include <cstdlib>
#include <vector>
#include "verilated.h"
#include "Vsnn_board_top.h"
#include "xil_io.h"
#include "xtime_l.h"

extern "C" int app_main(void);

static Vsnn_board_top *top;
static uint64_t ncyc = 0;
static int axi_lat = 8;
static std::vector<u32> spikes, labels;

static void low() { top->s_axi_aclk = 0; top->eval(); }
static void rise() { top->s_axi_aclk = 1; top->eval(); ncyc++; }
static void cycle() { low(); rise(); }

static void check(UINTPTR a) {
  if (a < SNN_BASE || a >= SNN_BASE + 0x10000) { fprintf(stderr, "bad PL address %lx\n", (unsigned long)a); exit(2); }
}

extern "C" void Xil_Out32(UINTPTR a, u32 v) {
  check(a);
  for (int i = 0; i < axi_lat; i++) cycle();
  top->s_axi_awaddr = a & 0xFFFF; top->s_axi_awvalid = 1;
  top->s_axi_wdata = v; top->s_axi_wstrb = 0xF; top->s_axi_wvalid = 1; top->s_axi_bready = 1;
  for (;;) { low(); bool hs = top->s_axi_awready && top->s_axi_wready; rise(); if (hs) break; }
  top->s_axi_awvalid = 0; top->s_axi_wvalid = 0;
  for (;;) { low(); bool b = top->s_axi_bvalid; rise(); if (b) break; }
  top->s_axi_bready = 0;
}

extern "C" u32 Xil_In32(UINTPTR a) {
  check(a);
  for (int i = 0; i < axi_lat; i++) cycle();
  top->s_axi_araddr = a & 0xFFFF; top->s_axi_arvalid = 1; top->s_axi_rready = 1;
  for (;;) { low(); bool hs = top->s_axi_arready; rise(); if (hs) break; }
  top->s_axi_arvalid = 0;
  u32 d;
  for (;;) { low(); bool v = top->s_axi_rvalid; d = top->s_axi_rdata; rise(); if (v) break; }
  top->s_axi_rready = 0;
  return d;
}

extern "C" void XTime_GetTime(XTime *t) {
  cycle();  // time only advances with the clock
  *t = ncyc * 13 / 2;
}

extern "C" const volatile u32 *cosim_ddr(UINTPTR a) {
  if (a >= SPIKES_ADDR && a < SPIKES_ADDR + 4 * spikes.size()) return &spikes[(a - SPIKES_ADDR) / 4];
  if (a >= LABELS_ADDR && a < LABELS_ADDR + 4 * labels.size()) return &labels[(a - LABELS_ADDR) / 4];
  fprintf(stderr, "bad DDR address %lx\n", (unsigned long)a);
  exit(2);
}

static std::vector<u32> load(const char *fn) {
  FILE *f = fopen(fn, "rb");
  if (!f) { perror(fn); exit(2); }
  std::vector<u32> v;
  u32 w = 0; int n = 0, c;
  while ((c = fgetc(f)) != EOF) { w |= (u32)c << (8 * n); if (++n == 4) { v.push_back(w); w = 0; n = 0; } }
  if (n) v.push_back(w);
  v.push_back(0);
  fclose(f);
  return v;
}

int main(int argc, char **argv) {
  if (argc < 3) { fprintf(stderr, "usage: %s spikes.bin labels.bin\n", argv[0]); return 2; }
  spikes = load(argv[1]);
  labels = load(argv[2]);
  if (getenv("COSIM_AXI_LAT")) axi_lat = atoi(getenv("COSIM_AXI_LAT"));
  top = new Vsnn_board_top;
  top->s_axi_aresetn = 0;
  for (int i = 0; i < 16; i++) cycle();
  top->s_axi_aresetn = 1;
  for (int i = 0; i < 16; i++) cycle();
  int rc = app_main();
  fflush(stdout);
  fprintf(stderr, "cosim: %llu PL cycles simulated\n", (unsigned long long)ncyc);
  top->final();
  delete top;
  return rc;
}
