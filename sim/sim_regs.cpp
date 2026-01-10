// Clean, single-definition simulator implementation.
#include "simulator.h"
#include "sim_types.h"
#include <fcntl.h>
#include <unistd.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <pty.h>
#include <termios.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <sys/ioctl.h>

namespace sim {

Simulator::Simulator() {
    master_fd = -1;
    slave_fd = -1;
    slave_name_buf[0] = '\0';

    /* Perform PTY creation and default register setup here so we avoid
     * calling methods on the global `simulator` from a separate
     * constructor-attribute function which may run before C++ object
     * dynamic initialization in some environments. */
    const char* slave = init_pty();
    if (slave) {
        fprintf(stderr, "sim: pty slave=%s\n", slave);
        FILE *pf = fopen("sim/pty_slave.txt", "w");
        if (pf) { fprintf(pf, "%s\n", slave); fclose(pf); }
    } else {
        fprintf(stderr, "sim: failed to create pty\n");
    }

    /* initialize default status bits (DRE interrupt enabled) */
    reg8("USART0_STATUS").raw_store(0x20);
    reg8("USART1_STATUS").raw_store(0x20);
    reg8("USART2_STATUS").raw_store(0x20);
    reg8("USART3_STATUS").raw_store(0x20);

    /* install simple callbacks */
    reg8("PORTA_DIR").set_write_cb([this](uint8_t v){ this->reg8("PORTA_DIR").raw_store(v); fprintf(stderr, "sim: write PORTA_DIR <- 0x%02x\n", (int)v); });
}

Simulator::~Simulator() {
    if (master_fd >= 0) close(master_fd);
    if (slave_fd >= 0) close(slave_fd);
}

const char* Simulator::init_pty() {
    int mfd = posix_openpt(O_RDWR | O_NOCTTY);
    if (mfd < 0) return nullptr;
    if (grantpt(mfd) != 0 || unlockpt(mfd) != 0) {
        close(mfd);
        return nullptr;
    }
    char *p = ptsname(mfd);
    if (!p) { close(mfd); return nullptr; }
    strncpy(slave_name_buf, p, sizeof(slave_name_buf)-1);
    slave_name_buf[sizeof(slave_name_buf)-1] = '\0';
    master_fd = mfd;
    int flags = fcntl(master_fd, F_GETFL, 0);
    fcntl(master_fd, F_SETFL, flags | O_NONBLOCK);
    return slave_name_buf;
}

size_t Simulator::available_bytes() {
    if (master_fd < 0) return 0;
    int avail = 0;
    if (ioctl(master_fd, FIONREAD, &avail) == 0 && avail > 0) return (size_t)avail;
    return 0;
}

void Simulator::poll_pty_nonblocking() {
    if (master_fd < 0) return;
    uint8_t tmp[256];
    ssize_t r = ::read(master_fd, tmp, sizeof(tmp));
    if (r > 0) {
        /* Store received byte into all RX data registers so any UART
         * index used by the firmware will observe the incoming byte. */
        reg8("USART0_RXDATAL").raw_store(tmp[0]);
        reg8("USART1_RXDATAL").raw_store(tmp[0]);
        reg8("USART2_RXDATAL").raw_store(tmp[0]);
        reg8("USART3_RXDATAL").raw_store(tmp[0]);
        /* Set RX complete bit (0x80) on all status registers. */
        reg8("USART0_STATUS").raw_store(reg8("USART0_STATUS").raw() | 0x80);
        reg8("USART1_STATUS").raw_store(reg8("USART1_STATUS").raw() | 0x80);
        reg8("USART2_STATUS").raw_store(reg8("USART2_STATUS").raw() | 0x80);
        reg8("USART3_STATUS").raw_store(reg8("USART3_STATUS").raw() | 0x80);
        fprintf(stderr, "sim: pty read %zd bytes\n", r);
    }
}

int Simulator::rx_pop() {
    if (master_fd < 0) return -1;
    uint8_t b;
    ssize_t r = ::read(master_fd, &b, 1);
    if (r <= 0) return -1;
    return (int)b;
}

bool Simulator::rx_push(uint8_t b) {
    (void)b; return false;
}

void Simulator::tx_write(uint8_t b) {
    if (master_fd < 0) return;
    ssize_t r = ::write(master_fd, &b, 1);
    (void)r;
}

Reg8 &Simulator::reg8(const char *name) {
    auto it = _r8.find(name);
    if (it == _r8.end()) {
        _r8.emplace(std::string(name), std::make_unique<Reg8>(name));
        it = _r8.find(name);
    }
    return *it->second;
}

Reg16 &Simulator::reg16(const char *name) {
    auto it = _r16.find(name);
    if (it == _r16.end()) {
        _r16.emplace(std::string(name), std::make_unique<Reg16>(name));
        it = _r16.find(name);
    }
    return *it->second;
}

void Simulator::write_usart_tx(int idx, uint8_t b) {
    char buf[32]; snprintf(buf, sizeof(buf), "USART%d_TXDATAL", idx); reg8(buf) = b;
}

uint8_t Simulator::read_usart_status(int idx) {
    /* Ensure we poll the PTY for new bytes before returning status. */
    poll_pty_nonblocking();
    char buf[32]; snprintf(buf, sizeof(buf), "USART%d_STATUS", idx); return (uint8_t)reg8(buf);
}

uint8_t Simulator::read_usart_rxdatal(int idx) {
    /* Poll to update RX registers from PTY then return the RX data.
     * After returning the byte, clear the RXDATAL and RX flag so the
     * firmware does not repeatedly read the same value. */
    poll_pty_nonblocking();
    char buf[32]; snprintf(buf, sizeof(buf), "USART%d_RXDATAL", idx);
    uint8_t v = (uint8_t)reg8(buf).raw();
    reg8(buf).raw_store(0);
    char sname[32]; snprintf(sname, sizeof(sname), "USART%d_STATUS", idx);
    reg8(sname).raw_store(reg8(sname).raw() & ~(uint8_t)0x80);
    return v;
}

// single simulator instance
Simulator simulator;

// Initialization moved into Simulator::Simulator() to avoid static init order issues.

} // namespace sim

extern "C" void sim_write_usart_tx(int idx, uint8_t b) { sim::simulator.write_usart_tx(idx, b); }
extern "C" uint8_t sim_read_usart_status(int idx) { return sim::simulator.read_usart_status(idx); }
extern "C" uint8_t sim_read_usart_rxdatal(int idx) { return sim::simulator.read_usart_rxdatal(idx); }

