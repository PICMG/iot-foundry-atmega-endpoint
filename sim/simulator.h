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
    void poll_pty_nonblocking(int idx);

    /* register access by name */
    Reg8 &reg8(const char *name);
    Reg16 &reg16(const char *name);

    /* helpers for USART indexed access */
    void txdatal_write_cb(int idx, uint8_t b);
    uint8_t status_read_cb(int idx);
    uint8_t rxdatal_read_cb(int idx);
    uint8_t udr_read_cb(int idx);
    void udr_write_cb(int idx, uint8_t b);
    uint8_t ucsra_read_cb(int idx);
      
    bool validate_configuration(int idx);

public:
    std::atomic<size_t> rx_head{0};
    std::atomic<size_t> rx_tail{0};

private:
    std::unordered_map<std::string, std::unique_ptr<Reg8>> _r8;
    std::unordered_map<std::string, std::unique_ptr<Reg16>> _r16;

    int master_fd{-1};
    char slave_name_buf[128];
    int slave_fd{-1};
};

extern Simulator simulator;

} // namespace sim
