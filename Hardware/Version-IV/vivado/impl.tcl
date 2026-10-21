# HASTE Version-IV -- Vivado non-project flow (synth + place + route + reports)
#
#   cd Hardware/Version-IV
#   vivado -mode batch -source vivado/impl.tcl -tclargs lif 64x10 [path/to/activity.saif]
#   (all configurations: vivado -mode batch -source vivado/run_all.tcl [-tclargs saif])
#
# The build/<model>_<topo>/ directories (memory images, params.svh) are shipped
# and must not be regenerated (do not run "campaign.py prepare").
# Target: xc7z010clg400-1, out-of-context (no I/O buffers), clock 'clk'
# constrained at 50 MHz (vivado/snn.xdc).  If a SAIF file is given (see
# vivado/saif.tcl) power is computed from simulated switching activity,
# otherwise vectorless.
# Outputs: vivado/out/<model>_<topo>/{utilization,timing,power,...}.rpt and
#          summary.txt (LUT/FF/BRAM/DSP, WNS, Fmax, power).
#
# 2026-10-11 fixes (Vivado run by Bardia): one in-memory project per
# configuration; .mem files added as "Memory File" (read_mem is not available
# in every Vivado version); a $readmemh file that cannot be opened
# (Synth 8-4445) is now an ERROR instead of a warning, because synthesis would
# otherwise silently build the network with empty weights; power is parsed
# from power.rpt (there is no get_power_results command).
set model [lindex $argv 0]
set topo  [lindex $argv 1]
set saif  [lindex $argv 2]
set V4    [file normalize [file join [file dirname [info script]] ..]]
set B     [file join $V4 build ${model}_${topo}]
set OUT   [file join $V4 vivado out ${model}_${topo}]
set PART  xc7z010clg400-1
file mkdir $OUT
if {![file exists [file join $B params.svh]]} {
  error "missing $B/params.svh -- the shipped build/ folder is incomplete"
}
set cwd0 [pwd]
cd $B

catch {close_design}
catch {close_project}
create_project -in_memory -part $PART

# a memory image that cannot be found must stop the run
set_msg_config -id {Synth 8-4445} -new_severity {ERROR}

read_verilog -sv [list [file join $V4 rtl snn_fifo.sv] [file join $V4 rtl snn_${model}.sv]]
set mems [glob -nocomplain [file join $B *.mem]]
if {[llength $mems] == 0} { error "no .mem files in $B" }
foreach m $mems {
  add_files -norecurse $m
  set_property FILE_TYPE {Memory File} [get_files $m]
}
read_xdc -mode out_of_context [file join $V4 vivado snn.xdc]

synth_design -top snn_${model} -part $PART -mode out_of_context -include_dirs [list $B] \
  -flatten_hierarchy rebuilt
report_utilization -file [file join $OUT synth_utilization.rpt]
opt_design
place_design
phys_opt_design
route_design

report_utilization               -file [file join $OUT utilization.rpt]
report_utilization -hierarchical -file [file join $OUT utilization_hier.rpt]
report_timing_summary -max_paths 10 -file [file join $OUT timing.rpt]
set power_src "vectorless"
if {$saif ne ""} {
  if {![file exists [file normalize $saif]]} { error "SAIF file not found: $saif" }
  read_saif -strip_path tb_snn/dut [file normalize $saif]
  set power_src "SAIF"
}
report_power -file [file join $OUT power.rpt]
write_checkpoint -force [file join $OUT routed.dcp]
# post-route functional netlist for the gate-level check (vivado/netlist_sim.tcl)
write_verilog -mode funcsim -force [file join $OUT netlist_funcsim.v]

# ---- one-line summary
set wns   [get_property SLACK [get_timing_paths -max_paths 1 -setup]]
set per   [get_property PERIOD [get_clocks clk]]
set fmax  [expr {1000.0 / ($per - $wns)}]
set lut   [llength [get_cells -hier -filter {PRIMITIVE_GROUP == LUT}]]
set ff    [llength [get_cells -hier -filter {PRIMITIVE_GROUP == FLOP_LATCH}]]
set ram36 [llength [get_cells -hier -filter {REF_NAME =~ RAMB36*}]]
set ram18 [llength [get_cells -hier -filter {REF_NAME =~ RAMB18*}]]
set lutram [llength [get_cells -hier -filter {PRIMITIVE_GROUP == DMEM}]]
set dsp   [llength [get_cells -hier -filter {REF_NAME =~ DSP48*}]]

# power figures from the report (rows "| Total On-Chip Power (W) | 0.123 |" etc.)
set pw -1.0; set pdyn -1.0; set psta -1.0; set conf "?"
set pfp [open [file join $OUT power.rpt] r]
while {[gets $pfp line] >= 0} {
  regexp {Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)} $line -> pw
  regexp {^\|\s*Dynamic \(W\)\s*\|\s*([0-9.]+)} $line -> pdyn
  regexp {Device Static \(W\)\s*\|\s*([0-9.]+)} $line -> psta
  regexp {Confidence Level\s*\|\s*(\S+)} $line -> conf
}
close $pfp
if {$pw < 0 || $pdyn < 0 || $psta < 0} { error "could not parse power.rpt in $OUT" }

set fh [open [file join $OUT summary.txt] w]
puts $fh [format "%s %s LUTcells=%d FF=%d LUTRAMcells=%d BRAM36=%d BRAM18=%d (BRAM=%.1f) DSP=%d WNS=%.3fns Fmax=%.1fMHz P_total=%.3fW P_dyn=%.3fW P_static=%.3fW power_src=%s confidence=%s" \
  $model $topo $lut $ff $lutram $ram36 $ram18 [expr {$ram36 + 0.5*$ram18}] $dsp $wns $fmax $pw $pdyn $psta $power_src $conf]
close $fh
set fh [open [file join $OUT summary.txt] r]; puts [read $fh]; close $fh
catch {close_design}
catch {close_project}
cd $cwd0
