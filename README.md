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

Build-time serial configuration
-------------------------------

The build now generates a `include/generated_serial_config.h` header from `configurations.json` using `tools/generate_serial_config.py`. Provide the minimal variables to configure serial at build time:

- `MCU` (already used by the Makefile)
- `SERIAL_BAUD` (required) — e.g. `115200`
- `SERIAL_UART` (optional) — required if the MCU exposes more than one UART (e.g. `USART1`).
- `SERIAL_PIN_OPTION` (optional) — index (0-based) selecting the pin mapping when a UART has multiple `ports` options.
- `F_CPU` (optional) — CPU clock frequency used to compute baud registers; defaults to `16000000` if not set.

CPU clock (`F_CPU`)
-------------------

You can pass the processor clock frequency to `make` using the `F_CPU` variable. This value is used by the generator and by the compiler flags to calculate baud register values. If you do not specify `F_CPU`, the build system uses `16000000` (16 MHz) by default.

Examples:

```
make MCU=ATmega328P SERIAL_BAUD=115200 F_CPU=8000000
```

Or rely on the default 16 MHz:

```
make MCU=ATmega328P SERIAL_BAUD=115200
```

The Makefile invokes the generator automatically and will fail with a clear message if configuration is ambiguous or missing. The generator computes register values (UBRR / BD) and writes macros such as `SERIAL_BAUD`, `SERIAL_UART_NAME`, `SERIAL_TX_PORT`, `SERIAL_TX_PIN`, and `SERIAL_BAUD_REG_VALUE` into `include/generated_serial_config.h`.

Examples:

- Single-UART MCU (no UART/pin needed):
```
make MCU=ATmega328P SERIAL_BAUD=115200
```
- Multi-UART MCU, select UART:
```
make MCU=ATmega328PB SERIAL_BAUD=38400 SERIAL_UART=USART1
```
- Multi-UART with specific pin option (pin option is the index into the `ports` array):
```
make MCU=ATmega4809 SERIAL_BAUD=115200 SERIAL_UART=USART2 SERIAL_PIN_OPTION=1
```

Note: the generated header is placed at `include/generated_serial_config.h` and is automatically included by the build; you can inspect it to see the resolved register values and pin assignments.

Supported UART Architectures
----------------------------

This repository supports the UART/USART architectures enumerated in `configurations.json`:

- `USART_CLASSIC`: the traditional AVR USART with `UDRn`, `UCSRnA/B/C` and `UBRRn` (UBRR/UBRRL/UBRRH) baud registers and the classic baud equation `BAUD = fclk / (16*(BD+1))`. Typical devices: ATmega48/88/168/328 and similar classic ATmega parts.
- `USART_0SERIES`: the newer 0-series/DA/DB family where data registers are split (`RXDATALx`/`RXDATAHx`, `TXDATALx`/`TXDATAHx`) and baud is configured via `BAUDx` with routing controlled by `USARTROUTEA`. Baud calculation follows `BAUD = fclk / (2 * BD)`. Typical devices: ATmega808/1608/3208/4808/809/1609/3209/4809.

Note: LIN-style `LIN_UART` entries were intentionally removed from supported configurations and are not generated or validated by the build generator.

Supported processors (from configurations.json)
---------------------------------------------

The build currently supports the following ATmega parts (as listed in `configurations.json`):

- ATmega1284
- ATmega1284P
- ATmega1608
- ATmega1609
- ATmega164PA
- ATmega165A
- ATmega165PA
- ATmega168A
- ATmega169PA
- ATmega3208
- ATmega3209
- ATmega324PA
- ATmega324PB
- ATmega3250PA
- ATmega325PA
- ATmega328P
- ATmega328PB
- ATmega3290PA
- ATmega32A
- ATmega4808
- ATmega4809
- ATmega48A
- ATmega48PA
- ATmega644
- ATmega644A
- ATmega644P
- ATmega644PA
- ATmega649P
- ATmega64A
- ATmega808
- ATmega809
- ATmega88A
- ATmega88PA

If you need additional parts supported, add them to `configurations.json` and run the validation/generator step (the Makefile will invoke it automatically when building).

Two common targets and how to configure them:

- ATmega4809 (default)
      - No extra flags required. The build generator produces `include/generated_serial_config.h` from `configurations.json` for the selected `MCU` and `SERIAL_BAUD` and the build uses that header automatically.

- ATmega328P (classic AVR with UBRR)
      - The generator will emit sensible register aliases and a UBRR writer when possible. Typically you only need to set `MCU` and `SERIAL_BAUD`:

```bash
make MCU=ATmega328P SERIAL_BAUD=115200
```

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
- The host test runner lives at `tests/run_mctp_tests.py` and will print decoded frames and diagnostics.

