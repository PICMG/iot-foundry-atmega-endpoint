/**
 * @file platform.c
 * @brief Platform API shim layer for ATMEGA microcontrollers.
 *
 * @author Douglas Sandy
 *
 * MIT No Attribution
 *
 * Copyright (c) 2025 Doug
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to
 * deal in the Software without restriction, including without limitation the
 * rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
 * sell copies of the Software, and to permit persons to whom the Software is
 * furnished to do so.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */

#include <stdint.h>
#include <avr/io.h>
#include "core/platform.h"
#include "board_config.h"

/* Baud helper implementations live here so board_config.h only contains
 * selection switches. Implement the common cases: DA/DB style BAUD register
 * and classic UBRR. Boards may override these by defining
 * MCTP_USART_SET_BAUD or MCTP_USART_WRITE_UBRR via BOARD_CFLAGS. */
#if MCTP_BAUD_MODE == MCTP_BAUD_MODE_DA_DB
#ifndef MCTP_USART_SET_BAUD
#define MCTP_USART_SET_BAUD(baudval) \
    do { \
        uint16_t _bsel = (uint16_t)((8UL * (uint32_t)F_CPU - (baudval)) / (2UL * (baudval))); \
        MCTP_USART_BAUD = _bsel; \
    } while (0)
#endif
#
/* Token-paste and register concatenation helpers (local to platform.c).
 * These are only needed when platform code needs to form register names
 * from macros; keeping them local avoids polluting board_config.h.
 */
#define CAT(a,b) a##b
#define CAT2(a,b) CAT(a,b)
#define PORT_OF(p) CAT2(PORT, p)
#define DIRSET_OF(p) CAT2(p, .DIRSET)
#define DIRCLR_OF(p) CAT2(p, .DIRCLR)
#define PIN_OF(p) CAT2(PIN, p)
#define USART_OF(n) CAT2(USART, n)

/* Generic register concatenation helper: REG(USART_OF(MCTP_USART_NUM), STATUS)
 * -> USART3_STATUS */
#define REG2(a,b) a##_##b
#define REG(a,b) REG2(a,b)
#elif MCTP_BAUD_MODE == MCTP_BAUD_MODE_CLASSIC
#ifndef MCTP_USART_WRITE_UBRR
/* Default writer: place UBRR value into MCTP_USART_BAUD alias. Boards
 * targeting classic AVRs should provide a proper MCTP_USART_WRITE_UBRR. */
#define MCTP_USART_WRITE_UBRR(v) do { MCTP_USART_BAUD = (v); } while (0)
#endif
#ifndef MCTP_USART_SET_BAUD
#define MCTP_USART_SET_BAUD(baudval) \
    do { \
        uint16_t _ubrr = (uint16_t)(((uint32_t)F_CPU / (16UL * (uint32_t)(baudval))) - 1UL); \
        MCTP_USART_WRITE_UBRR(_ubrr); \
    } while (0)
#endif
#else
/* AUTO or unknown: fallback to DA/DB formula */
#ifndef MCTP_USART_SET_BAUD
#define MCTP_USART_SET_BAUD(baudval) \
    do { \
        uint16_t _bsel = (uint16_t)((8UL * (uint32_t)F_CPU - (baudval)) / (2UL * (baudval))); \
        MCTP_USART_BAUD = _bsel; \
    } while (0)
#endif
#endif

/* platform configuration is provided by src/board_config.h which exposes
 * MCTP_USART_NUM, MCTP_UART_TX_PORT, MCTP_UART_TX_PIN, MCTP_UART_RX_PORT,
 * MCTP_UART_RX_PIN, and MCTP_BAUD. MCU and F_CPU may also be overridden
 * via that header or via -D flags in the build.
 */

/**
 * @brief Initialize platform hardware.
 *
 * This function is called once by mctp_init to initialize
 * platform-specific hardware (serial interfaces, timers, etc.).
 */
void platform_init(void) {
    /* set peripheral clock to 16 MHz (no divide) */
    CPU_CCP = CCP_IOREG_gc;
    CLKCTRL_MCLKCTRLB = 0;

    /* Configure USART route if user provided a PORTMUX value */
#ifdef MCTP_PORTMUX_VAL
    PORTMUX_USARTROUTEA = MCTP_PORTMUX_VAL;
#else
    PORTMUX_USARTROUTEA = (PORTMUX_USART3_ALT1_gc | PORTMUX_USART0_NONE_gc |
                           PORTMUX_USART1_NONE_gc | PORTMUX_USART2_NONE_gc);
#endif

    /* Configure TX pin as output and RX pin as input using configured port/pin */
    /* Use concrete register mapping macros from board_config.h */
    MCTP_TX_PORT_DIR |= (1 << MCTP_UART_TX_PIN);
    MCTP_RX_PORT_DIR &= ~(1 << MCTP_UART_RX_PIN);

    /* Frame format and mode (8N1, async) */
    MCTP_USART_CTRLC = (USART_CHSIZE_8BIT_gc) | (USART_PMODE_DISABLED_gc) |
                     (USART_SBMODE_1BIT_gc) | (USART_CMODE_ASYNCHRONOUS_gc);

    /* Compute BAUD using board-configured abstraction. */
    const uint32_t baud = MCTP_BAUD;
    MCTP_USART_SET_BAUD(baud);

    /* Enable TX/RX and (optionally) RX/DRE interrupts as in your working code */
    MCTP_USART_CTRLB = USART_RXEN_bm | USART_TXEN_bm;
    MCTP_USART_CTRLA |= USART_RXCIE_bm | USART_DREIE_bm;
}

/**
 * @brief Query whether data is available to read from the serial interface.
 *
 * @return uint8_t Returns non-zero when data is available to read.
 */
uint8_t platform_serial_has_data(void) {
    /* RX Complete flag in STATUS register indicates received data */
    return (MCTP_USART_STATUS & USART_RXCIF_bm) ? 1 : 0;
}

/**
 * @brief Read a byte from the serial interface. May block if no data is available.
 *
 * @return uint8_t The byte read from the serial interface.
 */
uint8_t platform_serial_read_byte(void) {
    /* Wait for data to be available, then read the low data register */
    while (!(MCTP_USART_STATUS & USART_RXCIF_bm)) {
        ;
    }
    uint8_t b = (uint8_t)MCTP_USART_RXDATAL;
    return (uint8_t)b;
}

/**
 * @brief Write a byte to the serial interface. May block if the interface is not ready.
 *
 * @param b The byte to write.
 */
void platform_serial_write_byte(uint8_t b) {   
    /* Wait until Data Register Empty, then write */
    while (!(MCTP_USART_STATUS & USART_DREIF_bm)) {
        ;
    }
    MCTP_USART_TXDATAL = b;
}

/**
 * @brief Query whether the serial interface can accept writes.
 *
 * @return uint8_t Returns non-zero when writes are currently allowed.
 */
uint8_t platform_serial_can_write(void) {
    return (MCTP_USART_STATUS & USART_DREIF_bm) ? 1 : 0;
}
