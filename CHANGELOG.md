# Changelog

## 0.1.3 (2026-11-24)

- `USSD_REPLY_FILE`: each USSD reply (type, description, text) written to a file for a local
  tool, such as an interactive USSD console, with nothing in the log.
- `SIP_BIND` set to one address: the media (SDP and RTP) use it too, so several gateways can
  share a host, each with its own address.

## 0.1.2 (2026-11-24)

- `DIAL_ALLOW` accepts commas, as in `[0-9]{2,3}`: they were refused, and the gateway did not
  start with such a pattern.

## 0.1.1 (2026-11-24)

- `DIAL_ALLOW`: numbers allowed for calls and SMS (regular expression), against toll fraud
  with a stolen password; refused numbers never reach the module.
- USSD codes masked in the log, like numbers (a recharge or payment code can be in them).
- `docs/SECURITY.md`: the nftables example accepts an `ip` mode server only on its VPN
  interface (an address alone can be forged from the LAN) and rate-limits SIP from the LAN;
  `ip` mode is for a VPN or a trusted LAN, `register` mode on a shared LAN.
- Base image pinned by digest (`ubuntu:22.04`), like the driver.
- Tested on a Raspberry Pi 3 Model B+ with an EC25-E; hardware guide with photos, USB cable
  and power supply advice; troubleshooting for a module whose USB audio is stuck.

## 0.1.0 (2026-11-24)

First version.

- One Docker container: Asterisk 18 (Ubuntu 22.04) and the chan_quectel driver, built from
  its fork at a pinned commit, checked by Git tree.
- Configuration in one `.env` file; the Asterisk configuration is generated at every start
  and refused as a whole when a setting is invalid (`gw-config`).
- Voice calls both ways between the SIM and SIP: a softphone on the LAN, a SIP server or PBX
  in `register` mode (account and password) or `ip` mode (trusted peer), or both.
- SMS both ways as SIP `MESSAGE` (GSM 7-bit and UCS2, long SMS in several parts).
- USSD: `*code#` dialled from the SIP side, the reply as a `MESSAGE`.
- Echo test `9600`; `GSM_ECHO_TEST` to test the GSM side alone.
- Incoming GSM calls rejected as busy when nobody can answer, so the operator's
  forward-on-busy or voicemail applies; GSM calls hung up after 60 s without RTP.
- `gw-check`: status of the modem, the network and SIP, without any identifier; Docker
  health check.
- Numbers masked in the log by default.
- Bench without hardware (`tests/bench.sh`): simulated EC25, softphone and SIP server.
- Jitter buffer on the voice from SIP to the modem (`JITTER_BUFFER`, adaptive by default): with
  USB audio, voice arriving in bursts otherwise leaves calls silent both ways.
- USSD for local tools: context `ussd-console` to send a USSD without a SIP call, and
  `USSD_LOG_TEXT=1` to find the replies in the log (off by default).
- Static checks (`tests/lint.sh`) and CI on amd64 and arm64.
