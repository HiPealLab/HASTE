# 50 MHz reporting clock (20 ns).  Fmax is derived from the routed WNS.
create_clock -name clk -period 20.000 [get_ports clk]
# out-of-context: model generic I/O timing as 40% of the period
set_input_delay  -clock clk 8.000 [get_ports -filter {DIRECTION == IN && NAME != clk}]
set_output_delay -clock clk 8.000 [get_ports -filter {DIRECTION == OUT}]
