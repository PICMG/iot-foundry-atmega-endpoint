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

## System Requirements
The following are system requirements for buidling/testing teh code in this library.

- Linux with the gnu toolchain and make tools installed.
- An atmega-based microcontroller board that is programmable using avrdude.

## Repository Resources

- `configurations.json` — A json structure that shows all serial port and MCU mappings supported by this project.  Contents of this file drive the interactive build process and the configuration header file generator (`tools/generate_serial_config.py`).
- `CONRIBUTING.md` — instructions for contributing to this project.
- `LICENSE` — The license for this project (MIT)
- `Makefile` — build, generation and flash recipes.
- `README.md` — this document.
- `include/` — public headers and generator output (see `include/generated_serial_config.h`).
  - `include/core` — (template core includes)
- `src/` — application and platform C sources
  - `src/core/` — (template core sources).
- `tools/` — helper scripts used by the build and flash workflows.
- `tests/` — test scripts and requirements for host-side tests and tooling.

## Environment Installation

Update your package index and install the AVR toolchain and `avrdude` with your distribution package manager. The packages below provide the `avr-gcc` compiler, AVR libc headers and runtime, and `avrdude` for programming.

### Debian / Ubuntu

Install the distribution-maintained AVR toolchain and `avrdude` with `apt`. This is the simplest approach on Debian-family systems and is sufficient for most development and flashing tasks:

```bash
sudo apt-get update
sudo apt-get install -y gcc-avr binutils-avr avr-libc avrdude make python3-pip

avr-gcc --version
avrdude -v
```

### Fedora / RHEL (dnf)

Use `dnf` to install equivalent packages on Fedora or RHEL derivatives:

```bash
sudo dnf install -y avr-gcc avr-binutils avr-libc avrdude make python3-pip

avr-gcc --version
avrdude -v
```

### Arch Linux

On Arch, install the toolchain from the main repositories with `pacman`:

```bash
sudo pacman -S --needed avr-gcc avr-binutils avr-libc avrdude make python-pip

avr-gcc --version
avrdude -v
```

## Build Flow

This project contains several makefile recepies to help build IoTFoundry endpoints for a variety of ATmega target devices.  To make selection of the target easy, the build process supports an an interactive mode.

### Interactive Builds
For first-time builds or when changing board configurations, run `make interactive`. This guides you through selecting the microprocessor type (`MCU`), the desired serial baud rate (`SERIAL_BAUD`), and optional UART/pin choices.  Your selections converted to a header file (to direct code compilation) and your configuration is stored for subsequent builds.

to run in interactive mode, invoke the following command:

```bash
make interactive
```

### Build Using Defaults
Once the build settings have been configured using `make interactive`, subsequent builds may be completed using the previous settings.  This is accomplished with a simple  'make' command:

```bash
make
```

### Overriding Build Defaults (Advanced)
For automation purposes, it may be useful to override (or assign) default build parameters.  To do this, each parameter to be overridden is passed to the make file like this:

```
make MCU=ATmega328P SERIAL_BAUD=115200 F_CPU=8000000
```

The table below lists all the build override paramters, and how you may obtain acceptable values for them from `configurations.json`

| Name | Description |
|---|---|
| `MCU` | Target part name that must match a `part_numbers` entry in `configurations.json` (case-insensitive). Open `configurations.json`, find the entry whose `part_numbers` list contains your device (for example `ATmega328P`), and use that exact part string. |
| `SERIAL_BAUD` | Numeric UART baud rate used by the firmware (e.g., `115200`). The generator uses it together with `F_CPU` to compute baud register values. |
| `SERIAL_UART` | Select the serial interface by the `name` field from the matching MCU entry's `serial_ports` array in `configurations.json` (for example `USART1`). Use that `name`. |
| `SERIAL_PIN_OPTION` | When the chosen `serial_ports` entry contains a `ports` array, this is the zero-based index into that array selecting the TX/RX pin mapping. Inspect the `ports` array for the chosen `serial_ports` entry in `configurations.json` and use `0`, `1`, etc. to pick the mapping. |
| `F_CPU` | CPU clock frequency used to calculate baud registers (e.g., `16000000` or `8000000`).  |

## Programming Target Devices
This project contains makefile recepies to help program IoTFoundry endpoints.  To make programming of the target easy, the build process supports an an interactive mode.

### Interactive Programming
For first-time programming or when changing a program target, run `make flash_interactive`. This guides you through selecting target device, programmer, and programming speed. Your selections are stored for subsequent programming sessions.

Invoke interactive programming using the following make command:

```bash
make flash_interactive
```

### Programming Using Defaults
Once the programming settings have been configured using `make flash_interactive`, subsequent programming sessions may be completed using the previous settings.  This is accomplished with the 'make flash' command:

```bash
make flash
```

### Overriding Programmer Defaults (Advanced)
For automation purposes, it may be useful to override (or assign) default programming parameters.  To do this, each parameter to be overridden is passed to the make file like this:

```bash
make flash PROG=jtag2updi PORT=/dev/ttyACM0 PROG_BAUD=115200
```
The following table shows parameters that may be overridden.

| Name | Description |
|---|---|
| `PROG` | avrdude programmer type (e.g., `arduino`, `stk500v1`, `usbasp`,`jtag2updi`). Choose a value supported by `avrdude` for your target hardware. |
| `PORT` | Host serial device used for flashing (e.g., `/dev/ttyACM0`, `/dev/ttyUSB0`).  |
| `PROG_BAUD` | Baud rate passed to `avrdude` for the chosen programmer (default `115200`).  |
| `MCU` | MCU used for the build/flash. `make flash` prefers `include/last_mcu` (written by the generator) but you can override with `MCU=<part>` on the command line; the part should match a `part_numbers` entry in `configurations.json`. |

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

# Editor integration notes
If your editor expects a `compile_commands.json` compilation database for IDE features (IntelliSense, clangd, etc.), generate one externally from your build system or use your editor's project settings. This repository no longer generates `compile_commands.json` automatically.

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

