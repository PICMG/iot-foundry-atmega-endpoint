-include include/last_build.make

# MCU and F_CPU may be provided on the command line. If not provided,
# prefer values from include/last_build.make (if present) or these defaults.
MCU ?= atmega328p
# canonical lowercase MCU name used for compiler flags
MCU_GCC := $(shell echo $(MCU) | tr '[:upper:]' '[:lower:]')
F_CPU ?= 16000000UL

# If `F_CPU` wasn't provided on the command line, prefer the last-used
# F_CPU recorded by the generator at `include/last_fcpu`.
ifneq ($(origin F_CPU), command line)
ifneq ($(wildcard include/last_fcpu),)
F_CPU := $(shell cat include/last_fcpu)
endif
endif
CC = avr-gcc
OBJCOPY = avr-objcopy

# Determine MCU to use for flashing: if `MCU` was provided on the command line
# use that. Otherwise prefer the last-used MCU recorded by the generator
# at `include/last_mcu` (written when `include/generated_serial_config.h` is
# generated). This lets `make flash` be run without specifying `MCU`.
ifeq ($(origin MCU), command line)
MCU_FOR_FLASH := $(MCU)
else
ifneq ($(wildcard include/last_mcu),)
MCU_FOR_FLASH := $(shell cat include/last_mcu)
else
MCU_FOR_FLASH := $(MCU)
endif
endif

.DEFAULT_GOAL := all

PORT = /dev/ttyUSB1
# Programmer type (required for flashing). No default — supply PROG=<type> when calling `make flash`.
PROG =
PROG_BAUD = 115200

# Allow calling `make flash /dev/ttyACM0` — if an extra goal is provided
# and it's not a known make target, treat the first extra goal as the
# serial `PORT` to use. This keeps `make flash PORT=...` working as well.
KNOWN_GOALS := all download-core platform_build generate-compile-commands clean flash gdb
TTY_ARGS := $(filter-out $(KNOWN_GOALS),$(MAKECMDGOALS))
ifneq ($(TTY_ARGS),)
TTY_ARG := $(firstword $(TTY_ARGS))
PORT := $(TTY_ARG)
$(eval .PHONY: $(TTY_ARG))
$(eval $(TTY_ARG): ; @:)
endif

CFLAGS = -std=gnu11 -g -Og -Wall -mmcu=$(MCU_GCC) -DF_CPU=$(F_CPU) -Iinclude -Iinclude/core

# Configuration is generated from configurations.json by
# `tools/generate_serial_config.py` and written to include/generated_serial_config.h
LDFLAGS = -mmcu=$(MCU_GCC)

TARGET = atmega

# collect C sources from project `src/` and downloaded `src/core/`
SRCS := $(wildcard src/*.c src/core/*.c)

# fetch core sources from IoTFoundry template and place them under `core/` and `include/core/`
# Repository to pull from (owner/repo) and branch
CORE_REPO=PICMG/iot-foundry-endpoint
CORE_BRANCH=main
CORE_URL=https://raw.githubusercontent.com/$(CORE_REPO)/$(CORE_BRANCH)
# Do not hardcode remote filenames; use wildcard-based retrieval.
# The download recipe clones the remote repo and copies
# `src/*` -> `src/core/` and `include/*` -> `include/core/`.


download-core:
	mkdir -p src/core
	mkdir -p include/core
	# Download repository tarball and extract relevant subfolders (wildcard behavior)
	TMPDIR=$$(mktemp -d) && \
	wget -q -O $$TMPDIR/repo.tar.gz https://github.com/$(CORE_REPO)/archive/refs/heads/$(CORE_BRANCH).tar.gz || (rm -rf $$TMPDIR; exit 1); \
	mkdir -p $$TMPDIR/repo && \
	tar -xzf $$TMPDIR/repo.tar.gz -C $$TMPDIR/repo --strip-components=1 || (rm -rf $$TMPDIR; exit 1); \
	cp -a $$TMPDIR/repo/src/. src/core/ 2>/dev/null || true; \
	cp -a $$TMPDIR/repo/include/. include/core/ 2>/dev/null || true; \
	rm -rf $$TMPDIR


.PHONY: download-core platform_build generate-serial-config interactive

# Force target used to ensure generator runs each build (prevents stale header usage)
FORCE:

generate-compile-commands:
	python3 tools/generate_compile_commands.py

platform_build: $(TARGET).hex
	@echo "Built $(TARGET).hex from: $(SRCS)"
.PHONY: all build clean flash gdb

interactive:
	@python3 tools/interactive_build.py

all: download-core platform_build

$(TARGET).elf: include/generated_serial_config.h $(SRCS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(SRCS)


# Generate the serial configuration header from configurations.json
include/generated_serial_config.h: tools/generate_serial_config.py configurations.json FORCE
	@echo "Generating serial config header..."
	@MCU=$(MCU) \
	  SERIAL_BAUD=$(SERIAL_BAUD) \
	  SERIAL_UART=$(SERIAL_UART) \
	  SERIAL_PIN_OPTION=$(SERIAL_PIN_OPTION) \
	  F_CPU=$(F_CPU) \
	  python3 tools/generate_serial_config.py || (echo "Failed to generate serial config; set SERIAL_BAUD and valid MCU"; exit 2)

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@

clean:
	rm -f $(TARGET).elf $(TARGET).hex

flash: $(TARGET).hex
	# Program using avrdude. PROG (programmer) must be supplied by the caller.
	@echo "Using MCU: $(MCU_FOR_FLASH)"
	@if [ -z "$(PROG)" ]; then \
		echo "Error: PROG (programmer) not set. Invoke as 'make flash PROG=<programmer> PORT=/dev/tty...'"; \
		exit 1; \
	fi
	@echo "avrdude: programming at $(PROG_BAUD) baud (single attempt)";
	@avrdude -v -p $(MCU_FOR_FLASH) -c $(PROG) -P $(PORT) -b $(PROG_BAUD) -U flash:w:$(TARGET).hex:i

gdb: $(TARGET).elf
	avr-gdb $(TARGET).elf

