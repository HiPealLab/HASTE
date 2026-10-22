# HASTE Version-IV -- gate-level check: simulate the post-route netlist written by
# vivado/impl.tcl (vivado/out/<cfg>/netlist_funcsim.v) with the unchanged RTL
# testbench and require it to equal the shipped Verilator result, spike for spike.
#
#   cd Hardware/Version-IV
#   vivado -mode batch -source vivado/netlist_sim.tcl -tclargs lif 64x10 [N_IMAGES] [T_PREFIX]
#
# Added 2026-10-19: on the board, Vivado 2022.2 had synthesised
# "i <= l_start(f_lay + 1'b1)" as l_start(0), which the RTL simulators cannot see.
# This check runs the synthesised logic itself.  Default N_IMAGES: 3 for LIF/IZH,
# 1 for HH and the CNN (gate-level simulation of one HH image takes long).
# Result: vivado/out/<cfg>/netlist_sim_results.txt and a PASS/FAIL line in
# vivado/out/<cfg>/netlist_check.txt.
#
# T_PREFIX (added 2026-10-22, for hh_64x10, hh_64x64x10 and lif_cnn, where one full
# image is 1.8M-87M cycles): stop after the first T_PREFIX timesteps of image 0 and
# compare the SPK lines of the completed timesteps.  The layer-table bug shows up in
# the first output spikes (wrong neuron indices), so a prefix is enough to catch it.
set model [lindex $argv 0]
set topo  [lindex $argv 1]
set nimg  [expr {[llength $argv] > 2 ? [lindex $argv 2] : (($model eq "hh" || $topo eq "cnn") ? 1 : 3)}]
set tpre  [expr {[llength $argv] > 3 ? [lindex $argv 3] : 0}]
set V4    [file normalize [file join [file dirname [info script]] ..]]
set B     [file join $V4 build ${model}_${topo}]
set OUT   [file join $V4 vivado out ${model}_${topo}]
set NET   [file join $OUT netlist_funcsim.v]
if {![file exists $NET]} { error "missing $NET -- run vivado/impl.tcl for ${model}_${topo} first" }
set GLBL  [file join $::env(XILINX_VIVADO) data verilog src glbl.v]
set cwd0 [pwd]
set W [file join $OUT netlist_sim]
file mkdir $W
cd $W
set def "MODEL_[string toupper $model]"
set X [expr {$::tcl_platform(platform) eq "windows" ? ".bat" : ""}]
exec xvlog$X $NET $GLBL >@ stdout
exec xvlog$X -sv -d $def -i $B [file join $V4 tb tb_snn.sv] >@ stdout
exec xelab$X -timescale 1ns/1ps -L unisims_ver -L secureip -top tb_snn -top glbl -snapshot net_${model} >@ stdout
set res [file join $OUT netlist_sim_results.txt]
file delete -force $res
set plus [list -testplusarg SPIKES=[file join $V4 data spikes.mem] -testplusarg LABELS=[file join $V4 data labels.mem] \
  -testplusarg START=0 -testplusarg COUNT=$nimg -testplusarg OUT=$res]
if {$tpre > 0} {
  # run time = T_PREFIX/100 of image 0's Verilator cycle count (T = 100 steps), x1.5 margin
  set ncyc 0
  set h [open [file join $B rtl_results.txt] r]
  set cyc_line {}
  while {[gets $h line] >= 0} { if {[string match "IMG 0 *" $line]} { set cyc_line $line; break } }
  close $h
  regexp {CYCLES (\d+)} $cyc_line -> ncyc
  set run_ns [expr {wide(1.5 * $ncyc * $tpre / 100.0 * 20) + 100000}]
  set tb [open run_prefix.tcl w]; puts $tb "run ${run_ns}ns\nquit"; close $tb
  exec xsim$X net_${model} -tclbatch run_prefix.tcl {*}$plus >@ stdout
} else {
  exec xsim$X net_${model} -R {*}$plus >@ stdout
}

# all IMG and SPK lines of the first nimg images must equal the Verilator file
proc first_images {path n} {
  set out {}; set k 0
  set h [open $path r]
  while {[gets $h line] >= 0 && $k < $n} {
    set line [string trim $line]
    if {[string match "SPK *" $line]} { lappend out $line }
    if {[string match "IMG *" $line]} { lappend out $line; incr k }
  }
  close $h
  return $out
}
# prefix mode: SPK lines of image 0 with t < T_PREFIX (only completed timesteps)
proc prefix_lines {path tmax} {
  set out {}
  set h [open $path r]
  while {[gets $h line] >= 0} {
    set line [string trim $line]
    if {[string match "IMG *" $line]} break
    if {[string match "SPK *" $line] && [lindex $line 2] < $tmax} { lappend out $line }
  }
  close $h
  return $out
}
set fh [open [file join $OUT netlist_check.txt] w]
if {$tpre > 0} {
  set got [prefix_lines $res $tpre]
  set ref [prefix_lines [file join $B rtl_results.txt] $tpre]
} else {
  set got [first_images $res $nimg]
  set ref [first_images [file join $B rtl_results.txt] $nimg]
}
if {$tpre > 0 && [llength $ref] > 0 && $got eq $ref} {
  set msg "${model}_${topo}: PASS (prefix) -- post-route netlist == Verilator RTL on image 0, timesteps 0..[expr {$tpre-1}], [llength $ref] SPK lines"
} elseif {$tpre > 0 && [llength $ref] > 0 && [llength $got] < [llength $ref] && $got eq [lrange $ref 0 [expr {[llength $got]-1}]]} {
  set msg "${model}_${topo}: INCOMPLETE -- [llength $got] of [llength $ref] SPK lines match, simulation stopped before timestep T_PREFIX (increase the 1.5x run-time margin)"
} elseif {$tpre == 0 && $got eq $ref} {
  set msg "${model}_${topo}: PASS -- post-route netlist == Verilator RTL on $nimg image(s), [llength $ref] IMG/SPK lines"
} else {
  set msg "${model}_${topo}: FAIL -- post-route netlist differs from Verilator RTL (see $res)"
}
puts $fh $msg; close $fh
puts $msg
cd $cwd0
