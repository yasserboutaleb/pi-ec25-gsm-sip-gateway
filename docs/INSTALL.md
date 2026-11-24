# Installation

## 1. Prepare the host

- A Raspberry Pi with **Raspberry Pi OS 64-bit** (the reference set-up runs Debian 13), or
  another Linux host. See [HARDWARE.md](HARDWARE.md) for the module, the SIM and the power.
- **Docker Engine with the Compose plugin**: follow the Docker documentation for your system
  (<https://docs.docker.com/engine/install/>). Check with `docker compose version`.
- Stop **ModemManager**, which would open the module's AT ports:

  ```
  sudo systemctl disable --now ModemManager
  ```

- Plug in the module and check that it is seen, with **USB audio enabled** (once per module,
  see [HARDWARE.md](HARDWARE.md#enable-usb-audio-once)):

  ```
  ls -l /dev/serial/by-id/           # usb-Android_Android-if02-port0 is the AT port
  cat /proc/asound/cards             # a card named "Android"
  ```

## 2. Get the gateway and configure it

```
git clone https://github.com/yasserboutaleb/pi-ec25-gsm-sip-gateway.git
cd pi-ec25-gsm-sip-gateway
cp .env.example .env
chmod 600 .env                     # it holds passwords
nano .env
```

Set at least one SIP side:

- a **softphone on the LAN**: `SOFTPHONE_PASSWORD` (8 characters or more) and
  `SOFTPHONE_NETWORK` (your LAN, e.g. `192.168.1.0/24`);
- and/or a **SIP server or PBX**: `SERVER_ENABLED=1` and the `SERVER_*` settings, see
  [SIP-SERVER.md](SIP-SERVER.md).

Check the settings without starting anything:

```
docker compose run --rm gateway gw-config check
```

An invalid setting is reported with its name, and nothing is generated. The gateway never
starts with a configuration it refused.

## 3. Start

```
docker compose up -d --build
```

The first build compiles the chan_quectel driver and takes a while on a Raspberry Pi. The
container restarts by itself after a crash or a reboot of the host (`restart: unless-stopped`).

```
docker compose exec gateway gw-check
```

`gw-check` shows the modem state, the signal and the SIP side. It prints no identifier (IMEI,
IMSI, ICCID or phone number):

| Modem state | Meaning |
|---|---|
| `Free` | ready |
| `Not connected` | the AT port is missing or busy: cable, power, ModemManager |
| `Not initialized` | the module answers but is still being set up (a few seconds after start) |
| `GSM not registered` | no network: antenna, SIM, PIN code, coverage |
| `NoVoice` | registered, but voice is not enabled yet; retried automatically while `MODEM_CLCC_POLL` is not 0 |
| `Ring`, `Dialing`, `Outgoing`, `Incoming`, `Held` | a call is in progress |
| `SMS` | an SMS is being read or sent |
| `Stopped` | the device was stopped from the Asterisk console |

`docker ps` also shows the Docker health check (`healthy` once the modem is connected).

## 4. Connect a softphone

In the softphone (Linphone, Zoiper, MicroSIP, a desk phone...):

| Field | Value |
|---|---|
| User name, authentication name | `SOFTPHONE_USERNAME` (`gsm` by default) |
| Password | `SOFTPHONE_PASSWORD` |
| Domain / server | the address of the host, e.g. `192.168.1.20` |
| Transport, port | UDP, `SIP_PORT` (5060) |
| Codecs | G.711 (PCMU, PCMA) |

Then:

- call **9600**: echo test of the gateway itself, without any GSM call; you should hear
  yourself;
- call a number in national (`06...`) or international (`+33...`) format: it goes out
  through the SIM;
- call the SIM's number from a mobile: the softphone rings (unless `INCOMING_CALLS_TO` sends
  calls to a server only);
- send a chat message to a number: it is sent as an SMS. Received SMS appear as messages from
  the sender's number;
- dial a USSD code such as `*100#` (it depends on the operator): the reply arrives as a
  message from `ussd`.

The softphone is accepted only from `SOFTPHONE_NETWORK` (and the loopback), with its
password, and one device at a time.

## Settings

All settings are in `.env`, read at every start. After a change: `docker compose up -d`.

| Setting | Default | Meaning |
|---|---|---|
| `MODEM_DATA_PORT` | `/dev/serial/by-id/usb-Android_Android-if02-port0` | AT port of the module |
| `MODEM_AUDIO` | `uac` | `uac`: USB audio; `serial`: PCM over a serial port |
| `MODEM_ALSA_DEVICE` | `hw:CARD=Android` | ALSA device of the module (`uac`) |
| `MODEM_AUDIO_PORT` | | audio port (`serial`), e.g. `.../usb-Android_Android-if01-port0` |
| `MODEM_CLCC_POLL` | `1000` | call state polling (`AT+CLCC`) in ms, 250 to 10000. `0`: notifications only, without the recovery of refused hang-ups, unknown calls and voice ([DRIVER](DRIVER.md)) |
| `SOFTPHONE_USERNAME` | `gsm` | softphone account (letters, digits, `_ . + -`) |
| `SOFTPHONE_PASSWORD` | | empty: no softphone; else 8 characters or more |
| `SOFTPHONE_NETWORK` | | network the softphone connects from, e.g. `192.168.1.0/24` |
| `SERVER_ENABLED` | `0` | `1`: connect to a SIP server or PBX |
| `SERVER_MODE` | `register` | `register` (account and password) or `ip` (trusted peer) |
| `SERVER_HOST`, `SERVER_PORT` | `5060` | address and port of the server |
| `SERVER_USERNAME`, `SERVER_PASSWORD` | | gateway account on the server (`register`) |
| `SERVER_EXTENSION` | | extension of the server that receives GSM calls, SMS and USSD replies |
| `SERVER_CODEC` | `ulaw` | `ulaw`, `alaw`, or both in order of preference |
| `SERVER_LOCAL_ADDRESS` | `gateway` | host part of the `From` of the messages (SMS, USSD replies) sent to the server or the softphone; in `ip` mode, set it to the address of the gateway as the server sees it |
| `INCOMING_CALLS_TO` | `auto` | `auto` (the server if enabled, else the softphone), `server`, `softphone`, `both` |
| `GSM_ECHO_TEST` | `0` | `1`: incoming GSM calls are answered and echoed back (test of the GSM side) |
| `USSD_ENABLED` | `1` | `1`: `*code#` dialled from the SIP side is sent as USSD |
| `USSD_LOG_TEXT` | `0` | `1`: the text of USSD replies is also written in the log (`Got USSD type <n> '<type>': [<text>]`), for a local tool such as a status page with USSD menus. A local tool sends a USSD with `asterisk -rx "channel originate Local/s@ussd-console application QUECTEL_SEND_USSD quectel0,*100#"`. Off by default: a reply may hold a balance or codes ([SECURITY.md](SECURITY.md)) |
| `RINGBACK` | `network` | `network`: the operator's ringback; `local`: generated by the gateway |
| `DIAL_ALLOW` | empty | numbers allowed for calls and SMS (extended regular expression on the dialled number; empty = any). Example, French mobiles only: `^(0[67]\|[+]33[67])[0-9]{8}$`. Write `[+]` for a literal `+`; spaces, backslashes, `"` and `;` are refused. A refused number is logged (`not allowed by DIAL_ALLOW`), nothing reaches the module |
| `JITTER_BUFFER` | `adaptive` | jitter buffer on the voice from SIP to the modem: `adaptive`, `fixed` or `off`. Keep it with USB audio when the SIP side is reached through a VPN, Wi-Fi or Internet: without it the call can be silent both ways ([TROUBLESHOOTING.md](TROUBLESHOOTING.md#no-voice-at-all-in-a-call)) |
| `COUNTRY` | `fr` | country of the tones (busy, ringback), two letters |
| `SIP_BIND`, `SIP_PORT` | `0.0.0.0`, `5060` | address and UDP port of SIP |
| `RTP_START`, `RTP_END` | `10000`, `10100` | UDP port range of the voice (RTP) |
| `GSM_VERBOSE` | `0` | Asterisk verbosity, 0 to 5. **Above 0, the log shows full numbers and SMS texts.** |

Passwords may not contain `;`, `\`, `"` or a newline.

## Everyday use

```
docker compose logs -f                        # log (numbers masked with GSM_VERBOSE=0)
docker compose exec gateway gw-check          # status
docker compose exec gateway gw-config show    # generated settings, passwords hidden
docker compose exec gateway asterisk -r       # Asterisk console (quit with "exit")
docker compose restart                        # restart
```

Update to a new version:

```
git pull
docker compose up -d --build
```

Remove: `docker compose down`, then delete the folder. The module keeps its USB audio
setting.
