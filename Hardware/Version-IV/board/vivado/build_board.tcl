# HASTE Version-IV -- on-board build: Zynq PS7 + AXI4-Lite + snn_board wrapper
#
#   cd Hardware/Version-IV
#   vivado -mode batch -source board/vivado/build_board.tcl                      # defaults below
#   vivado -mode batch -source board/vivado/build_board.tcl -tclargs fclk=100    # 100 MHz PL clock
#   vivado -mode batch -source board/vivado/build_board.tcl -tclargs saif=auto   # + SAIF power
#
# Options (-tclargs key=value ...), all optional:
#   cfg=lif_64x10            network (build/<cfg>/: params.svh, syn.mem, layer.mem)
#   fclk=50                  FCLK_CLK0 in MHz (PS7 picks the nearest achievable value;
#                            the actual value is printed and written to summary.txt)
#   board_part=digilentinc.com:zybo-z7-10:part0:1.2
#                            Vivado board part; if this exact version is not installed the
#                            newest installed version of the same board is used
#   board_repo=<dir>         folder with Digilent board files (vivado-boards/new/board_files)
#                            if they are not installed in Vivado
#   part=xc7z010clg400-1     only used when board_part=none
#   ps7_preset=<file.tcl>    only with board_part=none: Tcl file with
#                            "set_property -dict {...} [get_bd_cells processing_system7_0]"
#                            holding the DDR/MIO settings of your board
#   saif=<file>|auto         also report power with switching activity from a SAIF of
#                            tb/tb_snn.sv (vivado/saif.tcl); auto = vivado/out/<cfg>/activity.saif
#                            if it exists (else skipped with a warning)
#   jobs=4                   parallel Vivado jobs
#   base=0x43C00000          AXI base address of the wrapper (= SNN_BASE in board/sw/main.c)
#
# Output: board/vivado/out/<cfg>_<fclk>MHz/
#   snn_board.bit  snn_board.xsa (with bitstream; for Vitis/XSCT)
#   utilization.rpt utilization_hier.rpt timing_summary.rpt power_vectorless.rpt
#   [power_saif.rpt] summary.txt  proj/ (Vivado project)
# The core RTL (rtl/) and build/<cfg>/ are used unchanged.

# ---------------------------------------------------------------- defaults (edit here or use -tclargs)
set CFG        lif_64x10
set FCLK_MHZ   50
set BOARD_PART digilentinc.com:zybo-z7-10:part0:1.2
set BOARD_REPO ""
set PART       xc7z010clg400-1
set PS7_PRESET ""
set SAIF       ""
set JOBS       4
set BASE_ADDR  0x43C00000

foreach a $argv {
  if {![regexp {^([a-z_0-9]+)=(.*)$} $a -> k v]} { error "bad argument '$a' (use key=value)" }
  switch -- $k {
    cfg        { set CFG $v }
    fclk       { set FCLK_MHZ $v }
    board_part { set BOARD_PART $v }
    board_repo { set BOARD_REPO $v }
    part       { set PART $v }
    ps7_preset { set PS7_PRESET $v }
    saif       { set SAIF $v }
    jobs       { set JOBS $v }
    base       { set BASE_ADDR $v }
    default    { error "unknown option '$k'" }
  }
}

set V4   [file normalize [file join [file dirname [info script]] .. ..]]
set B    [file join $V4 build $CFG]
set OUT  [file join $V4 board vivado out ${CFG}_${FCLK_MHZ}MHz]
set PROJ [file join $OUT proj]
set model [lindex [split $CFG _] 0]
if {$SAIF eq "auto"} {
  set SAIF [file join $V4 vivado out $CFG activity.saif]
  if {![file exists $SAIF]} { puts "WARNING: saif=auto but $SAIF does not exist -- vectorless power only"; set SAIF "" }
}
if {$SAIF ne "" && ![file exists $SAIF]} { error "SAIF file not found: $SAIF (run vivado/saif.tcl first)" }
foreach f [list params.svh syn.mem layer.mem] {
  if {![file exists [file join $B $f]]} { error "missing $B/$f -- the shipped build/ folder is incomplete" }
}
file mkdir $OUT

# ---------------------------------------------------------------- project + board
if {$BOARD_REPO ne ""} { set_param board.repoPaths [list [file normalize $BOARD_REPO]] }
if {$BOARD_PART ne "none"} {
  set bp [get_board_parts -quiet $BOARD_PART]
  if {$bp eq ""} {
    set base [join [lrange [split $BOARD_PART :] 0 2] :]
    set bp [lindex [lsort -dictionary [get_board_parts -quiet ${base}:*]] end]
    if {$bp eq ""} {
      error "board part $BOARD_PART is not installed. Install the Digilent board files\
             (git clone https://github.com/Digilent/vivado-boards) and pass\
             board_repo=<clone>/new/board_files, or see board/MANUAL_BOARD.md."
    }
    puts "NOTE: $BOARD_PART not found, using $bp"
  }
  set BOARD_PART $bp
  set PART [get_property PART_NAME [get_board_parts $BOARD_PART]]
}
if {![string match xc7z010* $PART]} { puts "WARNING: part $PART is not an xc7z010" }
puts "board_part=$BOARD_PART part=$PART cfg=$CFG fclk=${FCLK_MHZ}MHz out=$OUT"

catch {close_project}
create_project -force snn_board $PROJ -part $PART
if {$BOARD_PART ne "none"} { set_property board_part $BOARD_PART [current_project] }
set_property target_language Verilog [current_project]

# a memory image that cannot be found must stop the run (else: empty weights)
set_msg_config -id {Synth 8-4445} -new_severity {ERROR}

set srcs [list [file join $V4 rtl snn_fifo.sv] [file join $V4 rtl snn_${model}.sv] \
               [file join $V4 board rtl snn_board.sv] [file join $V4 board rtl snn_board_top.v]]
add_files -norecurse -fileset sources_1 $srcs
foreach m [list [file join $B syn.mem] [file join $B layer.mem]] {
  add_files -norecurse -fileset sources_1 $m
  set_property FILE_TYPE {Memory File} [get_files $m]
}
set_property include_dirs [list $B] [get_filesets sources_1]
set defs [list MODEL_[string toupper $model]]
set_property verilog_define $defs [get_filesets sources_1]
add_files -fileset constrs_1 -norecurse [file join $V4 board vivado board.xdc]
update_compile_order -fileset sources_1

# ---------------------------------------------------------------- block design
create_bd_design design_1
set ps [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 processing_system7_0]
if {$BOARD_PART ne "none"} {
  # board preset = DDR timing, MIO (UART1 on the Zybo USB-UART), clocks of the board
  apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps
} else {
  if {$PS7_PRESET eq ""} { error "board_part=none needs ps7_preset=<file.tcl> (DDR/MIO settings of your board)" }
  apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "0" Master "Disable" Slave "Disable"} $ps
  source $PS7_PRESET
}
set_property -dict [list CONFIG.PCW_USE_M_AXI_GP0 {1} CONFIG.PCW_EN_CLK0_PORT {1} CONFIG.PCW_EN_RST0_PORT {1} \
  CONFIG.PCW_FPGA0_PERIPHERAL_FREQMHZ $FCLK_MHZ] $ps
set fclk_act [get_property CONFIG.PCW_ACT_FPGA0_PERIPHERAL_FREQMHZ $ps]
puts "FCLK_CLK0 requested ${FCLK_MHZ} MHz, actual $fclk_act MHz"

create_bd_cell -type module -reference snn_board_top snn_0
# AXI interconnect + proc_sys_reset, FCLK_CLK0 on all clocks
apply_bd_automation -rule xilinx.com:bd_rule:axi4 -config [list Clk_master {Auto} Clk_slave {Auto} Clk_xbar {Auto} \
  Master {/processing_system7_0/M_AXI_GP0} Slave {/snn_0/s_axi} ddr_seg {Auto} intc_ip {New AXI Interconnect} \
  master_apm {0}] [get_bd_intf_pins snn_0/s_axi]
set segs [get_bd_addr_segs -of_objects [get_bd_addr_spaces processing_system7_0/Data] -filter {NAME =~ *snn_0*}]
if {[llength $segs] != 1} { error "could not find the address segment of snn_0 ($segs)" }
set_property range 64K $segs
set_property offset $BASE_ADDR $segs
validate_bd_design
save_bd_design
set bdf [get_files design_1.bd]
# synthesise the BD together with the top (one run that sees the .mem Memory Files)
set_property synth_checkpoint_mode None $bdf
generate_target all $bdf
set wrapper [make_wrapper -files $bdf -top]
add_files -norecurse $wrapper
set_property top design_1_wrapper [get_filesets sources_1]
update_compile_order -fileset sources_1

# ---------------------------------------------------------------- synth / impl / bitstream
launch_runs synth_1 -jobs $JOBS
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synthesis failed, see $PROJ/snn_board.runs/synth_1/runme.log" }
set slog [file join $PROJ snn_board.runs synth_1 runme.log]
if {[file exists $slog]} {
  set fh [open $slog r]; set txt [read $fh]; close $fh
  if {[regexp {Synth 8-4445} $txt]} { error "a memory image could not be read (Synth 8-4445), see $slog" }
  foreach line [split $txt "\n"] {
    if {[regexp {readmem|\.mem} $line] && [regexp {INFO|WARNING} $line]} { puts "synth: $line" }
  }
}
launch_runs impl_1 -to_step write_bitstream -jobs $JOBS
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "implementation failed, see $PROJ/snn_board.runs/impl_1/runme.log" }

open_run impl_1
report_utilization               -file [file join $OUT utilization.rpt]
report_utilization -hierarchical -file [file join $OUT utilization_hier.rpt]
report_timing_summary -max_paths 10 -report_unconstrained -file [file join $OUT timing_summary.rpt]
# default (vectorless) power estimate of the whole board design
proc power_report {f} {
  if {[catch {report_power -hierarchical_depth 8 -file $f} err]} {
    puts "report_power -hierarchical_depth not accepted ($err); plain report_power"
    report_power -file $f
  }
}
catch {reset_switching_activity -all}
power_report [file join $OUT power_vectorless.rpt]

set core [get_cells -hier -quiet -filter {NAME =~ *u_board/u_core}]
puts "core instance: $core"

proc saif_for_core {src dst core_path} {
  # Re-root the activity of /tb_snn/dut (vivado/saif.tcl) onto the core instance of
  # this design: <header> (INSTANCE design_1_wrapper (INSTANCE design_1_i ... (INSTANCE u_core <dut>)))
  set fh [open $src r]; set txt [read $fh]; close $fh
  if {![regexp -indices {\(INSTANCE\s+dut\M} $txt m]} { error "no (INSTANCE dut ...) in $src" }
  set s [lindex $m 0]
  set depth 0; set e -1; set n [string length $txt]
  for {set i $s} {$i < $n} {incr i} {
    set c [string index $txt $i]
    if {$c eq "("} { incr depth } elseif {$c eq ")"} { incr depth -1; if {$depth == 0} { set e $i; break } }
  }
  if {$e < 0} { error "unbalanced SAIF $src" }
  set block [string range $txt $s $e]
  regexp -indices {\(INSTANCE} $txt h
  set header [string range $txt 0 [expr {[lindex $h 0] - 1}]]
  set parts [split $core_path /]
  set opens "(INSTANCE design_1_wrapper\n"
  foreach p [lrange $parts 0 end-1] { append opens "(INSTANCE $p\n" }
  regsub {^\(INSTANCE\s+dut} $block "(INSTANCE [lindex $parts end]" block
  set fo [open $dst w]
  puts $fo "$header$opens$block[string repeat ")" [expr {[llength $parts]}]]\n)"
  close $fo
}

set power_saif "n/a"
if {$SAIF ne ""} {
  if {$core eq ""} { error "core instance u_board/u_core not found in the netlist; cannot map the SAIF" }
  set rs [file join $OUT activity_board.saif]
  saif_for_core [file normalize $SAIF] $rs $core
  read_saif -strip_path design_1_wrapper $rs
  power_report [file join $OUT power_saif.rpt]
  set power_saif [file join $OUT power_saif.rpt]
}

# ---------------------------------------------------------------- outputs
set bits [glob -nocomplain [file join $PROJ snn_board.runs impl_1 *.bit]]
if {[llength $bits] != 1} { error "bitstream not found" }
file copy -force [lindex $bits 0] [file join $OUT snn_board.bit]
write_hw_platform -fixed -include_bit -force -file [file join $OUT snn_board.xsa]

proc rpt_val {file re} {
  set v "?"
  if {![file exists $file]} { return $v }
  set fh [open $file r]
  while {[gets $fh line] >= 0} { if {[regexp $re $line -> x]} { set v $x; break } }
  close $fh
  return $v
}
set wns [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -hold]]
set pv  [file join $OUT power_vectorless.rpt]
set utl [file join $OUT utilization.rpt]
set fh [open [file join $OUT summary.txt] w]
puts $fh "cfg=$CFG board_part=$BOARD_PART part=$PART base=$BASE_ADDR"
puts $fh "FCLK_CLK0 requested=${FCLK_MHZ}MHz actual=${fclk_act}MHz"
puts $fh [format "timing: WNS=%.3fns WHS=%.3fns %s" $wns $whs [expr {($wns >= 0 && $whs >= 0) ? "MET" : "*** NOT MET -- do not use this bitstream for latency claims ***"}]]
puts $fh "utilization: SliceLUTs=[rpt_val $utl {^\|\s*Slice LUTs\*?\s*\|\s*(\d+)}] FF=[rpt_val $utl {^\|\s*Slice Registers\s*\|\s*(\d+)}] BRAM_tiles=[rpt_val $utl {^\|\s*Block RAM Tile\s*\|\s*([0-9.]+)}] DSP=[rpt_val $utl {^\|\s*DSPs\s*\|\s*(\d+)}]"
puts $fh "power vectorless: total=[rpt_val $pv {Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)}]W dynamic=[rpt_val $pv {^\|\s*Dynamic \(W\)\s*\|\s*([0-9.]+)}]W static=[rpt_val $pv {Device Static \(W\)\s*\|\s*([0-9.]+)}]W confidence=[rpt_val $pv {Confidence Level\s*\|\s*(\S+)}]"
if {$SAIF ne ""} {
  puts $fh "power SAIF ($SAIF): total=[rpt_val $power_saif {Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)}]W dynamic=[rpt_val $power_saif {^\|\s*Dynamic \(W\)\s*\|\s*([0-9.]+)}]W confidence=[rpt_val $power_saif {Confidence Level\s*\|\s*(\S+)}]"
}
puts $fh "core instance: $core   (its share: power_*.rpt section 'By Hierarchy'; LUT/FF/BRAM: utilization_hier.rpt)"
close $fh
set fh [open [file join $OUT summary.txt] r]; puts [read $fh]; close $fh
puts "bitstream: [file join $OUT snn_board.bit]"
puts "xsa      : [file join $OUT snn_board.xsa]"
