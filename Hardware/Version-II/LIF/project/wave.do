onerror {resume}
radix define fixed#16#decimal#signed -fixed -fraction 16 -signed -base signed -precision 6
radix define fixed#8#decimal -fixed -fraction 8 -base signed -precision 6
radix define fixed#4#decimal#signed -fixed -fraction 4 -signed -base signed -precision 6
quietly WaveActivateNextPane {} 0
TreeUpdate [SetDefaultTree]
WaveRestoreCursors {{Cursor 1} {218545 ns} 0} {{Cursor 3} {2886621 ns} 0}
quietly wave cursor active 2
configure wave -namecolwidth 296
configure wave -valuecolwidth 100
configure wave -justifyvalue left
configure wave -signalnamewidth 1
configure wave -snapdistance 10
configure wave -datasetprefix 0
configure wave -rowmargin 4
configure wave -childrowmargin 2
configure wave -gridoffset 0
configure wave -gridperiod 1
configure wave -griddelta 40
configure wave -timeline 0
configure wave -timelineunits ns
update
WaveRestoreZoom {2886535 ns} {2886699 ns}
