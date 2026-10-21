# HASTE Version-IV -- create the Vitis platform + bare-metal app from the .xsa (XSCT, Vitis 2022.2)
#
#   cd Hardware/Version-IV
#   xsct board/sw/create_app.tcl                                   # default xsa (50 MHz build)
#   xsct board/sw/create_app.tcl xsa=board/vivado/out/lif_64x10_100MHz/snn_board.xsa
#
# Options: xsa=<file> (default board/vivado/out/lif_64x10_50MHz/snn_board.xsa)
#          ws=<dir>   (default: <dir of the xsa>/vitis_ws)
# Result:  <ws>/snn_app/Release/snn_app.elf  (path printed at the end)
set SW [file normalize [file dirname [info script]]]
set V4 [file normalize [file join $SW .. ..]]
set XSA [file join $V4 board vivado out lif_64x10_50MHz snn_board.xsa]
set WS ""
foreach a $argv {
  if {![regexp {^([a-z]+)=(.*)$} $a -> k v]} { error "bad argument '$a' (use key=value)" }
  switch -- $k { xsa { set XSA [file normalize $v] } ws { set WS [file normalize $v] } default { error "unknown option $k" } }
}
if {![file exists $XSA]} { error "xsa not found: $XSA (run board/vivado/build_board.tcl first)" }
if {$WS eq ""} { set WS [file join [file dirname $XSA] vitis_ws] }
file delete -force $WS
file mkdir $WS
setws $WS

platform create -name snn_plat -hw $XSA -out $WS
domain create -name standalone_domain -os standalone -proc ps7_cortexa9_0
platform write
platform generate

set ok 0
foreach tmpl [list {Empty Application(C)} {Empty Application}] {
  if {![catch {app create -name snn_app -platform snn_plat -domain standalone_domain -template $tmpl -lang c} err]} { set ok 1; break }
  puts "template '$tmpl' not accepted: $err"
}
if {!$ok} { error "could not create the application" }
importsources -name snn_app -path [file join $SW main.c]
app config -name snn_app build-config release
app build -name snn_app

set elf [glob -nocomplain [file join $WS snn_app Release snn_app.elf] [file join $WS snn_app Debug snn_app.elf]]
if {[llength $elf] == 0} { error "build failed: no snn_app.elf in $WS/snn_app" }
puts "ELF: [lindex $elf 0]"
