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
#include <stdio.h>
#include "core/platform.h"
#include "generated_serial_config.h"
#ifdef SIM_HOST
#include "../sim/sim_c_api.h"
#endif

/* Token-paste helpers for deriving register tokens from numeric UART index
 * and port letters emitted by the generator (SERIAL_UART_INDEX, SERIAL_TX_PORT, etc.). */
#define CAT2(a, b) a##b
#define CAT3(a, b, c) a##b##c
#define CONCAT2(a, b) CAT2(a, b)
#define CONCAT3(a, b, c) CAT3(a, b, c)

/* Derive family-specific register aliases. Use SERIAL_UART_TYPE_USART_0SERIES
 * (emitted by the generator) to choose the naming convention. */
#if defined(SERIAL_UART_TYPE_USART_0SERIES)
    #define USART_RXDATAL  CONCAT3(USART, SERIAL_UART_INDEX, _RXDATAL)
    #define USART_TXDATAL  CONCAT3(USART, SERIAL_UART_INDEX, _TXDATAL)
    #define USART_STATUS   CONCAT3(USART, SERIAL_UART_INDEX, _STATUS)
    #define USART_CTRLA    CONCAT3(USART, SERIAL_UART_INDEX, _CTRLA)
    #define USART_CTRLB    CONCAT3(USART, SERIAL_UART_INDEX, _CTRLB)
    #define USART_CTRLC    CONCAT3(USART, SERIAL_UART_INDEX, _CTRLC)
    #define USART_BAUD     CONCAT3(USART, SERIAL_UART_INDEX, _BAUD)
    #define TX_PORT_DIR    CONCAT3(PORT, SERIAL_TX_PORT, _DIR)
    #define RX_PORT_DIR    CONCAT3(PORT, SERIAL_RX_PORT, _DIR)
    #define SERIAL_BAUD_VAL SERIAL_BAUD
#else
    #define USART_RXDATAL  CONCAT2(UDR, SERIAL_UART_INDEX)
    #define USART_TXDATAL  CONCAT2(UDR, SERIAL_UART_INDEX)
    #define USART_STATUS   CONCAT3(UCSR, SERIAL_UART_INDEX, A)
    #define USART_CTRLA    CONCAT3(UCSR, SERIAL_UART_INDEX, A)
    #define USART_CTRLB    CONCAT3(UCSR, SERIAL_UART_INDEX, B)
    #define USART_CTRLC    CONCAT3(UCSR, SERIAL_UART_INDEX, C)
    #define USART_BAUD     CONCAT2(UBRR, SERIAL_UART_INDEX)
    #define TX_PORT_DIR    CONCAT2(DDR, SERIAL_TX_PORT)
    #define RX_PORT_DIR    CONCAT2(DDR, SERIAL_RX_PORT)
    #define SERIAL_BAUD_VAL SERIAL_BAUD
#endif

/**
 * @brief Initialize platform hardware.
 *
 * This function is called once by mctp_init to initialize
 * platform-specific hardware (serial interfaces, timers, etc.).
 */
void platform_init(void) {
    #if defined(SERIAL_UART_TYPE_USART_0SERIES)
        /* set peripheral clock to 16 MHz (no divide) for 0-series */
        CPU_CCP = CCP_IOREG_gc;
        CLKCTRL_MCLKCTRLB = 0;
    #endif

    /* Configure USART route if required */
    #ifdef SERIAL_MUXREG
        #ifdef SERIAL_MUX_ANDMASK
            SERIAL_MUXREG = (SERIAL_MUXREG & SERIAL_MUX_ANDMASK) | SERIAL_MUX_ORMASK;
        #else
            SERIAL_MUXREG = SERIAL_MUX_ORMASK;
        #endif
    #endif

    /* Configure TX pin as output and RX pin as input using configured port/pin */
    TX_PORT_DIR |= (1 << SERIAL_TX_PIN);
    RX_PORT_DIR &= ~(1 << SERIAL_RX_PIN);

    /* Configure frame format and mode. Use token-pasted `USART_*` aliases
    * derived from `SERIAL_UART_INDEX` (and header enums when available). */
    #if defined(SERIAL_UART_TYPE_USART_0SERIES) || defined(USART_CHSIZE_8BIT_gc)
        /* 0-series or headers providing convenient enums: write typical 8N1 async */
        USART_CTRLC = (USART_CHSIZE_8BIT_gc) | (USART_PMODE_DISABLED_gc) |
                    (USART_SBMODE_1BIT_gc) | (USART_CMODE_ASYNCHRONOUS_gc);
    #else
        /* Fallback to classic bit-field names where available, else clear */
        #if defined(UCSZ1) && defined(UCSZ0)
            USART_CTRLC = (1 << UCSZ1) | (1 << UCSZ0);
        #elif defined(UCSZ01) && defined(UCSZ00)
            USART_CTRLC = (1 << UCSZ01) | (1 << UCSZ00);
        #else
            USART_CTRLC = 0;
        #endif
    #endif

    /* Compute BAUD using board-specific method. */
    const uint32_t baud = SERIAL_BAUD_VAL;
    #if defined(SERIAL_UART_TYPE_USART_0SERIES)
        /* DA/DB style BAUD register (0-series) */
        uint16_t _bsel = (uint16_t)((8UL * (uint32_t)F_CPU) / (2UL * (baud)));
        USART_BAUD = _bsel;
    #else
        /* Classic AVR UBRR calculation: compute UBRR and write it into UBRRn. */
        uint16_t _ubrr = (uint16_t)(((uint32_t)F_CPU / (16UL * (uint32_t)(baud))) - 1UL);
        USART_BAUD = _ubrr;
    #endif

    /* Enable TX/RX */
    #ifdef USART_RXEN_bm
        USART_CTRLB = USART_RXEN_bm | USART_TXEN_bm;
    #elif defined(RXEN)
        USART_CTRLB = (1 << RXEN) | (1 << TXEN);
    #elif defined(RXEN0)
        USART_CTRLB = (1 << RXEN0) | (1 << TXEN0);
    #else
        USART_CTRLB = 0;
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
        #ifdef SIM_HOST
            return (sim_read_usart_status(SERIAL_UART_INDEX) & USART_RXCIF_bm) ? 1 : 0;
        #else
            return (USART_STATUS & USART_RXCIF_bm) ? 1 : 0;
        #endif
    #elif defined(RXC)
        return (USART_STATUS & (1 << RXC)) ? 1 : 0;
    #elif defined(RXC0)
        return (USART_STATUS & (1 << RXC0)) ? 1 : 0;
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
        #ifdef SIM_HOST
            while (!(sim_read_usart_status(SERIAL_UART_INDEX) & USART_RXCIF_bm)) { ; }
        #else
            while (!(USART_STATUS & USART_RXCIF_bm)) { ; }
        #endif
    #elif defined(RXC)
        #ifdef SIM_HOST
            while (!(sim_read_usart_status(SERIAL_UART_INDEX) & (1 << RXC))) { ; }
        #else
            while (!(USART_STATUS & (1 << RXC))) { ; }
        #endif
    #elif defined(RXC0)
        #ifdef SIM_HOST
            while (!(sim_read_usart_status(SERIAL_UART_INDEX) & (1 << RXC0))) { ; }
        #else
            while (!(USART_STATUS & (1 << RXC0))) { ; }
        #endif
    #else
        ;
    #endif
    /* Debug: print addresses of STATUS and RXDATAL to confirm symbol identity */
    fprintf(stderr, "platform: addr USART_STATUS=%p USART_RXDATAL=%p\n", (void*)&USART_STATUS, (void*)&USART_RXDATAL);
    #ifdef SIM_HOST
    uint8_t b = sim_read_usart_rxdatal(SERIAL_UART_INDEX);
    #else
    uint8_t b = (uint8_t)USART_RXDATAL;
    #endif
    (void)b;
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
        #ifdef SIM_HOST
            while (!(sim_read_usart_status(SERIAL_UART_INDEX) & USART_DREIF_bm)) { ; }
        #else
            while (!(USART_STATUS & USART_DREIF_bm)) { ; }
        #endif
    #elif defined(UDRE)
        #ifdef SIM_HOST
            while (!(sim_read_usart_status(SERIAL_UART_INDEX) & (1 << UDRE))) { ; }
        #else
            while (!(USART_STATUS & (1 << UDRE))) { ; }
        #endif
    #elif defined(UDRE0)
        #ifdef SIM_HOST
            while (!(sim_read_usart_status(SERIAL_UART_INDEX) & (1 << UDRE0))) { ; }
        #else
            while (!(USART_STATUS & (1 << UDRE0))) { ; }
        #endif
    #else
        ;
    #endif
    #ifdef SIM_HOST
        sim_write_usart_tx(SERIAL_UART_INDEX, b);
    #else
        USART_TXDATAL = b;
    #endif
}

/**
 * @brief Query whether the serial interface can accept writes.
 *
 * @return uint8_t Returns non-zero when writes are currently allowed.
 */
uint8_t platform_serial_can_write(void) {
    #ifdef USART_DREIF_bm
        return (USART_STATUS & USART_DREIF_bm) ? 1 : 0;
    #elif defined(UDRE)
        return (USART_STATUS & (1 << UDRE)) ? 1 : 0;
    #elif defined(UDRE0)
        return (USART_STATUS & (1 << UDRE0)) ? 1 : 0;
    #else
        return 0;
    #endif
}
