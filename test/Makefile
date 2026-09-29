SIM ?= icarus
FST ?= -fst
TOPLEVEL_LANG ?= verilog
SRC_DIR = $(PWD)/../src

COMPILE_ARGS += -g2012

ifneq ($(GATES),yes)

SIM_BUILD = sim_build/rtl
CORE_SV   = compute regs result_regs ctrl hades_top hades_dupff
FIXED_SV  = $(addprefix $(SIM_BUILD)/,$(addsuffix .sv,$(CORE_SV)))

$(SIM_BUILD):
	mkdir -p $@

$(SIM_BUILD)/%.sv: $(SRC_DIR)/%.sv | $(SIM_BUILD)
	sed 's/input var logic/input logic/g; s/input  var logic/input  logic/g' $< > $@

VERILOG_SOURCES += $(SRC_DIR)/tt_um_hades.v
VERILOG_SOURCES += $(SRC_DIR)/rf_top.v
VERILOG_SOURCES += $(FIXED_SV)

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
VERILOG_SOURCES         += $(SRC_DIR)/rf_top.v

endif

COMPILE_ARGS    += -I$(SRC_DIR)
VERILOG_SOURCES += $(PWD)/tb.v
TOPLEVEL         = tb

COCOTB_TEST_MODULES = test

include $(shell cocotb-config --makefiles)/Makefile.sim
