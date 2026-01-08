/**
 * @file platform.c
 * @brief Platform API shim layer for ATMEGA microcontrollers.
 * 
 * Provides implementations of platform-specific functions for serial I/O.  Initialization
 * is performed based on generated_serial_config.h settings.  Macro switches allow
 * selection of different baud rate calculation methods and uart configuration
 * depending on the target MCU family.
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
#include "generated_serial_config.h"

/* Baud helper implementations:
 * DA/DB style BAUD register and classic UBRR. Builds may override these
 * by defining MCTP_USART_SET_BAUD or MCTP_USART_WRITE_UBRR. */
#if MCTP_BAUD_MODE == MCTP_BAUD_MODE_DA_DB
    #ifndef MCTP_USART_SET_BAUD
    #define MCTP_USART_SET_BAUD(baudval) \
        do { \
            uint16_t _bsel = (uint16_t)((8UL * (uint32_t)F_CPU - (baudval)) / (2UL * (baudval))); \
            MCTP_USART_BAUD = _bsel; \
        } while (0)
    #endif
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

/**
 * @brief Initialize platform hardware.
 *
 * This function is called once by mctp_init to initialize
 * platform-specific hardware (serial interfaces, timers, etc.).
 */
void platform_init(void) {
#ifdef CPU_CCP
    /* set peripheral clock to 16 MHz (no divide) */
    CPU_CCP = CCP_IOREG_gc;
    CLKCTRL_MCLKCTRLB = 0;
#endif

    /* Configure USART route if user provided a PORTMUX value */
#ifdef PORTMUX_USARTROUTEA
    #ifdef MCTP_PORTMUX_VAL
        PORTMUX_USARTROUTEA = MCTP_PORTMUX_VAL;
    #else
        PORTMUX_USARTROUTEA = (PORTMUX_USART3_ALT1_gc | PORTMUX_USART0_NONE_gc |
                           PORTMUX_USART1_NONE_gc | PORTMUX_USART2_NONE_gc);
    #endif
#endif

    /* Configure TX pin as output and RX pin as input using configured port/pin */
    /* Use concrete register mapping macros from include/generated_serial_config.h */
    MCTP_TX_PORT_DIR |= (1 << MCTP_UART_TX_PIN);
    MCTP_RX_PORT_DIR &= ~(1 << MCTP_UART_RX_PIN);

#if defined(MCTP_USART_0SERIES)
    /* 0-series: use io-header enum values for frame format */
    MCTP_USART_CTRLC = (USART_CHSIZE_8BIT_gc) | (USART_PMODE_DISABLED_gc) |
                      (USART_SBMODE_1BIT_gc) | (USART_CMODE_ASYNCHRONOUS_gc);
#elif defined(USART_CHSIZE_8BIT_gc)
    /* Frame format and mode (8N1, async) */
    MCTP_USART_CTRLC = (USART_CHSIZE_8BIT_gc) | (USART_PMODE_DISABLED_gc) |
                     (USART_SBMODE_1BIT_gc) | (USART_CMODE_ASYNCHRONOUS_gc);
#else
    /* Frame format and mode (8N1, async) - prefer classic bit names if present */
    #if defined(UCSZ1)
        MCTP_USART_CTRLC = (1 << UCSZ1) | (1 << UCSZ0);
    #elif defined(UCSZ01)
        MCTP_USART_CTRLC = (1 << UCSZ01) | (1 << UCSZ00); /* 8-bit data */
    #else
        MCTP_USART_CTRLC = 0; /* unknown; leave as-is */
    #endif
#endif

    /* Compute BAUD using board-configured abstraction. */
    const uint32_t baud = MCTP_BAUD;
    MCTP_USART_SET_BAUD(baud);

    /* Enable TX/RX */
#ifdef USART_RXEN_bm
    MCTP_USART_CTRLB = USART_RXEN_bm | USART_TXEN_bm;
#elif defined(RXEN)
    MCTP_USART_CTRLB = (1 << RXEN) | (1 << TXEN);
#elif defined(RXEN0)
    MCTP_USART_CTRLB = (1 << RXEN0) | (1 << TXEN0);
#else
    MCTP_USART_CTRLB = 0;
#endif
}

/**
 * @brief Query whether data is available to read from the serial interface.
 *
 * @return uint8_t Returns non-zero when data is available to read.
 */
uint8_t platform_serial_has_data(void) {
    /* RX Complete flag in STATUS register indicates received data */
    #ifdef USART_RXCIF_bm        
        return (MCTP_USART_STATUS & USART_RXCIF_bm) ? 1 : 0;
    #elif defined(RXC)
        return (MCTP_USART_STATUS & (1 << RXC)) ? 1 : 0;
    #elif defined(RXC0)
        return (MCTP_USART_STATUS & (1 << RXC0)) ? 1 : 0;
    #else
        return 0;
    #endif
}

/**
 * @brief Read a byte from the serial interface. May block if no data is available.
 *
 * @return uint8_t The byte read from the serial interface.
 */
uint8_t platform_serial_read_byte(void) {
    /* Wait for data to be available, then read the low data register */
    #ifdef USART_RXCIF_bm
    while (!(MCTP_USART_STATUS & USART_RXCIF_bm)) {
            ;
        }
    #elif defined(RXC)
        while (!(MCTP_USART_STATUS & (1 << RXC))) {
            ;
        }
    #elif defined(RXC0)
        while (!(MCTP_USART_STATUS & (1 << RXC0))) {
            ;
        }
    #else
        ;
    #endif
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
    #ifdef USART_DREIF_bm
        while (!(MCTP_USART_STATUS & USART_DREIF_bm)) {
            ;
        }
    #elif defined(UDRE)
        while (!(MCTP_USART_STATUS & (1 << UDRE))) {
            ;
        }
    #elif defined(UDRE0)
        while (!(MCTP_USART_STATUS & (1 << UDRE0))) {
            ;
        }
    #else
        ;
    #endif
    MCTP_USART_TXDATAL = b;
}

/**
 * @brief Query whether the serial interface can accept writes.
 *
 * @return uint8_t Returns non-zero when writes are currently allowed.
 */
uint8_t platform_serial_can_write(void) {
    #ifdef USART_DREIF_bm
        return (MCTP_USART_STATUS & USART_DREIF_bm) ? 1 : 0;
    #elif defined(UDRE)
        return (MCTP_USART_STATUS & (1 << UDRE)) ? 1 : 0;
    #elif defined(UDRE0)
        return (MCTP_USART_STATUS & (1 << UDRE0)) ? 1 : 0;
    #else
        return 0;
    #endif
}
