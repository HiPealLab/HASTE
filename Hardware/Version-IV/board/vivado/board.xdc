# HASTE Version-IV on-board build -- constraints.
#
# Intentionally (almost) empty: the only clock is FCLK_CLK0 of the Zynq PS,
# whose period constraint (clk_fpga_0) is created automatically by the
# processing_system7 IP from CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ, and the
# design has no PL pins (DDR and MIO are fixed PS pins).  Nothing to add for
# a standard xc7z010 board.
