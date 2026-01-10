#pragma once

#include <string>
#include <unordered_map>
#include <vector>
#include <memory>
#include <atomic>
#include <cstddef>
#include "sim_types.h"

namespace sim {

class Simulator {
public:
    Simulator();
    ~Simulator();

    /* PTY/IO management */
    const char* init_pty();
    void poll_pty_nonblocking();
    void ensure_poll();

    /* RX/TX helpers */
    bool rx_push(uint8_t b);
    int rx_pop();
    void tx_write(uint8_t b);

    /* register access by name */
    Reg8 &reg8(const char *name);
    Reg16 &reg16(const char *name);

    /* helpers for USART indexed access */
    void write_usart_tx(int idx, uint8_t b);
    uint8_t read_usart_status(int idx);
    uint8_t read_usart_rxdatal(int idx);

public:
    std::atomic<size_t> rx_head{0};
    std::atomic<size_t> rx_tail{0};

private:
    std::unordered_map<std::string, std::unique_ptr<Reg8>> _r8;
    std::unordered_map<std::string, std::unique_ptr<Reg16>> _r16;

    int master_fd{-1};
    char slave_name_buf[128];
    int slave_fd{-1};

    size_t available_bytes();
};

extern Simulator simulator;

} // namespace sim
