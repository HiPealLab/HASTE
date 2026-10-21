/* host co-simulation stand-in: global timer = 6.5 x the 50 MHz PL clock
   (325 MHz, as on a 650/667 MHz Zynq-7010 with CPU_3x2x clock) */
#pragma once
#include "xil_types.h"
typedef u64 XTime;
#define COUNTS_PER_SECOND 325000000u
#ifdef __cplusplus
extern "C" {
#endif
void XTime_GetTime(XTime *t);
#ifdef __cplusplus
}
#endif
