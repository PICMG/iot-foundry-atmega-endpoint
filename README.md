# IoTFoundry Atmega Endpoint

![License](https://img.shields.io/github/license/PICMG/iot-foundry-atmega-endpoint)
![Coverage](https://img.shields.io/codecov/c/github/PICMG/iot-foundry-atmega-endpoint)
![Issues](https://img.shields.io/github/issues/PICMG/iot-foundry-atmega-endpoint)
![Forks](https://img.shields.io/github/forks/PICMG/iot-foundry-atmega-endpoint)
![Stars](https://img.shields.io/github/stars/PICMG/iot-foundry-atmega-endpoint)
![Last Commit](https://img.shields.io/github/last-commit/PICMG/iot-foundry-atmega-endpoint)

This project implements an IoTFoundry serial MCTP/PLDM endpoint for the ATMega family of microcontrollers.

The code and build process in this project relies upon the template code found in the IoTFoundry endpoint project on github (https://github.com/PICMG/iot-foundry-endpoint) to implement the core features.  This project implements a platform-specific interface layer, and platform-specific build process.

This repository is part of the IoTFoundry family of open source projects.  For more information about IoTFoundry, please visit the main IoTFoundry site at: [https://picmg.github.io/iot-foundry/](https://picmg.github.io/iot-foundry/)

## Repository Resources
* .\src - the source files for implementing the mctp endpoint
* .\include - the header files

## System Requirements
The following are system requirements for buidling/testing teh code in this library.

- Linux with the gnu toolchain and make tools installed.
- An atmega-based microcontroller board that is programmable using avrdude.

# Environment Installation

```bash
# update the software registry
sudo apt-get --assume-yes update
sudo apt-get --assume-yes upgrade
```

```bash
# install avr build tools
# example - replace with the actual latest URL
wget https://<microchip_url>/avr8-gnu-toolchain-<VERSION>-linux.any.x86_64.tar.gz -O /tmp/avr8-toolchain.tar.gz

cd /tmp
tar xzf /tmp/avr8-toolchain.tar.gz
# this creates a directory like avr8-gnu-toolchain-<VERSION>
sudo mv avr8-gnu-toolchain-<VERSION> /usr/local/avr8-gnu-toolchain-<VERSION>

sudo ln -s /usr/local/avr8-gnu-toolchain-<VERSION>/bin/* /usr/local/bin/ || true
hash -r

which avr-gcc
avr-gcc --version
# confirm device specs for atmega4809 exist
grep -R "atmega4809" /usr/local/avr8-gnu-toolchain-<VERSION> || true
```

```bash
# patch and build gdb for avr
sudo apt-get --assume-yes --purge remove gdb-avr
wget ftp.gnu.org/gnu/gdb/gdb-8.1.1.tar.xz
tar xf gdb-8.1.1.tar.xz
cd gdb-8.1.1
perl -i -0pe 's/  ULONGEST addr = unpack_long \(type, buf\);\R\R  return avr_make_saddr \(addr\);\R/  ULONGEST addr = unpack_long (type, buf);\n\n  if (TYPE_DATA_SPACE (type))\n    return avr_make_saddr (addr);\n  else\n    return avr_make_iaddr (addr);\n/' gdb/avr-tdep.c
./configure --prefix=/usr --target=avr
make
sudo make install
cd ~
```

# Building

## Board Configuration

This project exposes a small set of build-time switches so you can target
different ATmega families without editing core code. Key knobs:

- `MCTP_BAUD_MODE`: selects baud calculation mode. Values: `MCTP_BAUD_MODE_DA_DB` (default), `MCTP_BAUD_MODE_CLASSIC`, or `MCTP_BAUD_MODE_AUTO`.
- Register/alias macros: `MCTP_USART_CTRLA`, `MCTP_USART_CTRLB`, `MCTP_USART_CTRLC`, `MCTP_USART_STATUS`, `MCTP_USART_BAUD`, `MCTP_USART_RXDATAL`, `MCTP_USART_TXDATAL`, `MCTP_TX_PORT_DIR`, `MCTP_RX_PORT_DIR`, `MCTP_UART_TX_PIN`, `MCTP_UART_RX_PIN`.

Two common targets and how to configure them:

- ATmega4809 (default)
      - No extra flags required. The default `board_config.h` and `platform.c` implementations target the DA/DB family (single `BAUD` register with BSEL/BSCALE).

- ATmega328P (classic AVR with UBRR)
      - Recommended: create a small board header (example `src/board_atmega328p.h`) that defines the minimal register aliases and a UBRR writer. Example contents:

```c
/* src/board_atmega328p.h */
#define MCTP_BAUD_MODE MCTP_BAUD_MODE_CLASSIC
#define MCTP_USART_BAUD UBRR0L
#define MCTP_USART_CTRLB UCSR0B
#define MCTP_USART_CTRLA UCSR0A
#define MCTP_USART_CTRLC UCSR0C
#define MCTP_USART_STATUS UCSR0A
#define MCTP_USART_RXDATAL UDR0
#define MCTP_USART_TXDATAL UDR0
#define MCTP_TX_PORT_DIR PORTD_DIR
#define MCTP_RX_PORT_DIR PORTD_DIR
#define MCTP_UART_TX_PIN 1
#define MCTP_UART_RX_PIN 0
/* Provide UBRR writer used by the classic-mode setter */
#define MCTP_USART_WRITE_UBRR(v) do { UBRR0H = (uint8_t)((v)>>8); UBRR0L = (uint8_t)(v); } while(0)
```

      - Build with the board header included via `BOARD_CFLAGS` or by copying the header into `src/` and adjusting include order. Example using `BOARD_CFLAGS`:

```bash
make BOARD_CFLAGS='-include src/board_atmega328p.h'
```

Quick inline alternative (less recommended): pass `-D` flags to map aliases and select classic mode. This is error-prone and verbose — prefer the board header approach.

# Eliminating False Linter Errors
This project generates a `compile_commands.json` to help IDEs (VS Code C/C++ extension) match your build flags and include paths.

To regenerate:

```bash
make generate-compile-commands
```

VS Code tip:
- Select the `AVR` configuration in the C/C++ extension and ensure `compile_commands.json` is selected (the workspace `.vscode/c_cpp_properties.json` already references it).
- Reload the window or restart the C/C++ server if IntelliSense still reports missing AVR symbols.

# Running device tests

Build and flash the firmware to your device (example target uses default board):

```bash
make
make flash
```

Install Python requirements for the serial test runner:

```bash
python3 -m pip install -r tests/requirements.txt
```

Run the host-side MCTP test runner against the device serial port (example):

```bash
python3 tests/run_mctp_tests.py /dev/ttyACM0 9600
```

Notes:
- Replace `/dev/ttyACM0` with the serial device node for your platform.
- If you target a different MCU/board, include a board header or pass `BOARD_CFLAGS` when building (see "Board Configuration").
- The host test runner lives at `tests/run_mctp_tests.py` and will print decoded frames and diagnostics.

