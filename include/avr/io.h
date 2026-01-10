/* Minimal shim for <avr/io.h> when building the host simulator.
 * When SIM_HOST is defined, this header provides the subset of
 * register names and bit masks used by platform.c and redirects
 * accesses to simulator objects implemented in C++.
 * Otherwise, include the real device header.
 */
#ifndef INCLUDE_AVR_IO_H_SIM_SHIM
#define INCLUDE_AVR_IO_H_SIM_SHIM

#ifdef SIM_HOST

#include "generated_serial_config.h"
#include <stdint.h>

typedef uint8_t register8_t;
typedef uint16_t register16_t;

/* Provide a fallback F_CPU if the sim build didn't pass it in
 * (the Makefile will be patched to pass -DF_CPU, but keep a default).
 */
#ifndef F_CPU
#define F_CPU 16000000UL
#endif

#if defined(__has_include)
# if __has_include("generated_avr_masks.h")
#  include "generated_avr_masks.h"
# endif
#endif

/* Minimal bit/enum constants used by platform.c. Define only when missing
 * so we don't override device-provided values pulled in via generated_avr_masks.h.
 */
#ifdef SERIAL_UART_TYPE_USART_0SERIES
    #ifndef USART_CHSIZE_8BIT_gc
    #define USART_CHSIZE_8BIT_gc (0x03<<0)
    #endif
    #ifndef USART_PMODE_DISABLED_gc
    #define USART_PMODE_DISABLED_gc (0x00<<4)
    #endif
    #ifndef USART_SBMODE_1BIT_gc
    #define USART_SBMODE_1BIT_gc (0x00<<3)
    #endif
    #ifndef USART_CMODE_ASYNCHRONOUS_gc
    #define USART_CMODE_ASYNCHRONOUS_gc (0x00<<6)
    #endif

    #ifndef USART_RXEN_bm
    #define USART_RXEN_bm 0x80
    #endif
    #ifndef USART_TXEN_bm
    #define USART_TXEN_bm 0x40
    #endif
    #ifndef USART_DREIF_bm
    #define USART_DREIF_bm 0x20
    #endif
    #ifndef USART_RXCIF_bm
    #define USART_RXCIF_bm 0x80
    #endif
#else 
    #ifndef RXC
        #define RXC 7
    #endif
    #ifndef TXC
        #define TXC 6
    #endif
    #ifndef UDRE
        #define UDRE 5
    #endif
    #ifndef RXEN
        #define RXEN 4
    #endif
    #ifndef TXEN
        #define TXEN 3
    #endif
    #ifndef UCSZ1
        #define UCSZ1 2
        #endif
    #ifndef UCSZ0
        #define UCSZ0 1
    #endif
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* Forward-declare simulator-backed register objects for C builds. */
struct sim_reg8_t; /* opaque for C */
extern volatile uint8_t SIM_DUMMY; /* placeholder for C builds */

#ifdef __cplusplus
}

/* Include simulator register class definitions so the C++ build sees
 * `sim::Reg8` and `sim::Reg16` (with operator overloads). Use a
 * relative path from this header (which lives in include/).
 */
#include "../sim/sim_regs.h"

/* Define a simple macro for CCP IOREG constant used by platform.c */
#ifndef CCP_IOREG_gc
#define CCP_IOREG_gc 0
#endif

/* When building the simulator we map register symbols to the single
 * `sim::simulator` instance via macros in sim/sim_regs.h. Do not declare
 * C++ `extern sim::Reg8` symbols here to avoid conflicts with those macros. */

#else
/* When not compiling C++ (shouldn't happen for simulator), provide
 * simple volatile variables to avoid compile errors. */
extern volatile uint8_t USART0_RXDATAL;
extern volatile uint8_t USART0_TXDATAL;
extern volatile uint8_t USART0_STATUS;
extern volatile uint8_t USART0_CTRLA;
extern volatile uint8_t USART0_CTRLB;
extern volatile uint8_t USART0_CTRLC;
extern volatile uint16_t USART0_BAUD;
#endif /* __cplusplus */

#else /* SIM_HOST */

/* Not building simulator: include the real device headers. Use include_next
 * so we forward to the toolchain-provided <avr/io.h>. */
#include_next <avr/io.h>

#endif /* SIM_HOST */

#endif /* INCLUDE_AVR_IO_H_SIM_SHIM */
