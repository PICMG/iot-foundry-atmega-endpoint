/* Board configuration header
 * Provides build-time macros for selecting MCU, clock and UART pins/peripheral
 * without editing core files. Defaults are safe for current board.
 */
#ifndef BOARD_CONFIG_H
#define BOARD_CONFIG_H

/* MCU and clock (can be overridden via -D on the compiler command line) */
#ifndef MCU_TYPE
#define MCU_TYPE atmega4809
#endif

#ifndef F_CPU
#define F_CPU 16000000UL
#endif

/* UART/peripheral selection */
#ifndef MCTP_USART_NUM
#define MCTP_USART_NUM 3
#endif

/* Ports are specified as single letters (A, B, C, ...). Pins are numbers. */
#ifndef MCTP_UART_TX_PORT
#define MCTP_UART_TX_PORT B
#endif
#ifndef MCTP_UART_TX_PIN
#define MCTP_UART_TX_PIN 4
#endif
#ifndef MCTP_UART_RX_PORT
#define MCTP_UART_RX_PORT B
#endif
#ifndef MCTP_UART_RX_PIN
#define MCTP_UART_RX_PIN 5
#endif

#ifndef MCTP_BAUD
#define MCTP_BAUD 9600UL
#endif

/* Convenience register mappings for the selected USART and ports.
 * These default to USART3 / PORTB pins used previously. Override via
 * -D flags if you need different tokens (e.g. -DMCTP_USART_CTRLC=USART1_CTRLC).
 */
#ifndef MCTP_USART_CTRLC
#define MCTP_USART_CTRLC USART3_CTRLC
#endif
#ifndef MCTP_USART_BAUD
#define MCTP_USART_BAUD USART3_BAUD
#endif
#ifndef MCTP_USART_CTRLB
#define MCTP_USART_CTRLB USART3_CTRLB
#endif
#ifndef MCTP_USART_CTRLA
#define MCTP_USART_CTRLA USART3_CTRLA
#endif
#ifndef MCTP_USART_STATUS
#define MCTP_USART_STATUS USART3_STATUS
#endif
#ifndef MCTP_USART_RXDATAL
#define MCTP_USART_RXDATAL USART3_RXDATAL
#endif
#ifndef MCTP_USART_TXDATAL
#define MCTP_USART_TXDATAL USART3_TXDATAL
#endif

#ifndef MCTP_TX_PORT_DIR
#define MCTP_TX_PORT_DIR PORTB_DIR
#endif
#ifndef MCTP_RX_PORT_DIR
#define MCTP_RX_PORT_DIR PORTB_DIR
#endif

/* Baud selection mode:
 * - MCTP_BAUD_MODE_DA_DB: use AVR DA/DB single BAUD register (BSEL/BSCALE style)
 * - MCTP_BAUD_MODE_CLASSIC: use classic UBRR calculation (UBRRnH/UBRRnL)
 * - MCTP_BAUD_MODE_AUTO: default; currently defaults to DA/DB behavior
 */
#ifndef MCTP_BAUD_MODE_DA_DB
#define MCTP_BAUD_MODE_DA_DB 1
#endif
#ifndef MCTP_BAUD_MODE_CLASSIC
#define MCTP_BAUD_MODE_CLASSIC 2
#endif
#ifndef MCTP_BAUD_MODE_AUTO
#define MCTP_BAUD_MODE_AUTO 0
#endif

#ifndef MCTP_BAUD_MODE
/* Default to DA/DB family behavior (matches ATmega4809 target). Override
 * via -DMCTP_BAUD_MODE=MCTP_BAUD_MODE_CLASSIC for classic AVRs. */
#define MCTP_BAUD_MODE MCTP_BAUD_MODE_DA_DB
#endif
/* Baud setter helpers are intentionally implemented in src/platform.c so
 * board_config.h stays minimal and only exposes the selection switches.
 * If a board needs a custom setter, define MCTP_USART_SET_BAUD or
 * MCTP_USART_WRITE_UBRR via BOARD_CFLAGS (e.g. -DMCTP_USART_WRITE_UBRR=...).
 */
#endif /* BOARD_CONFIG_H */
