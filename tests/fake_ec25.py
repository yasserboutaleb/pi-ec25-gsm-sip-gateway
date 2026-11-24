#!/usr/bin/env python3
"""Simulated Quectel EC25 AT port owned by chan_quectel: calls from fake_eg06.py, plus SMS and USSD.

fake_eg06.py (shared with the RUT360 bench, kept identical) simulates the calls. This module adds
what the driver does when it owns the module, in PDU mode with the UCS2 character set
(AT+CMGF=0, AT+CSCS="UCS2"), like a real EC25:

  incoming SMS   +CMTI: "ME",<idx>  ->  AT+CMGR=<idx> answers the SMS-DELIVER PDU  ->  AT+CMGD=<idx>
  outgoing SMS   AT+CMGS=<len>  ->  "> " prompt  ->  SMS-SUBMIT PDU ended by Ctrl-Z  ->  +CMGS: <ref>
  USSD           AT+CUSD=1,"<UCS2 hex>",15  ->  OK, then +CUSD: <type>,"<UCS2 hex>",72

Extra control commands (same FIFO as fake_eg06.py):
    sms <from> <text>        incoming SMS, GSM 7-bit alphabet when possible, otherwise UCS2
    sms_long <from> <text>   incoming SMS in 2 parts (concatenated, 8-bit reference), 2 s apart
    sms_burst <from> <text>  the same, both parts announced at once
    ussd_reply <text>        reply to the next USSD request (default: a balance message)
    ussd_type <n>            type of the next USSD replies: 0 final (default), 1 menu (further action)

Log lines (argument 2, UTF-8), checked by the bench:
    SMS-IN idx=<n> from=<number>              PDU stored, +CMTI sent
    SMS-OUT to=<number> dcs=<n> vp=<n> part=<i>/<n> ref=<r> text=<text>
    USSD-REQ <code>
"""
import os
import select
import sys
import time

import fake_eg06 as base

LOG = open(base.LOG, "a", buffering=1, encoding="utf-8")

GSM7 = ("@£$¥èéùìòÇ\nØø\rÅåΔ_ΦΓΛΩΠΨΣΘΞ\x1bÆæßÉ !\"#¤%&'()*+,-./0123456789:;<=>?"
        "¡ABCDEFGHIJKLMNOPQRSTUVWXYZÄÖÑÜ§¿abcdefghijklmnopqrstuvwxyzäöñüà")
GSM7_EXT = {0x0A: "\f", 0x14: "^", 0x28: "{", 0x29: "}", 0x2F: "\\", 0x3C: "[", 0x3D: "~", 0x3E: "]",
            0x40: "|", 0x65: "€"}
assert len(GSM7) == 128

store = {}                      # SMS storage: idx -> (tpdu length, PDU hex)
state = {"cmgs": None, "mr": 0, "ussd": "Balance: 12.50 EUR, valid until 31/12, café included", "ussd_type": 0}


def w(line):
    LOG.write("%.3f %s\n" % (time.time(), line))


# ---------------------------------------------------------------- GSM 7-bit and PDU helpers
def gsm7_septets(text):
    """septets of the text, or None if a character is outside the GSM 7-bit alphabet"""
    out = []
    rev = {v: k for k, v in GSM7_EXT.items()}
    for ch in text:
        if ch in GSM7 and ch != "\x1b":
            out.append(GSM7.index(ch))
        elif ch in rev:
            out += [0x1B, rev[ch]]
        else:
            return None
    return out


def septets_text(septets):
    out, esc = [], False
    for s in septets:
        if esc:
            out.append(GSM7_EXT.get(s, " "))
            esc = False
        elif s == 0x1B:
            esc = True
        else:
            out.append(GSM7[s])
    return "".join(out)


def pack7(prefix, septets):
    """user data: prefix octets (UDH), fill bits up to a septet boundary, then the septets"""
    start = len(prefix) * 8
    start += (7 - start % 7) % 7
    total = start + 7 * len(septets)
    data = bytearray(prefix) + bytearray((total + 7) // 8 - len(prefix))
    for i, s in enumerate(septets):
        for b in range(7):
            if s >> b & 1:
                pos = start + 7 * i + b
                data[pos // 8] |= 1 << (pos % 8)
    return bytes(data), total // 7


def unpack7(data, nsept, skip_octets):
    start = skip_octets * 8
    start += (7 - start % 7) % 7
    count = nsept - start // 7
    return [sum(((data[(start + 7 * i + b) // 8] >> ((start + 7 * i + b) % 8)) & 1) << b for b in range(7))
            for i in range(count)]


def bcd_number(num):
    """address field: length in digits, type, swapped BCD"""
    intl = num.startswith("+")
    digits = num.lstrip("+")
    sw = digits + ("F" if len(digits) % 2 else "")
    body = "".join(sw[i + 1] + sw[i] for i in range(0, len(sw), 2))
    return "%02X%02X%s" % (len(digits), 0x91 if intl else 0x81, body)


def parse_number(h, pos):
    n, typ = int(h[pos:pos + 2], 16), int(h[pos + 2:pos + 4], 16)
    octets = (n + 1) // 2
    raw = h[pos + 4:pos + 4 + octets * 2]
    digits = "".join(raw[i + 1] + raw[i] for i in range(0, len(raw), 2)).rstrip("F")[:n]
    return ("+" if typ == 0x91 else "") + digits, pos + 4 + octets * 2


def scts():
    t = time.gmtime(time.time() + 3600)
    v = "%02d%02d%02d%02d%02d%02d" % (t.tm_year % 100, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
    return "".join(v[i + 1] + v[i] for i in range(0, 12, 2)) + "40"  # time zone +1 h (4 quarters)


def deliver_pdu(sender, text, udh=b""):
    """SMS-DELIVER (with an SMSC address), as answered by AT+CMGR: (TPDU length, hex)"""
    sept = gsm7_septets(text)
    if sept is not None:
        dcs, (ud, udl) = 0x00, pack7(udh, sept)
    else:
        raw = text.encode("utf-16-be")
        dcs, ud, udl = 0x08, udh + raw, len(udh) + len(raw)
    first = 0x04 | (0x40 if udh else 0)
    tpdu = "%02X%s00%02X%s%02X%s" % (first, bcd_number(sender), dcs, scts(), udl, ud.hex().upper())
    return len(tpdu) // 2, "07913396050000F0" + tpdu  # SMSC +33695000000 (fictional)


def store_sms(sender, text, udh=b""):
    idx = 1
    while idx in store:
        idx += 1
    store[idx] = deliver_pdu(sender, text, udh)
    w("SMS-IN idx=%d from=%s" % (idx, sender))
    base.out('\r\n+CMTI: "ME",%d\r\n' % idx)


def decode_submit(h):
    """SMS-SUBMIT sent by the driver (with its SMSC length octet)"""
    pos = 2 + int(h[0:2], 16) * 2
    first = int(h[pos:pos + 2], 16)
    pos += 4  # first octet, message reference
    to, pos = parse_number(h, pos)
    pos += 2  # PID
    dcs = int(h[pos:pos + 2], 16)
    pos += 2
    vpf = (first >> 3) & 3
    vp = ""
    if vpf == 2:
        vp, pos = str(int(h[pos:pos + 2], 16)), pos + 2
    elif vpf in (1, 3):
        pos += 14
    udl = int(h[pos:pos + 2], 16)
    ud = bytes.fromhex(h[pos + 2:])
    part, udh_len = "1/1", 0
    ref = "-"
    if first & 0x40:
        udh_len = ud[0] + 1
        hdr = ud[1:udh_len]
        if hdr[0] == 0x00:      # concatenation, 8-bit reference
            ref, part = str(hdr[2]), "%d/%d" % (hdr[4], hdr[3])
        elif hdr[0] == 0x08:    # concatenation, 16-bit reference
            ref, part = str(hdr[2] << 8 | hdr[3]), "%d/%d" % (hdr[5], hdr[4])
    if dcs & 0x0C == 0x08:
        text = ud[udh_len:udl].decode("utf-16-be", errors="replace")
    else:
        text = septets_text(unpack7(ud, udl, udh_len))
    return to, dcs, vp, part, ref, text


# ---------------------------------------------------------------- AT commands and control
def handle(cmd):
    u = cmd.upper()
    if u.startswith("AT+CMGS="):
        base.log.write("%.3f %s\n" % (time.time(), cmd))
        state["cmgs"] = int(u[8:])
        base.out("\r\n> ")
        return
    if u.startswith("AT+CMGR="):
        base.log.write("%.3f %s\n" % (time.time(), cmd))
        idx = int(u[8:])
        if idx not in store:
            return base.reply(final="+CMS ERROR: 321")
        length, pdu = store[idx]
        # like the real module: the PDU on the line right after the header, no empty line between
        base.out("\r\n+CMGR: 0,,%d\r\n%s\r\n\r\nOK\r\n" % (length, pdu))
        return None
    if u.startswith("AT+CMGD="):
        base.log.write("%.3f %s\n" % (time.time(), cmd))
        store.pop(int(u[8:].split(",")[0]), None)
        return base.reply()
    if u.startswith("AT+CUSD=1,"):
        base.log.write("%.3f %s\n" % (time.time(), cmd))
        code = cmd.split('"')[1]
        try:
            code = bytes.fromhex(code).decode("utf-16-be")
        except ValueError:
            pass
        w("USSD-REQ %s" % code)
        base.reply()
        time.sleep(0.5)
        base.out('\r\n+CUSD: %d,"%s",72\r\n' % (state["ussd_type"], state["ussd"].encode("utf-16-be").hex().upper()))
        return
    base.handle(cmd)


def pdu_received(data):
    base.log.write("%.3f PDU %s\n" % (time.time(), data))
    try:
        to, dcs, vp, part, ref, text = decode_submit(data)
        w("SMS-OUT to=%s dcs=%d vp=%s part=%s ref=%s text=%s" % (to, dcs, vp, part, ref, text))
    except (ValueError, IndexError) as e:
        w("SMS-OUT undecodable PDU (%s)" % e)
    state["cmgs"] = None
    state["mr"] = (state["mr"] + 1) % 256
    base.reply(["+CMGS: %d" % state["mr"]])


def control(line):
    parts = line.split(None, 2)
    if parts and parts[0] == "sms" and len(parts) == 3:
        base.log.write("%.3f CTRL sms\n" % time.time())
        store_sms(parts[1], parts[2])
    elif parts and parts[0] in ("sms_long", "sms_burst") and len(parts) == 3:
        base.log.write("%.3f CTRL %s\n" % (time.time(), parts[0]))
        text = parts[2]
        half = (len(text) + 1) // 2
        state["ref"] = (state.get("ref", 0x41) + 1) % 256
        udh = [bytes([5, 0x00, 3, state["ref"], 2, i]) for i in (1, 2)]
        store_sms(parts[1], text[:half], udh[0])
        # sms_long: second part 2 s later, as usual on the network; sms_burst: right away
        delay = 2.0 if parts[0] == "sms_long" else 0.0
        scheduled.append((time.time() + delay, lambda: store_sms(parts[1], text[half:], udh[1])))
    elif parts and parts[0] == "ussd_type" and len(parts) > 1:
        state["ussd_type"] = int(parts[1])
    elif parts and parts[0] == "ussd_reply":
        state["ussd"] = line.split(None, 1)[1] if len(parts) > 1 else ""
    else:
        base.control(line)


scheduled = []  # (time, action): parts of a long SMS sent later


def run_scheduled():
    now = time.time()
    for item in [s for s in scheduled if s[0] <= now]:
        scheduled.remove(item)
        item[1]()


def main():
    fd_ctrl = os.open(base.CTRL, os.O_RDWR | os.O_NONBLOCK)
    buf, cbuf = b"", b""
    stdin = sys.stdin.buffer.raw
    while True:
        run_scheduled()
        r, _, _ = select.select([stdin, fd_ctrl], [], [], 0.2)
        if stdin in r:
            data = os.read(stdin.fileno(), 1024)
            if not data:
                return
            buf += data
            while True:
                if state["cmgs"] is not None:
                    if b"\x1a" not in buf:
                        break
                    pdu, buf = buf.split(b"\x1a", 1)
                    pdu_received(pdu.decode(errors="replace").strip())
                    continue
                if b"\r" not in buf:
                    break
                line, buf = buf.split(b"\r", 1)
                line = line.strip(b"\n").decode(errors="replace").strip()
                if line:
                    handle(line)
        if fd_ctrl in r:
            cbuf += os.read(fd_ctrl, 1024)
            while b"\n" in cbuf:
                line, cbuf = cbuf.split(b"\n", 1)
                control(line.decode(errors="replace").strip())


if __name__ == "__main__":
    main()
