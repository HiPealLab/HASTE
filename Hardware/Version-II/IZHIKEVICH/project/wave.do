onerror {resume}
radix define fixed#16#decimal#signed -fixed -fraction 16 -signed -base signed -precision 6
radix define fixed#8#decimal -fixed -fraction 8 -base signed -precision 6
radix define fixed#4#decimal#signed -fixed -fraction 4 -signed -base signed -precision 6
quietly WaveActivateNextPane {} 0
add wave -noupdate -expand -group TB /neuron_tb/ack
add wave -noupdate -expand -group TB /neuron_tb/addr_f
add wave -noupdate -expand -group TB /neuron_tb/ADDR_I
add wave -noupdate -expand -group TB /neuron_tb/ADDR_J
add wave -noupdate -expand -group TB /neuron_tb/ae
add wave -noupdate -expand -group TB /neuron_tb/clk
add wave -noupdate -expand -group TB /neuron_tb/de
add wave -noupdate -expand -group TB /neuron_tb/done
add wave -noupdate -expand -group TB /neuron_tb/fifo_empty
add wave -noupdate -expand -group TB /neuron_tb/fifo_full
add wave -noupdate -expand -group TB -radix unsigned /neuron_tb/I_ADDR
add wave -noupdate -expand -group TB /neuron_tb/Icol
add wave -noupdate -expand -group TB /neuron_tb/input_current
add wave -noupdate -expand -group TB /neuron_tb/input_volt
add wave -noupdate -expand -group TB /neuron_tb/Irow
add wave -noupdate -expand -group TB /neuron_tb/J_ADDR
add wave -noupdate -expand -group TB /neuron_tb/Nneuron
add wave -noupdate -expand -group TB /neuron_tb/read_f
add wave -noupdate -expand -group TB /neuron_tb/rst
add wave -noupdate -expand -group TB /neuron_tb/spike
add wave -noupdate -expand -group TB /neuron_tb/tr
add wave -noupdate -expand -group TB /neuron_tb/ve
add wave -noupdate -expand -group TB /neuron_tb/vn
add wave -noupdate -expand -group TB /neuron_tb/write_f
add wave -noupdate -group FIFO /neuron_tb/fifo/ADDR_WIDTH
add wave -noupdate -group FIFO /neuron_tb/fifo/clk
add wave -noupdate -group FIFO /neuron_tb/fifo/DEPTH
add wave -noupdate -group FIFO -radix unsigned /neuron_tb/fifo/din
add wave -noupdate -group FIFO -radix unsigned /neuron_tb/fifo/dout
add wave -noupdate -group FIFO /neuron_tb/fifo/empty
add wave -noupdate -group FIFO /neuron_tb/fifo/full
add wave -noupdate -group FIFO -radix unsigned /neuron_tb/fifo/mem
add wave -noupdate -group FIFO /neuron_tb/fifo/rd_en
add wave -noupdate -group FIFO /neuron_tb/fifo/rd_ptr
add wave -noupdate -group FIFO /neuron_tb/fifo/rst
add wave -noupdate -group FIFO /neuron_tb/fifo/spike_file
add wave -noupdate -group FIFO /neuron_tb/fifo/WIDTH
add wave -noupdate -group FIFO /neuron_tb/fifo/wr_en
add wave -noupdate -group FIFO /neuron_tb/fifo/wr_ptr
add wave -noupdate -group LIF /neuron_tb/lif/ack
add wave -noupdate -group LIF /neuron_tb/lif/ae
add wave -noupdate -group LIF /neuron_tb/lif/clk
add wave -noupdate -group LIF /neuron_tb/lif/de
add wave -noupdate -group LIF /neuron_tb/lif/done
add wave -noupdate -group LIF /neuron_tb/lif/e_f
add wave -noupdate -group LIF /neuron_tb/lif/FINISHN
add wave -noupdate -group LIF /neuron_tb/lif/I_ADDR
add wave -noupdate -group LIF /neuron_tb/lif/IADDR
add wave -noupdate -group LIF /neuron_tb/lif/input_current
add wave -noupdate -group LIF /neuron_tb/lif/input_volt
add wave -noupdate -group LIF /neuron_tb/lif/J_ADDR
add wave -noupdate -group LIF /neuron_tb/lif/JADDR
add wave -noupdate -group LIF /neuron_tb/lif/lay1
add wave -noupdate -group LIF /neuron_tb/lif/lay2
add wave -noupdate -group LIF /neuron_tb/lif/lay3
add wave -noupdate -group LIF /neuron_tb/lif/n_f
add wave -noupdate -group LIF /neuron_tb/lif/nDendrite
add wave -noupdate -group LIF /neuron_tb/lif/nRefractory
add wave -noupdate -group LIF /neuron_tb/lif/nVolt
add wave -noupdate -group LIF /neuron_tb/lif/r_f
add wave -noupdate -group LIF /neuron_tb/lif/rst
add wave -noupdate -group LIF /neuron_tb/lif/spike
add wave -noupdate -group LIF /neuron_tb/lif/spikeN
add wave -noupdate -group LIF /neuron_tb/lif/STARTN
add wave -noupdate -group LIF /neuron_tb/lif/tr
add wave -noupdate -group LIF /neuron_tb/lif/ve
add wave -noupdate -group LIF /neuron_tb/lif/vn
add wave -noupdate -group LIF /neuron_tb/lif/w_f
add wave -noupdate -expand -group State /neuron_tb/lif/pstate
add wave -noupdate -expand -group State /neuron_tb/lif/nstate
add wave -noupdate -expand -group State /neuron_tb/lif/fstate
add wave -noupdate -expand -group State /neuron_tb/lif/hstate
TreeUpdate [SetDefaultTree]
WaveRestoreCursors {{Cursor 1} {575 ns} 0}
quietly wave cursor active 1
configure wave -namecolwidth 150
configure wave -valuecolwidth 100
configure wave -justifyvalue left
configure wave -signalnamewidth 1
configure wave -snapdistance 10
configure wave -datasetprefix 0
configure wave -rowmargin 4
configure wave -childrowmargin 2
configure wave -gridoffset 0
configure wave -gridperiod 1
configure wave -griddelta 40
configure wave -timeline 0
configure wave -timelineunits ns
update
WaveRestoreZoom {1077 ns} {1261 ns}
