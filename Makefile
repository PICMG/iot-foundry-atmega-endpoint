MCU = atmega4809
F_CPU = 16000000UL
CC = avr-gcc
OBJCOPY = avr-objcopy

.DEFAULT_GOAL := all

PORT = /dev/ttyACM0
PROG = jtag2updi
PROG_BAUD = 115200
TOUCH_BAUD = 1200
TOUCH_DELAY = 2

CFLAGS = -std=gnu11 -g -Og -Wall -mmcu=$(MCU) -DF_CPU=$(F_CPU) -Iinclude -Iinclude/core

# Board-specific build flags (override to select pins/peripheral without editing source)
# Example usage: make BOARD_CFLAGS="-DMCTP_USART_NUM=3 -DMCTP_UART_TX_PORT=B -DMCTP_UART_TX_PIN=4 \
#   -DMCTP_UART_RX_PORT=B -DMCTP_UART_RX_PIN=5 -DMCTP_BAUD=9600UL -DF_CPU=16000000UL" all
BOARD_CFLAGS ?=
CFLAGS += $(BOARD_CFLAGS)
LDFLAGS = -mmcu=$(MCU)

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


.PHONY: download-core platform_build

generate-compile-commands:
	python3 tools/generate_compile_commands.py

platform_build: $(TARGET).hex
	@echo "Built $(TARGET).hex from: $(SRCS)"
.PHONY: all build clean flash gdb

all: download-core platform_build

$(TARGET).elf: $(SRCS)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $(SRCS)

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O ihex -R .eeprom $< $@

clean:
	rm -f $(TARGET).elf $(TARGET).hex

flash: $(TARGET).hex
	# Touch-reset at $(TOUCH_BAUD), then program at $(PROG_BAUD) with retries
	@stty -F $(PORT) $(TOUCH_BAUD) || true
	@printf '' > $(PORT) || true
	@sleep $(TOUCH_DELAY)
	@stty -F $(PORT) $(PROG_BAUD) || true
	@echo "avrdude: programming at $(PROG_BAUD) baud (single attempt)";
	@avrdude -v -p $(MCU) -c $(PROG) -P $(PORT) -b $(PROG_BAUD) -U flash:w:$(TARGET).hex:i

gdb: $(TARGET).elf
	avr-gdb $(TARGET).elf

