#pragma once

/* Central mapping header that redirects legacy device register symbols
 * to the single `sim::simulator` instance. Keep this header minimal
 * (no includes of the AVR shim) to avoid circular includes.
 */

#include "simulator.h"

#define USART0_RXDATAL   (sim::simulator.reg8("USART0_RXDATAL"))
#define USART0_TXDATAL   (sim::simulator.reg8("USART0_TXDATAL"))
#define USART0_STATUS    (sim::simulator.reg8("USART0_STATUS"))
#define USART0_CTRLA     (sim::simulator.reg8("USART0_CTRLA"))
#define USART0_CTRLB     (sim::simulator.reg8("USART0_CTRLB"))
#define USART0_CTRLC     (sim::simulator.reg8("USART0_CTRLC"))
#define USART0_BAUD      (sim::simulator.reg16("USART0_BAUD"))

#define USART1_RXDATAL   (sim::simulator.reg8("USART1_RXDATAL"))
#define USART1_TXDATAL   (sim::simulator.reg8("USART1_TXDATAL"))
#define USART1_STATUS    (sim::simulator.reg8("USART1_STATUS"))
#define USART1_CTRLA     (sim::simulator.reg8("USART1_CTRLA"))
#define USART1_CTRLB     (sim::simulator.reg8("USART1_CTRLB"))
#define USART1_CTRLC     (sim::simulator.reg8("USART1_CTRLC"))
#define USART1_BAUD      (sim::simulator.reg16("USART1_BAUD"))

#define USART2_RXDATAL   (sim::simulator.reg8("USART2_RXDATAL"))
#define USART2_TXDATAL   (sim::simulator.reg8("USART2_TXDATAL"))
#define USART2_STATUS    (sim::simulator.reg8("USART2_STATUS"))
#define USART2_CTRLA     (sim::simulator.reg8("USART2_CTRLA"))
#define USART2_CTRLB     (sim::simulator.reg8("USART2_CTRLB"))
#define USART2_CTRLC     (sim::simulator.reg8("USART2_CTRLC"))
#define USART2_BAUD      (sim::simulator.reg16("USART2_BAUD"))

#define USART3_RXDATAL   (sim::simulator.reg8("USART3_RXDATAL"))
#define USART3_TXDATAL   (sim::simulator.reg8("USART3_TXDATAL"))
#define USART3_STATUS    (sim::simulator.reg8("USART3_STATUS"))
#define USART3_CTRLA     (sim::simulator.reg8("USART3_CTRLA"))
#define USART3_CTRLB     (sim::simulator.reg8("USART3_CTRLB"))
#define USART3_CTRLC     (sim::simulator.reg8("USART3_CTRLC"))
#define USART3_BAUD      (sim::simulator.reg16("USART3_BAUD"))

#define UDR0             (sim::simulator.reg8("UDR0"))
#define UCSR0A           (sim::simulator.reg8("UCSR0A"))
#define UCSR0B           (sim::simulator.reg8("UCSR0B"))
#define UCSR0C           (sim::simulator.reg8("UCSR0C"))
#define UBRR0            (sim::simulator.reg16("UBRR0"))

#ifndef  UDR0
    #define UDR              (sim::simulator.reg8("UDR0"))
    #define UCSRA            (sim::simulator.reg8("UCSR0A"))
    #define UCSRB            (sim::simulator.reg8("UCSR0B"))
    #define UCSRC            (sim::simulator.reg8("UCSR0C"))
    #define UBRR             (sim::simulator.reg16("UBRR0"))
#endif

#define UDR1             (sim::simulator.reg8("UDR1"))
#define UCSR1A           (sim::simulator.reg8("UCSR1A"))
#define UCSR1B           (sim::simulator.reg8("UCSR1B"))
#define UCSR1C           (sim::simulator.reg8("UCSR1C"))
#define UBRR1            (sim::simulator.reg16("UBRR1"))

#define UDR2             (sim::simulator.reg8("UDR2"))
#define UCSR2A           (sim::simulator.reg8("UCSR2A"))
#define UCSR2B           (sim::simulator.reg8("UCSR2B"))
#define UCSR2C           (sim::simulator.reg8("UCSR2C"))
#define UBRR2            (sim::simulator.reg16("UBRR2"))

#define UDR3             (sim::simulator.reg8("UDR3"))
#define UCSR3A           (sim::simulator.reg8("UCSR3A"))
#define UCSR3B           (sim::simulator.reg8("UCSR3B"))
#define UCSR3C           (sim::simulator.reg8("UCSR3C"))
#define UBRR3            (sim::simulator.reg16("UBRR3"))

#define PORTA_DIR        (sim::simulator.reg8("PORTA_DIR"))
#define PORTB_DIR        (sim::simulator.reg8("PORTB_DIR"))
#define PORTC_DIR        (sim::simulator.reg8("PORTC_DIR"))
#define PORTD_DIR        (sim::simulator.reg8("PORTD_DIR"))
#define PORTE_DIR        (sim::simulator.reg8("PORTE_DIR"))
#define PORTF_DIR        (sim::simulator.reg8("PORTF_DIR"))
#define DDRA             (sim::simulator.reg8("PORTA_DIR"))
#define DDRB             (sim::simulator.reg8("PORTB_DIR"))
#define DDRC             (sim::simulator.reg8("PORTC_DIR"))
#define DDRD             (sim::simulator.reg8("PORTD_DIR"))
#define DDRE             (sim::simulator.reg8("PORTE_DIR"))
#define DDRF             (sim::simulator.reg8("PORTF_DIR"))

#define CPU_CCP          (sim::simulator.reg8("CPU_CCP"))
#define CLKCTRL_MCLKCTRLB (sim::simulator.reg8("CLKCTRL_MCLKCTRLB"))
#define PORTMUX_USARTROUTEA (sim::simulator.reg8("PORTMUX_USARTROUTEA"))


#include <avr/io.h>

