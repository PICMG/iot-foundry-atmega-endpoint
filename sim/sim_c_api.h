#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* C API used by platform.c when built for SIM_HOST. These functions
 * forward to the simulator-backed register objects so platform code
 * accesses the same underlying storage as the simulator.
 */
uint8_t sim_read_usart_status(int uart_index);
uint8_t sim_read_usart_rxdatal(int uart_index);
void sim_write_usart_tx(int uart_index, uint8_t b);

#ifdef __cplusplus
}
#endif
