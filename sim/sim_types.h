#/**
 * @file sim/sim_types.h
 * @brief Register types and small helpers used by the host simulator.
 *
 * Defines `Reg8`/`Reg16` types, callback signatures, and simple thread-
 * safe wrappers used by `sim::Simulator` and the register mapping
 * header `sim_regs.h`.
 *
 * This file follows the project's Doxygen commenting conventions.
 *
 * @author Doug Sandy
 */
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <atomic>
#include <mutex>

namespace sim {

/* When false (default), suppress per-register operator debug prints. */
extern bool sim_verbose;


class Reg8 {
public:
    using ReadCb = std::function<uint8_t()>;
    using WriteCb = std::function<void(uint8_t)>;

    Reg8(const char* name = nullptr) : _val(0), _read_cb(nullptr), _write_cb(nullptr), _name(name) {}
    Reg8(const Reg8&) = delete;
    Reg8& operator=(const Reg8&) = delete;

    /* read - invoked when code reads the register */
    operator uint8_t() const {
        ReadCb cb;
        {
            std::lock_guard<std::mutex> lk(_cb_mutex);
            cb = _read_cb;
        }
        if (cb) {
            uint8_t v = cb();
            return v;
        }
        uint8_t v = _val.load();
        return v;
    }

    /* write - invoked when code writes the register */
    Reg8& operator=(uint8_t v) {
        if (_write_cb) _write_cb(v);
        else _val.store(v);
        return *const_cast<Reg8*>(this);
    }

    Reg8& operator|=(uint8_t v) {
        uint8_t old = _val.load();
        uint8_t nw = old | v;
        if (_write_cb) _write_cb(nw);
        else _val.store(nw);
        return *const_cast<Reg8*>(this);
    }

    Reg8& operator&=(uint8_t v) {
        uint8_t old = _val.load();
        uint8_t nw = old & v;
        if (_write_cb) _write_cb(nw);
        else _val.store(nw);
        return *const_cast<Reg8*>(this);
    }

    void set_read_cb(ReadCb cb) { std::lock_guard<std::mutex> lk(_cb_mutex); _read_cb = cb; }
    void set_write_cb(WriteCb cb) { _write_cb = cb; }
    uint8_t raw() const { return _val.load(); }
    void raw_store(uint8_t v) { _val.store(v); }
    bool has_read_cb() const { std::lock_guard<std::mutex> lk(_cb_mutex); return static_cast<bool>(_read_cb); }

private:
    std::atomic<uint8_t> _val;
    ReadCb _read_cb;
    WriteCb _write_cb;
    const char* _name;
    mutable std::mutex _cb_mutex;
};

class Reg16 {
public:
    using ReadCb = std::function<uint16_t()>;
    using WriteCb = std::function<void(uint16_t)>;

    Reg16(const char* name = nullptr) : _val(0), _read_cb(nullptr), _write_cb(nullptr), _name(name) {}
    Reg16(const Reg16&) = delete;
    Reg16& operator=(const Reg16&) = delete;

    operator uint16_t() const {
        if (_read_cb) return _read_cb();
        return _val.load();
    }

    Reg16& operator=(uint16_t v) {
        if (_write_cb) _write_cb(v);
        else _val.store(v);
        return *const_cast<Reg16*>(this);
    }

    void set_read_cb(ReadCb cb) { _read_cb = cb; }
    void set_write_cb(WriteCb cb) { _write_cb = cb; }
    uint16_t raw() const { return _val.load(); }
    void raw_store(uint16_t v) { _val.store(v); }
    bool has_read_cb() const { return static_cast<bool>(_read_cb); }

private:
    std::atomic<uint16_t> _val;
    ReadCb _read_cb;
    WriteCb _write_cb;
    const char* _name;
};

} // namespace sim
