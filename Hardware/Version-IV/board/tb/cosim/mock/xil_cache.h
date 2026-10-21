/* host co-simulation stand-in */
#pragma once
#include "xil_types.h"
static inline void Xil_DCacheInvalidateRange(UINTPTR a, u32 n) { (void)a; (void)n; }
