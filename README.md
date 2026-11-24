# pi-ec25-gsm-sip-gateway

A minimal **GSM <-> SIP gateway** in one Docker container: a **Quectel EC25** LTE module on a
**Raspberry Pi** (or any Linux host), **Asterisk 18** and the
[chan_quectel](https://github.com/yasserboutaleb/asterisk-chan-quectel) driver.

It bridges the SIM card of the module to SIP:

- **voice calls** in both directions, to a softphone on the LAN and/or to a SIP server or PBX;
- **SMS** both ways, as SIP `MESSAGE`;
- **USSD**: dial `*100#` from the SIP side, the reply comes back as a message.

This project is a proof of feasibility, kept small on purpose: no web interface, one module,
one call at a time, configuration in a single `.env` file.

> Status: tested on a Raspberry Pi 3 Model B+ with an EC25-E (USB audio, calls both ways, SMS,
> USSD, a SIP server in `ip` mode through a VPN) and on a bench with a simulated module, run by
> the CI on amd64 and arm64 (`tests/bench.sh`).

## How it works

```
 mobile network ── EC25 (USB) ── chan_quectel ── Asterisk ──┬── softphone on the LAN
                   AT port + USB audio                       └── SIP server / PBX
```

- The driver owns the module: call control, SMS and USSD go through the AT port, voice through
  the module's USB audio (an ALSA sound card, 8 kHz).
- The Asterisk configuration is **generated at every start** from `.env` (`gw-config`): there is
  nothing to edit inside the container, and an invalid setting stops the start with a message
  naming it.
- The driver is built from its public fork, **pinned by commit and checked by Git tree**, with
  the call handling fixes developed for this gateway and for
  [rutos-gsm-sip-gateway](https://github.com/yasserboutaleb/rutos-gsm-sip-gateway).

## Quick start

You need the module with **USB audio enabled** (once, see [HARDWARE](docs/HARDWARE.md)), a SIM
without PIN code, Docker with the Compose plugin, and ModemManager stopped.

```
git clone https://github.com/yasserboutaleb/pi-ec25-gsm-sip-gateway.git
cd pi-ec25-gsm-sip-gateway
cp .env.example .env && chmod 600 .env
nano .env     # at least SOFTPHONE_PASSWORD and SOFTPHONE_NETWORK, or the SERVER_* settings
docker compose up -d --build
docker compose exec gateway gw-check
```

`gw-check` shows the modem state (`Free` = ready), the signal and the SIP side. Then, from a
softphone registered with the account `gsm`:

- call **9600**: echo test of the gateway, without any GSM call;
- call a number (`06...` or `+336...`): it goes out through the SIM;
- send a chat message to a number: it is sent as an SMS; received SMS arrive as messages from
  the sender's number;
- dial `*100#` (or your operator's code): the reply arrives as a message from `ussd`.

## Documentation

| Page | Content |
|---|---|
| [INSTALL](docs/INSTALL.md) | host preparation, settings, softphone, everyday use |
| [HARDWARE](docs/HARDWARE.md) | reference set-up with photos, USB audio of the EC25, SIM, power and USB cable |
| [SIP-SERVER](docs/SIP-SERVER.md) | connecting an Asterisk or FreePBX server, `register` and `ip` modes, NAT |
| [SECURITY](docs/SECURITY.md) | exposure, host firewall, access control, secrets, logs |
| [TROUBLESHOOTING](docs/TROUBLESHOOTING.md) | modem states, sound, softphone, calls, SMS |
| [DRIVER](docs/DRIVER.md) | the chan_quectel fork, how it is built and updated |
| [CHANGELOG](CHANGELOG.md) | versions |

## Known limits

- One module, one call at a time; no call waiting, no conference.
- Voice is 8 kHz: the EC25's USB audio has no wideband mode.
- No TLS or SRTP: keep SIP on the LAN, or carry it in a VPN ([SECURITY](docs/SECURITY.md)).
- No delivery report for sent SMS, and no failure message back to the SIP side (the log has it).
- Asterisk runs as root inside the container, the known-working set-up for the serial and
  sound devices.
- With `GSM_VERBOSE=0` (default) the log shows masked numbers; driver warnings about an
  unknown call may still show a number.

## Tests

`sh tests/bench.sh` builds the image and runs it against a simulated EC25
(`tests/fake_ec25.py`), a SIP softphone and a fake SIP server, all on the loopback, without
hardware. It covers:

- calls: start with a call left open, outgoing and incoming calls, refused hang-ups, call index
  reuse, softphone to GSM, calls from the server;
- SMS both ways: GSM 7-bit and UCS2 texts, long texts in several parts (also announced at
  once), a text with quotes, `${...}` and commas that must reach the network unchanged, invalid
  numbers refused;
- USSD from the softphone, reply as a message;
- the SIP server in `register` mode (digest authentication, caller's number in the call request,
  busy relayed to the GSM caller, SMS on the registered line only) and in `ip` mode;
- masked numbers in the log, the device state shown without a module.

`sh tests/lint.sh` runs the static checks, each tool in its own pinned container: ShellCheck,
hadolint, ruff, actionlint, the links of the documentation and gitleaks.

The CI (GitHub Actions) runs both scripts, the bench on amd64 and on arm64. Each needs only
Docker, so the same checks run on a workstation.

## License

GPL-2.0, like chan_quectel: see [LICENSE.md](LICENSE.md).
