# HASTE Version-IV -- gate-level check: simulate the post-route netlist written by
# vivado/impl.tcl (vivado/out/<cfg>/netlist_funcsim.v) with the unchanged RTL
# testbench and require it to equal the shipped Verilator result, spike for spike.
#
#   cd Hardware/Version-IV
#   vivado -mode batch -source vivado/netlist_sim.tcl -tclargs lif 64x10 [N_IMAGES]
#
# Added 2026-10-19: on the board, Vivado 2022.2 had synthesised
# "i <= l_start(f_lay + 1'b1)" as l_start(0), which the RTL simulators cannot see.
# This check runs the synthesised logic itself.  Default N_IMAGES: 3 for LIF/IZH,
# 1 for HH and the CNN (gate-level simulation of one HH image takes long).
# Result: vivado/out/<cfg>/netlist_sim_results.txt and a PASS/FAIL line in
# vivado/out/<cfg>/netlist_check.txt.
set model [lindex $argv 0]
set topo  [lindex $argv 1]
set nimg  [expr {[llength $argv] > 2 ? [lindex $argv 2] : (($model eq "hh" || $topo eq "cnn") ? 1 : 3)}]
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
exec xsim$X net_${model} -R \
  -testplusarg SPIKES=[file join $V4 data spikes.mem] -testplusarg LABELS=[file join $V4 data labels.mem] \
  -testplusarg START=0 -testplusarg COUNT=$nimg -testplusarg OUT=$res >@ stdout

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
set got [first_images $res $nimg]
set ref [first_images [file join $B rtl_results.txt] $nimg]
set fh [open [file join $OUT netlist_check.txt] w]
if {$got eq $ref} {
  set msg "${model}_${topo}: PASS -- post-route netlist == Verilator RTL on $nimg image(s), [llength $ref] IMG/SPK lines"
} else {
  set msg "${model}_${topo}: FAIL -- post-route netlist differs from Verilator RTL (see $res)"
}
puts $fh $msg; close $fh
puts $msg
cd $cwd0
