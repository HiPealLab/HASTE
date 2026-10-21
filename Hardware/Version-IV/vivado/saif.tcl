# HASTE Version-IV -- switching-activity (SAIF) capture with Vivado xsim.
#
#   cd Hardware/Version-IV
#   vivado -mode batch -source vivado/saif.tcl -tclargs lif 64x10 [N_IMAGES]
#   vivado -mode batch -source vivado/impl.tcl -tclargs lif 64x10 vivado/out/lif_64x10/activity.saif
#
# Simulates the RTL testbench on the first N_IMAGES test images and records
# toggle activity of the DUT into activity.saif.  Default N_IMAGES: 10 for
# LIF/IZH, 2 for HH (one HH image is 6.3M-87M clock cycles; its activity is
# almost identical from image to image, cycle counts vary by < 0.6 %).
# 2026-10-11: xelab gets -timescale 1ns/1ps (the RTL files carry no
# `timescale; the testbench does), and the run fails if the simulation wrote
# no result for the requested images.
set model [lindex $argv 0]
set topo  [lindex $argv 1]
set nimg  [expr {[llength $argv] > 2 ? [lindex $argv 2] : ($model eq "hh" ? 2 : 10)}]
set V4    [file normalize [file join [file dirname [info script]] ..]]
set B     [file join $V4 build ${model}_${topo}]
set OUT   [file join $V4 vivado out ${model}_${topo}]
file mkdir $OUT
set cwd0 [pwd]
cd $B
set def "MODEL_[string toupper $model]"
set X [expr {$::tcl_platform(platform) eq "windows" ? ".bat" : ""}]
exec xvlog$X -sv -d $def -i $B [file join $V4 rtl snn_fifo.sv] [file join $V4 rtl snn_${model}.sv] [file join $V4 tb tb_snn.sv] >@ stdout
exec xelab$X -timescale 1ns/1ps -debug typical -top tb_snn -snapshot tb_${model} >@ stdout
set f [open saif_run.tcl w]
puts $f "open_saif [file join $OUT activity.saif]"
puts $f "log_saif \[get_objects -r /tb_snn/dut/*\]"
puts $f "run all"
puts $f "close_saif"
puts $f "quit"
close $f
set res [file join $OUT saif_sim_results.txt]
file delete -force $res
exec xsim$X tb_${model} -tclbatch saif_run.tcl \
  -testplusarg SPIKES=[file join $V4 data spikes.mem] -testplusarg LABELS=[file join $V4 data labels.mem] \
  -testplusarg START=0 -testplusarg COUNT=$nimg -testplusarg OUT=$res >@ stdout
# sanity check: one IMG line per simulated image, identical to the shipped Verilator result
set n 0
set h [open $res r]
while {[gets $h line] >= 0} { if {[string match "IMG *" $line]} { incr n } }
close $h
if {$n != $nimg} { error "SAIF simulation produced $n of $nimg images ($res)" }
proc img_lines {path n} {
  set out {}
  set h [open $path r]
  while {[gets $h line] >= 0 && [llength $out] < $n} { if {[string match "IMG *" $line]} { lappend out $line } }
  close $h
  return $out
}
set ref [file join $B rtl_results.txt]
if {[file exists $ref]} {
  if {[img_lines $res $nimg] ne [img_lines $ref $nimg]} {
    error "xsim result differs from the shipped Verilator result $ref (first $nimg images)"
  }
  puts "xsim == Verilator on the first $nimg images"
}
if {![file exists [file join $OUT activity.saif]]} { error "no activity.saif written" }
puts "wrote [file join $OUT activity.saif] ($n images)"
cd $cwd0
