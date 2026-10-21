/* host co-simulation stand-in: register accesses become AXI4-Lite
   transactions on the Verilated snn_board_top (board/tb/cosim/cosim.cpp) */
#pragma once
#include "xil_types.h"
#ifdef __cplusplus
extern "C" {
#endif
void Xil_Out32(UINTPTR addr, u32 value);
u32 Xil_In32(UINTPTR addr);
const volatile u32 *cosim_ddr(UINTPTR addr);
#ifdef __cplusplus
}
#endif
