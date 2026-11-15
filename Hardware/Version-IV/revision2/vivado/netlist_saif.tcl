# HASTE revision 2 -- power from POST-ROUTE NETLIST switching activity.
#
# Why: the first-round SAIF (vivado/saif.tcl) simulated the RTL, so only 5-26 % of the
# routed nets (1 % for the CNN) were annotated and dynamic power was mostly vectorless.
# Here the routed netlist itself (netlist_funcsim.v, written by impl.tcl /
# impl_ann.tcl) is simulated, so activity names match the implemented nets.
#
#   cd Hardware/Version-IV
#   vivado -mode batch -source revision2/vivado/netlist_saif.tcl -tclargs snn lif_64x10 [N_IMAGES] [T_PREFIX]
#   vivado -mode batch -source revision2/vivado/netlist_saif.tcl -tclargs ann 64x10 [N_IMAGES]
#
# Needs: the routed checkpoint + netlist of that configuration (vivado/out/<cfg>/ for SNNs,
# revision2/vivado/out/ann_<topo>/ for ANNs).  Defaults: N_IMAGES 10 (LIF/IZH/ANN), 1 (HH/CNN);
# T_PREFIX (SNN only): simulate only the first T_PREFIX timesteps of image 0 (HH 64x10 /
# 64x64x10 / CNN: use 5).
# Checks: the simulated netlist must reproduce the Verilator result (IMG lines / SPK prefix),
# otherwise the run stops.  Output in the same out/<cfg>/ folder:
#   activity_netlist.saif, power_netlist_saif.rpt, saif_netlist_read.log,
#   summary_netsaif.txt  (P_total, P_dyn, P_static, nets matched %, confidence)
set kind [lindex $argv 0]
set cfg  [lindex $argv 1]
set V4   [file normalize [file join [file dirname [info script]] .. ..]]
set R2   [file join $V4 revision2]
if {$kind eq "ann"} {
  set B   [file join $R2 build_ann ann_${cfg}]
  set OUT [file join $R2 vivado out ann_${cfg}]
  set TB  tb_ann
  set dflt 10
} else {
  set B   [file join $V4 build $cfg]
  set OUT [file join $V4 vivado out $cfg]
  set TB  tb_snn
  set model [lindex [split $cfg _] 0]
  set dflt [expr {($model eq "hh" || [string match "*cnn" $cfg]) ? 1 : 10}]
}
set nimg [expr {[llength $argv] > 2 ? [lindex $argv 2] : $dflt}]
set tpre [expr {[llength $argv] > 3 ? [lindex $argv 3] : 0}]
set NET  [file join $OUT netlist_funcsim.v]
set DCP  [file join $OUT routed.dcp]
foreach f [list $NET $DCP] { if {![file exists $f]} { error "missing $f -- implement $cfg first" } }
set GLBL [file join $::env(XILINX_VIVADO) data verilog src glbl.v]
set X [expr {$::tcl_platform(platform) eq "windows" ? ".bat" : ""}]
set W [file join $OUT netsaif_sim]
file mkdir $W
set cwd0 [pwd]
cd $W

# ---- simulate the routed netlist with the unchanged testbench, recording SAIF
exec xvlog$X $NET $GLBL >@ stdout
if {$kind eq "ann"} {
  exec xvlog$X -sv -i $B [file join $R2 tb tb_ann.sv] >@ stdout
  set plus [list -testplusarg INPUTS=[file join $R2 build_ann inputs.mem] -testplusarg LABELS=[file join $R2 build_ann labels.mem]]
} else {
  exec xvlog$X -sv -d MODEL_[string toupper $model] -i $B [file join $V4 tb tb_snn.sv] >@ stdout
  set plus [list -testplusarg SPIKES=[file join $V4 data spikes.mem] -testplusarg LABELS=[file join $V4 data labels.mem]]
}
exec xelab$X -timescale 1ns/1ps -debug typical -L unisims_ver -L secureip -top $TB -top glbl -snapshot netsaif >@ stdout
set res [file join $OUT netsaif_sim_results.txt]
file delete -force $res
lappend plus -testplusarg START=0 -testplusarg COUNT=$nimg -testplusarg OUT=$res
set saif [file join $OUT activity_netlist.saif]
set runcmd "run all"
if {$tpre > 0} {
  set h [open [file join $B rtl_results.txt] r]
  set ncyc 0
  while {[gets $h line] >= 0} { if {[regexp {^IMG 0 .*CYCLES (\d+)} $line -> ncyc]} break }
  close $h
  set runcmd "run [expr {wide($ncyc * $tpre / 100.0 * 20) + 1000}]ns"
}
set f [open saif_run.tcl w]
puts $f "open_saif $saif"
puts $f "log_saif \[get_objects -r /$TB/dut/*\]"
puts $f $runcmd
puts $f "close_saif"
puts $f "quit"
close $f
exec xsim$X netsaif -tclbatch saif_run.tcl {*}$plus >@ stdout

# ---- functional check against the Verilator result
proc lines_of {path pat n} {
  set out {}
  set h [open $path r]
  while {[gets $h line] >= 0 && [llength $out] < $n} {
    set line [string trim $line]
    if {[string match $pat $line]} { lappend out $line }
  }
  close $h
  return $out
}
set ref [file join $B rtl_results.txt]
if {$tpre > 0} {
  # SPK lines of image 0 with t < T_PREFIX-1 (completed timesteps only)
  set got {}; set exp {}
  foreach l [lines_of $res "SPK 0 *" 100000] { if {[lindex $l 2] < $tpre - 1} { lappend got $l } }
  foreach l [lines_of $ref "SPK 0 *" 100000] { if {[lindex $l 2] < $tpre - 1} { lappend exp $l } }
  if {[llength $exp] == 0 || $got ne $exp} { error "netlist SAIF run: spike prefix differs from Verilator ($res)" }
  set chk "prefix: [llength $exp] SPK lines == Verilator"
} else {
  set got [lines_of $res "IMG *" $nimg]
  set exp [lines_of $ref "IMG *" $nimg]
  if {[llength $got] != $nimg || $got ne $exp} { error "netlist SAIF run differs from Verilator ($res)" }
  set chk "$nimg images == Verilator"
}
puts "functional check: $chk"

# ---- power of the routed design with the netlist activity
cd $OUT
open_checkpoint $DCP
read_saif -strip_path $TB/dut $saif -out_file [file join $OUT saif_netlist_read.log]
report_power -file [file join $OUT power_netlist_saif.rpt]
set pw -1.0; set pdyn -1.0; set psta -1.0; set conf "?"; set match "?"
set h [open [file join $OUT power_netlist_saif.rpt] r]
while {[gets $h line] >= 0} {
  regexp {Total On-Chip Power \(W\)\s*\|\s*([0-9.]+)} $line -> pw
  regexp {^\|\s*Dynamic \(W\)\s*\|\s*([0-9.]+)} $line -> pdyn
  regexp {Device Static \(W\)\s*\|\s*([0-9.]+)} $line -> psta
  regexp {Confidence Level\s*\|\s*(\S+)} $line -> conf
  regexp -nocase {Design Nets Matched\s*\|\s*([^|]+)\|} $line -> match
}
close $h
set fh [open [file join $OUT summary_netsaif.txt] w]
puts $fh [format "%s P_total=%.4fW P_dyn=%.4fW P_static=%.4fW nets_matched=%s confidence=%s check=\"%s\"" \
  $cfg $pw $pdyn $psta [string trim $match] $conf $chk]
close $fh
set fh [open [file join $OUT summary_netsaif.txt] r]; puts [read $fh]; close $fh
catch {close_design}
cd $cwd0
