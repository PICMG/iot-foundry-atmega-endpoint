// Clean, single-definition simulator implementation.
#include "simulator.h"
#include "generated_serial_config.h"
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

    /* initialize default status bits */
    reg8("USART0_STATUS").raw_store(0x60);
    reg8("USART1_STATUS").raw_store(0x60);
    reg8("USART2_STATUS").raw_store(0x60);
    reg8("USART3_STATUS").raw_store(0x60);
    reg8("UCSR0A").raw_store(0x20);
    reg8("UCSR1A").raw_store(0x20);
    reg8("UCSR2A").raw_store(0x20);
    reg8("UCSR3A").raw_store(0x20);
    reg8("UCSR0B").raw_store(0x00);
    reg8("UCSR1B").raw_store(0x00);
    reg8("UCSR2B").raw_store(0x00);
    reg8("UCSR3B").raw_store(0x00);
    reg8("UCSR0C").raw_store(0x06);
    reg8("UCSR0C").raw_store(0x06);
    reg8("UCSR1C").raw_store(0x06);
    reg8("UCSR2C").raw_store(0x06);
    reg8("UCSR3C").raw_store(0x06);
    
    /* install write callbacks */
    reg8("PORTA_DIR").set_write_cb([this](uint8_t v){ this->reg8("PORTA_DIR").raw_store(v); });
    reg8("USART0_TXDATAL").set_write_cb([this](uint8_t v){ this->txdatal_write_cb(0, v); });
    reg8("USART1_TXDATAL").set_write_cb([this](uint8_t v){ this->txdatal_write_cb(1, v); });
    reg8("USART2_TXDATAL").set_write_cb([this](uint8_t v){ this->txdatal_write_cb(2, v); });
    reg8("USART3_TXDATAL").set_write_cb([this](uint8_t v){ this->txdatal_write_cb(3, v); });
    reg8("UDR0").set_write_cb([this](uint8_t v){ this->udr_write_cb(0, v); });
    reg8("UDR1").set_write_cb([this](uint8_t v){ this->udr_write_cb(1, v); });
    reg8("UDR2").set_write_cb([this](uint8_t v){ this->udr_write_cb(2, v); });
    reg8("UDR3").set_write_cb([this](uint8_t v){ this->udr_write_cb(3, v); });
    
    /* install read callbacks */
    reg8("USART0_RXDATAL").set_read_cb([this](){ uint8_t b = rxdatal_read_cb(0); return b;});
    reg8("USART1_RXDATAL").set_read_cb([this](){ uint8_t b = rxdatal_read_cb(1); return b;});
    reg8("USART2_RXDATAL").set_read_cb([this](){ uint8_t b = rxdatal_read_cb(2); return b;});
    reg8("USART3_RXDATAL").set_read_cb([this](){ uint8_t b = rxdatal_read_cb(3); return b;});
    reg8("UDR0").set_read_cb([this](){ uint8_t b = this->udr_read_cb(0); return b; });
    reg8("UDR1").set_read_cb([this](){ uint8_t b = this->udr_read_cb(1); return b; });
    reg8("UDR2").set_read_cb([this](){ uint8_t b = this->udr_read_cb(2); return b; });
    reg8("UDR3").set_read_cb([this](){ uint8_t b = this->udr_read_cb(3); return b; });

    reg8("USART0_STATUS").set_read_cb([this](){ uint8_t s = status_read_cb(0); return s;});
    reg8("USART1_STATUS").set_read_cb([this](){ uint8_t s = status_read_cb(1); return s;});
    reg8("USART2_STATUS").set_read_cb([this](){ uint8_t s = status_read_cb(2); return s;});
    reg8("USART3_STATUS").set_read_cb([this](){ uint8_t s = status_read_cb(3); return s;});
    reg8("UCSR0A").set_read_cb([this](){ uint8_t s = ucsra_read_cb(0); return s;});
    reg8("UCSR1A").set_read_cb([this](){ uint8_t s = ucsra_read_cb(1); return s;});
    reg8("UCSR2A").set_read_cb([this](){ uint8_t s = ucsra_read_cb(2); return s;});
    reg8("UCSR3A").set_read_cb([this](){ uint8_t s = ucsra_read_cb(3); return s;});
}

Simulator::~Simulator() {
    if (master_fd >= 0) close(master_fd);
    if (slave_fd >= 0) close(slave_fd);
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

void Simulator::poll_pty_nonblocking(int idx) {
    validate_configuration(idx);

    // create the register name
    char name[32]; 
    #ifdef SERIAL_UART_TYPE_USART_0SERIES
        // for USART 0-series, use RXDATAL/STATUS registers
        snprintf(name, sizeof(name), "USART%d_STATUS", idx);
    #else
        // for classic USART, use UCSRnA register
        snprintf(name, sizeof(name), "UCSR%dA", idx);
    #endif

    // see if there are any bytes available to read
    if (master_fd < 0) return;
    int n = 0;
    ioctl(master_fd, FIONREAD, &n);

    // if so, set the RXCIF bit in the status register
    if (n > 0) {
        /* Set RX complete bit (0x80) on all status registers. */
        /* this bit always signifies a byte is ready to be read */
        reg8(name).raw_store(reg8(name).raw() | 0x80);
    }
}

void Simulator::txdatal_write_cb(int idx, uint8_t b) {
    // create the register name
    char txname[32]; 
    snprintf(txname, sizeof(txname), "USART%d_TXDATAL", idx);
    char rxname[32]; 
    snprintf(rxname, sizeof(rxname), "USART%d_RXDATAL", idx);

    #ifdef SERIAL_UART_TYPE_USART_0SERIES
        // write to the TX register but do not send the byte
        reg8(txname).raw_store(b);
    #else
        // write to the TX register but do not send the byte
        // note, for clasic USART, TXDATAL and RXDATAL are the same register
        reg8(rxname).raw_store(b);
    #endif

    // clear the data register empty flag in the status register
    char sname[32];
    snprintf(sname, sizeof(sname), "USART%d_STATUS", idx);
    #ifdef USART_DREIF_bm
        reg8(sname).raw_store(reg8(sname).raw() & ~(uint8_t)USART_DREIF_bm);
    #elif defined(UDRE)
        reg8(sname).raw_store(reg8(sname).raw() & ~(uint8_t)(1 << UDRE));
    #elif defined(UDRE0)
        reg8(sname).raw_store(reg8(sname).raw() & ~(uint8_t)(1 << UDRE0));
    #endif    

    if (validate_configuration(idx)) {
        // send the byte out the pty
        // TODO: it would be good to validate that the byte has been sent
        int unused = ::write(master_fd, &b, 1);
    }   
}

void Simulator::udr_write_cb(int idx, uint8_t b) {
    // create the register name
    char txname[32]; 
    snprintf(txname, sizeof(txname), "UDR%d", idx);
    char rxname[32]; 
    snprintf(rxname, sizeof(rxname), "UDR%d", idx);

    // write to the TX register but do not send the byte
    // note, for clasic USART, TXDATAL and RXDATAL are the same register
    reg8(rxname).raw_store(b);

    // clear the data register empty flag in the status register
    char sname[32];
    snprintf(sname, sizeof(sname), "UCSR%dA", idx);
    #ifdef USART_DREIF_bm
        reg8(sname).raw_store(reg8(sname).raw() & ~(uint8_t)USART_DREIF_bm);
    #elif defined(UDRE)
        reg8(sname).raw_store(reg8(sname).raw() & ~(uint8_t)(1 << UDRE));
    #elif defined(UDRE0)
        reg8(sname).raw_store(reg8(sname).raw() & ~(uint8_t)(1 << UDRE0));
    #endif    

    if (validate_configuration(idx)) {
        // send the byte out the pty
        // TODO: it would be good to validate that the byte has been sent
        int unused = ::write(master_fd, &b, 1);
    }   
}

uint8_t Simulator::status_read_cb(int idx) {
    // create the register name
    char name[32]; 
    snprintf(name, sizeof(name), "USART%d_STATUS", idx);

    /* Ensure we poll the PTY for new bytes before returning status. */
    poll_pty_nonblocking(idx);

    /* take care of transmit complete and data register empty values */
    if (validate_configuration(idx)) {
        uint8_t status = reg8(name).raw();

        // get the current status value and check if DREIF is clear
        #ifdef USART_DREIF_bm
            status = status & (uint8_t)USART_DREIF_bm);
        #elif defined(UDRE)
            status = status & (uint8_t)(1 << UDRE));
        #elif defined(UDRE0)
            status = status & (uint8_t)(1 << UDRE0));
        #endif

        // if DREIF is clear, randomly set it to simulate data transmission completion
        if (!status) {
            // get a random number between 0 and 255
            // and use it to randomly to simulate transmission complete
            int r = rand() % 100;
            if (r > 95) {
                // set TXCIF bit
                #ifdef USART_TXCIF_bm
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)USART_TXCIF_bm);
                #elif defined(TXC)
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)TXC);
                #elif defined(TXC0)
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)TXC0);
                #endif

                // clear DREIF bit
                #ifdef USART_DREIF_bm
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)USART_DREIF_bm);
                #elif defined(UDRE)
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)(1 << UDRE));
                #elif defined(UDRE0)
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)(1 << UDRE0));
                #endif
            }
        }
    }
    uint8_t status = reg8(name).raw();
    return status;
}

uint8_t Simulator::ucsra_read_cb(int idx) {
    // create the register name
    char name[32]; 
    snprintf(name, sizeof(name), "UCSR%dA", idx);

    /* Ensure we poll the PTY for new bytes before returning status. */
    poll_pty_nonblocking(idx);

    /* take care of transmit complete and data register empty values */
    if (validate_configuration(idx)) {
        uint8_t status = reg8(name).raw();

        // get the current status value and check if DREIF is clear
        #ifdef USART_DREIF_bm
            status = status & (uint8_t)USART_DREIF_bm);
        #elif defined(UDRE)
            status = status & (uint8_t)(1 << UDRE));
        #elif defined(UDRE0)
            status = status & (uint8_t)(1 << UDRE0));
        #endif

        // if DREIF is clear, randomly set it to simulate data transmission completion
        if (!status) {
            // get a random number between 0 and 255
            // and use it to randomly to simulate transmission complete
            int r = rand() % 100;
            if (r > 95) {
                // set TXCIF bit
                #ifdef USART_TXCIF_bm
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)USART_TXCIF_bm);
                #elif defined(TXC)
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)TXC);
                #elif defined(TXC0)
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)TXC0);
                #endif

                // clear DREIF bit
                #ifdef USART_DREIF_bm
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)USART_DREIF_bm);
                #elif defined(UDRE)
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)(1 << UDRE));
                #elif defined(UDRE0)
                    status = reg8(name).raw_store(reg8(name).raw() | (uint8_t)(1 << UDRE0));
                #endif
            }
        }
    }
    uint8_t status = reg8(name).raw();
    return status;
}

#define STR_HELPER(x) #x
#define STR(x) STR_HELPER(x)
bool Simulator::validate_configuration(int idx) {
    auto fail = [&](const char *msg)->bool { fprintf(stderr, "sim: validate[%d] fail: %s\n", idx, msg); return false; };
    
    #ifdef SERIAL_UART_TYPE_USART_0SERIES
        // validate the baud rate setting for this usart
        char bname[32]; 
        snprintf(bname, sizeof(bname), "USART%d_BAUD", idx);
        uint16_t baud = reg16(bname).raw();
        uint16_t expected_baud = (uint16_t)((8UL * (uint32_t)GENERATED_F_CPU) / (2UL * (uint32_t)(SERIAL_BAUD)));
        if (baud != expected_baud) {    
            char buf[64]; snprintf(buf, sizeof(buf), "baud mismatch got %u expected %u", (unsigned)baud, (unsigned)expected_baud);
            return fail(buf);
        }

        // calculate the data direction port name for this usart from SERIAL_RX_PORT
        char ddrname[32]; 
        char port_letter[] = STR(SERIAL_RX_PORT);
        snprintf(ddrname, sizeof(ddrname), "PORT%s_DIR", port_letter);
        uint8_t ddr = reg8(ddrname).raw();

        // validate that the RX pin is set as input and TX pin is set as output
        uint8_t rx_pin_mask = (1 << SERIAL_RX_PIN);
        uint8_t tx_pin_mask = (1 << SERIAL_TX_PIN);
        if ((ddr & (uint8_t)(rx_pin_mask)) != 0) {
            return fail("RX pin not input (DDR bit set)");
        }
        if ((ddr & (uint8_t)(tx_pin_mask)) == 0) {
            return fail("TX pin not output (DDR bit clear)");
        }

        // validate the pin mux settings for this usart
        char pmname[] = "PORTMUX_USARTROUTEA";
        uint8_t portmux = reg8(pmname).raw();
        if ((portmux & (~SERIAL_MUX_ANDMASK)) != SERIAL_MUX_ORMASK) {
            return fail("portmux mismatch");
        }

        // validate the mode settings for USARTn_CTRLB for this usart
        char ctrlbname[32]; 
        snprintf(ctrlbname, sizeof(ctrlbname), "USART%d_CTRLB", idx);
        uint8_t ctrlb = reg8(ctrlbname).raw();
        // validate that RX and TX are enabled
        if ((ctrlb & 0xc0) != 0xc0) {
            return fail("CTRLB TX/RX not enabled");
        }
        // validate the mode settings for USARTn_CTRLB for this usart
        if ((ctrlb & 0x07) != 0x00) { // standard mode, no multi-processor
            return fail("CTRLB mode not standard");
        }

        // validate the mode settings for USARTn_CTRLC for this usart
        char ctrlcname[32]; 
        snprintf(ctrlcname, sizeof(ctrlcname), "USART%d_CTRLC", idx);
        uint8_t ctrlc = reg8(ctrlcname).raw();
        // for simplicity, assume that valid setting is asynchronous mode, 8-n-1
        if ((ctrlc  != 0x03)) { // 8N1 async
            return fail("CTRLC not 8N1");
        }

        // validate that the clock prescale is set to no division
        char clkname[] = "CLKCTRL_MCLKCTRLB";
        uint8_t clk = reg8(clkname).raw();
        if (clk != 0) {
            return fail("CLK prescaler non-zero");
        }
    #else
        // validate the baud rate setting for this usart
        char bname[32]; 
        snprintf(bname, sizeof(bname), "UBRR%d", idx);
        uint16_t baud = reg16(bname).raw();
        uint16_t expected_baud = (uint16_t)(((uint32_t)GENERATED_F_CPU) / (16 * (uint32_t)(SERIAL_BAUD)))-1;
        if (baud != expected_baud) {    
            char buf[64]; snprintf(buf, sizeof(buf), "baud mismatch got %u expected %u", (unsigned)baud, (unsigned)expected_baud);
            return fail(buf);
        }

        // calculate the data direction port name for this usart from SERIAL_RX_PORT
        char ddrname[32]; 
        char port_letter[] = STR(SERIAL_RX_PORT);
        snprintf(ddrname, sizeof(ddrname), "PORT%s_DIR", port_letter);
        uint8_t ddr = reg8(ddrname).raw();

        // validate that the RX pin is set as input and TX pin is set as output
        uint8_t rx_pin_mask = (1 << SERIAL_RX_PIN);
        uint8_t tx_pin_mask = (1 << SERIAL_TX_PIN);
        if ((ddr & (uint8_t)(rx_pin_mask)) != 0) {
            return fail("RX pin not input (DDR bit set)");
        }
        if ((ddr & (uint8_t)(tx_pin_mask)) == 0) {
            return fail("TX pin not output (DDR bit clear)");
        }

        // validate the mode settings for UCSRnA for this usart
        char ctrlaname[32]; 
        snprintf(ctrlaname, sizeof(ctrlaname), "UCSR%dA", idx);
        uint8_t ctrla = reg8(ctrlaname).raw();
        // validate that normal speed and no multi-processor RX and TX are enabled
        if ((ctrla & 0x3) != 0) {
            return fail("CTRLA invalid (speed/multi)");
        }

        // validate the mode settings for UCSRnB for this usart
        char ctrlbname[32]; 
        snprintf(ctrlbname, sizeof(ctrlbname), "UCSR%dB", idx);
        uint8_t ctrlb = reg8(ctrlbname).raw();
        // validate that RX and TX are enabled
        if ((ctrlb & 0x1c) != 0x18) {
            return fail("CTRLB RX/TX not enabled");
        }

        // validate the mode settings for UCSRnC for this usart
        char ctrlcname[32]; 
        snprintf(ctrlcname, sizeof(ctrlcname), "UCSR%dC", idx);
        uint8_t ctrlc = reg8(ctrlcname).raw();
        // for simplicity, assume that valid setting is asynchronous mode, 8-n-1
        if (ctrlc  != 0x06) { // 8N1 async
            return fail("CTRLC not 8N1");
        }

    #endif
    return true;
}

uint8_t Simulator::rxdatal_read_cb(int idx) {
    // create the register name
    char txname[32]; 
    snprintf(txname, sizeof(txname), "USART%d_TXDATAL", idx);
    char rxname[32]; 
    snprintf(rxname, sizeof(rxname), "USART%d_RXDATAL", idx);

    // read from the rx register
    uint8_t v = (uint8_t)reg8(rxname).raw();

    /* validate the configuration */
    if (!validate_configuration(idx)) {
        return v;
    }

    /* if there is a character in the input buffer, get it */
    int n = 0;
    ioctl(master_fd, FIONREAD, &n);
    if (n > 0) {
        size_t n = ::read(master_fd, &v, 1);
        #ifdef SERIAL_UART_TYPE_USART_0SERIES
            // write to the rx register
            reg8(rxname).raw_store(v);
        #endif

        // clear status register bit
        char sname[32]; snprintf(sname, sizeof(sname), "USART%d_STATUS", idx);
        reg8(sname).raw_store(reg8(sname).raw() & ~(uint8_t)0x80);
    }

    /* update the status register - there could be more characters */
    poll_pty_nonblocking(idx);

    /* return the received byte */
    return v;
}

uint8_t Simulator::udr_read_cb(int idx) {
    // create the register name
    char txname[32]; 
    snprintf(txname, sizeof(txname), "UDR%d", idx);
    char rxname[32]; 
    snprintf(rxname, sizeof(rxname), "UDR%d", idx);

    // note, for clasic USART, TXDATAL and RXDATAL are the same register
    uint8_t v = (uint8_t)reg8(txname).raw();

    /* validate the configuration */
    if (!validate_configuration(idx)) {
        return v;
    }

    /* if there is a character in the input buffer, get it */
    int n = 0;
    ioctl(master_fd, FIONREAD, &n);
    if (n > 0) {
        size_t n = ::read(master_fd, &v, 1);

        // clear status register bit
        char sname[32]; snprintf(sname, sizeof(sname), "UCSR%dA", idx);
        reg8(sname).raw_store(reg8(sname).raw() & ~(uint8_t)0x80);
    }

    /* update the status register - there could be more characters */
    poll_pty_nonblocking(idx);

    /* return the received byte */
    return v;
}

// single simulator instance
Simulator simulator;

} // namespace sim

