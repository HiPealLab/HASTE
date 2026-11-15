# HASTE revision 2 -- everything Bardia runs, in one Vivado session.
#   cd Hardware/Version-IV
#   vivado -mode batch -source revision2/vivado/run_rev2_all.tcl  |& tee revision2/vivado/run_rev2_all.log
#
# 1. implement the three ANN baseline cores (impl_ann.tcl, vectorless first pass)
# 2. netlist-SAIF power for the ANN cores and for the SNN configurations below
#    (needs vivado/out/<cfg>/routed.dcp + netlist_funcsim.v from the fix2 run of 2026-10-22;
#     if a checkpoint is missing, re-run:  vivado -mode batch -source vivado/impl.tcl -tclargs <model> <topo>)
# Summary: revision2/vivado/out/summary_rev2.txt
set R2 [file normalize [file join [file dirname [info script]] ..]]
set V4 [file normalize [file join $R2 ..]]
set ANN {10 64x10 64x64x10}
# {cfg n_images t_prefix}
set SNN {{lif_10 10 0} {lif_64x10 10 0} {lif_64x64x10 10 0} {izh_10 10 0} {izh_64x10 3 0} {izh_64x64x10 2 0}
         {hh_10 1 0} {hh_64x10 1 5} {hh_64x64x10 1 5} {lif_cnn 1 5}}
if {[info exists ::env(ANN)]} { set ANN $::env(ANN) }
if {[info exists ::env(SNN)]} { set SNN $::env(SNN) }
set failed {}
foreach t $ANN {
  set ::argv [list $t ""]
  if {[catch {source [file join $R2 vivado impl_ann.tcl]} e]} { puts "IMPL FAILED ann_$t: $e"; lappend failed impl_ann_$t; catch {close_project} }
  set ::argv [list ann $t]
  if {[catch {source [file join $R2 vivado netlist_saif.tcl]} e]} { puts "NETSAIF FAILED ann_$t: $e"; lappend failed saif_ann_$t; catch {close_design} }
}
foreach s $SNN {
  lassign $s c n tp
  set ::argv [list snn $c $n $tp]
  if {[catch {source [file join $R2 vivado netlist_saif.tcl]} e]} { puts "NETSAIF FAILED $c: $e"; lappend failed saif_$c; catch {close_design} }
}
set out [open [file join $R2 vivado out summary_rev2.txt] w]
foreach t $ANN {
  foreach f [list [file join $R2 vivado out ann_$t summary.txt] [file join $R2 vivado out ann_$t summary_netsaif.txt]] {
    if {[file exists $f]} { set h [open $f r]; puts -nonewline $out [read $h]; close $h }
  }
}
foreach s $SNN {
  set f [file join $V4 vivado out [lindex $s 0] summary_netsaif.txt]
  if {[file exists $f]} { set h [open $f r]; puts -nonewline $out [read $h]; close $h }
}
puts $out "failed: $failed"
close $out
set h [open [file join $R2 vivado out summary_rev2.txt] r]; puts [read $h]; close $h
