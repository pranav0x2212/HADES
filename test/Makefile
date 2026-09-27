# Makefile
# See https://docs.cocotb.org/en/stable/quickstart.html for more info

SIM ?= icarus
FST ?= -fst
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src

COMPILE_ARGS += -g2012

ifneq ($(GATES),yes)

SIM_BUILD = sim_build/rtl
FIXED_CORE_SV = $(SIM_BUILD)/hades_v0_core_fixed.sv
$(FIXED_CORE_SV): $(SRC_DIR)/hades_v0_core.sv | $(SIM_BUILD)
	sed 's/input  var logic/input  logic/g' $< > $@

$(SIM_BUILD):
	mkdir -p $@

VERILOG_SOURCES += $(SRC_DIR)/tt_um_hades_v0.v
VERILOG_SOURCES += $(FIXED_CORE_SV)
VERILOG_SOURCES += $(PWD)/sky130_sram_1rw_tiny.v

else

SIM_BUILD                = sim_build/gl
COMPILE_ARGS            += -DGL_TEST
COMPILE_ARGS            += -DFUNCTIONAL
COMPILE_ARGS            += -DUSE_POWER_PINS
COMPILE_ARGS            += -DSIM
COMPILE_ARGS            += -DUNIT_DELAY=\#1
VERILOG_SOURCES         += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v
VERILOG_SOURCES         += $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog/sky130_fd_sc_hd.v
VERILOG_SOURCES         += $(PWD)/gate_level_netlist.v

endif

COMPILE_ARGS    += -I$(SRC_DIR)
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL         = tb

COCOTB_TEST_MODULES = test

include $(shell cocotb-config --makefiles)/Makefile.sim
