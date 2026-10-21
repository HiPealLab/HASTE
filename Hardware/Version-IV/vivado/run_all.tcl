# HASTE Version-IV -- implement every configuration in one Vivado session.
#
#   cd Hardware/Version-IV
#   vivado -mode batch -source vivado/run_all.tcl                  (vectorless power)
#   vivado -mode batch -source vivado/run_all.tcl -tclargs saif    (SAIF power, see vivado/saif.tcl)
#   subset:  CFGS="lif_10 hh_10" vivado -mode batch -source vivado/run_all.tcl -tclargs saif
#
# Uses the shipped build/ folders (do not run "campaign.py prepare").
# Result table: vivado/out/summary_all.txt (+ per-config reports in vivado/out/<cfg>/)
set V4   [file normalize [file join [file dirname [info script]] ..]]
set SAIF [expr {[lindex $argv 0] eq "saif"}]
set CFGS {lif_10 lif_64x10 lif_64x64x10 izh_10 izh_64x10 izh_64x64x10 hh_10 hh_64x10 hh_64x64x10
          lif_64x10_b4 lif_64x10_b16 izh_64x10_b4 izh_64x10_b16 hh_10_b4 hh_10_b16}
if {[info exists ::env(CFGS)]} { set CFGS $::env(CFGS) }
set failed {}
set saif_failed {}

foreach c $CFGS {
  set i [string first _ $c]
  set model [string range $c 0 [expr {$i - 1}]]
  set topo  [string range $c [expr {$i + 1}] end]
  set s ""
  if {$SAIF} {
    set ::argv [list $model $topo]
    if {[catch {source [file join $V4 vivado saif.tcl]} e]} {
      puts "SAIF FAILED for $c (power will be vectorless): $e"
      lappend saif_failed $c
    } else {
      set s [file join $V4 vivado out $c activity.saif]
    }
  }
  set ::argv [list $model $topo $s]
  if {[catch {source [file join $V4 vivado impl.tcl]} e]} {
    puts "IMPLEMENTATION FAILED for $c: $e"
    lappend failed $c
    catch {close_design}
    catch {close_project}
  }
}

set out [open [file join $V4 vivado out summary_all.txt] w]
foreach c $CFGS {
  set f [file join $V4 vivado out $c summary.txt]
  if {[file exists $f]} {
    set h [open $f r]
    puts -nonewline $out [read $h]
    close $h
  }
}
close $out
puts "implementation failed: $failed"
puts "SAIF failed: $saif_failed"
set h [open [file join $V4 vivado out summary_all.txt] r]
puts [read $h]
close $h
