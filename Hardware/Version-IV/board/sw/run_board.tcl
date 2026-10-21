# HASTE Version-IV -- program the board over JTAG and start the measurement app (XSCT)
#
#   cd Hardware/Version-IV
#   xsct board/sw/run_board.tcl                                    # 50 MHz build
#   xsct board/sw/run_board.tcl out=board/vivado/out/lif_64x10_100MHz
#
# Start the UART terminal/logger BEFORE running this (see MANUAL_BOARD.md).
# Board: boot-mode jumper on JTAG.  Steps: system reset, configure the PL
# with snn_board.bit, ps7_init (DDR, clocks incl. FCLK_CLK0, MIO, UART),
# ps7_post_config (PS-PL level shifters), download the ELF, the spike and
# label data into DDR, run.
# Options: out=<build_board.tcl output dir>  (default board/vivado/out/lif_64x10_50MHz)
#          ws=<vitis workspace>              (default <out>/vitis_ws)
#          data=<dir with spikes.bin, labels.bin> (default board/data)
#          spikes_addr=0x08000000 labels_addr=0x0F000000 (= SPIKES_ADDR/LABELS_ADDR in main.c)
#          pl_only=1  only configure the PL + ps7_init, do not start the app
set SW [file normalize [file dirname [info script]]]
set V4 [file normalize [file join $SW .. ..]]
set OUT [file join $V4 board vivado out lif_64x10_50MHz]
set WS ""; set DATA [file join $V4 board data]
set SPIKES_ADDR 0x08000000; set LABELS_ADDR 0x0F000000; set PL_ONLY 0
foreach a $argv {
  if {![regexp {^([a-z_]+)=(.*)$} $a -> k v]} { error "bad argument '$a' (use key=value)" }
  switch -- $k {
    out { set OUT [file normalize $v] } ws { set WS [file normalize $v] } data { set DATA [file normalize $v] }
    spikes_addr { set SPIKES_ADDR $v } labels_addr { set LABELS_ADDR $v } pl_only { set PL_ONLY $v }
    default { error "unknown option $k" }
  }
}
if {$WS eq ""} { set WS [file join $OUT vitis_ws] }
set BIT [file join $OUT snn_board.bit]
set ELF [lindex [glob -nocomplain [file join $WS snn_app Release snn_app.elf] [file join $WS snn_app Debug snn_app.elf]] 0]
proc find_file {dir name} {
  foreach f [glob -nocomplain -directory $dir *] {
    if {[file isdirectory $f]} { set r [find_file $f $name]; if {$r ne ""} { return $r } } elseif {[file tail $f] eq $name} { return $f }
  }
  return ""
}
set PS7INIT [find_file [file join $WS snn_plat] ps7_init.tcl]
foreach {what f} [list bitstream $BIT ps7_init.tcl $PS7INIT] {
  if {$f eq "" || ![file exists $f]} { error "$what not found (out=$OUT ws=$WS)" }
}
if {!$PL_ONLY} {
  foreach {what f} [list ELF $ELF spikes.bin [file join $DATA spikes.bin] labels.bin [file join $DATA labels.bin]] {
    if {$f eq "" || ![file exists $f]} { error "$what not found ($f) -- run create_app.tcl / make_bin.py" }
  }
}
puts "bit=$BIT\nps7_init=$PS7INIT\nelf=$ELF\ndata=$DATA"

connect
targets -set -nocase -filter {name =~ "APU*"}
rst -system
after 2000
targets -set -nocase -filter {name =~ "xc7z*"}
fpga -file $BIT
targets -set -nocase -filter {name =~ "APU*"}
source $PS7INIT
ps7_init
ps7_post_config
if {$PL_ONLY} { puts "PL configured, PS initialised; app not started"; exit }
targets -set -nocase -filter {name =~ "*A9*#0"}
rst -processor
dow $ELF
dow -data [file join $DATA spikes.bin] $SPIKES_ADDR
dow -data [file join $DATA labels.bin] $LABELS_ADDR
con
puts "app running -- watch the UART terminal"
