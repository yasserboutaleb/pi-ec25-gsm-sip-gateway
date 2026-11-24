# Troubleshooting

Start with:

```
docker compose ps                             # running, healthy?
docker compose exec gateway gw-check          # modem, network, SIP
docker compose logs --tail 100                # what happened
```

## The container does not start, or restarts in a loop

- `gw-config: ...` in the log: a setting is invalid, and the message names it. Fix `.env`, then
  `docker compose up -d`. Check without starting: `docker compose run --rm gateway gw-config check`.
- `env file ... .env not found`: copy `.env.example` to `.env` first.

## Modem: `Not connected`

The AT port cannot be opened.

- `ls -l /dev/serial/by-id/` on the host must show `usb-Android_Android-if02-port0`. If not,
  check the cable, the adapter and the power (`lsusb -d 2c7c:0125`, `dmesg | tail`).
- **ModemManager** may hold the port: `sudo systemctl disable --now ModemManager`.
- Another program (a serial terminal left open) may hold it: `sudo fuser -v /dev/ttyUSB*`.
- The driver retries every 15 s: no restart is needed once the port is back.

## Modem: `GSM not registered`

- `Needs PIN code!` in the log: remove the PIN of the SIM (in a phone).
- No antenna, or no coverage for the module's bands.
- A SIM without an active subscription.

## Modem: `NoVoice`, or calls without sound

- **No sound card**: the log shows `no USB sound card: USB audio of the modem not enabled`, and
  `cat /proc/asound/cards` on the host has no `Android` card. Enable USB audio once, see
  [HARDWARE.md](HARDWARE.md#enable-usb-audio-once).
- `MODEM_ALSA_DEVICE` must name the module's card (`hw:CARD=Android`).
- The driver enables voice again by itself when no call is open; `NoVoice` that lasts more than
  a minute without a call points to the sound card or to the module.

## No voice at all in a call

The call is set up and answered, but nobody hears anything, not even the ringback; the echo
test `9600` works. With USB audio the driver writes the voice to the module at a steady pace,
and the capture stream is linked to the playback stream. If the voice from SIP arrives in bursts
(VPN, Wi-Fi, Internet), the playback buffer empties, both streams stop (XRUN), and the call stays
silent both ways. Keep `JITTER_BUFFER=adaptive` (the default), or try `fixed`. On the host,
`cat /proc/asound/card*/pcm0p/sub0/status` showing `XRUN` after a call points to this.

## The module disappears during calls, or resets

Almost always the power supply. `vcgencmd get_throttled` on a Raspberry Pi shows past
under-voltage (any value other than `0x0`). Use the official supply and a powered USB hub, see
[HARDWARE.md](HARDWARE.md#power). The container keeps running and the driver reconnects when
the module is back.

## Softphone

| Symptom | Cause |
|---|---|
| `401 Unauthorized` again and again | wrong user name or password: the user name **and** the authentication name are `SOFTPHONE_USERNAME` |
| no answer at all, or `403` | the softphone's address is not in `SOFTPHONE_NETWORK`; or the host firewall blocks UDP `SIP_PORT` |
| `No matching endpoint found` in the log | the softphone sends another user name than `SOFTPHONE_USERNAME` |
| registered, but the call to `9600` has no sound | RTP blocked: the host firewall must accept UDP `RTP_START`-`RTP_END` from the softphone |
| a second device takes over the first | one device at a time: the last registration wins |

## Calls

- **Outgoing call refused at once**: the number must be digits and `+` only
  (no spaces, no dashes); the log shows `call refused: invalid number`.
- **The caller hears nothing before the answer**: some networks send no ringback, e.g. on
  VoLTE. Set `RINGBACK=local`.
- **Incoming GSM call rejected as busy**: no destination registered, reachable or free (softphone not
  registered, server unreachable or busy). `INCOMING_CALLS_TO` chooses the destination.
- **The call ends after about 60 s of silence**: no RTP was received for 60 s (hang-up safety).
  Check the firewall and NAT for RTP.
- **No audio in one direction with a server**: NAT, see [SIP-SERVER.md](SIP-SERVER.md#nat).
- **Test each half separately**: `9600` from the SIP side tests SIP and RTP without any GSM
  call; `GSM_ECHO_TEST=1` answers incoming GSM calls with an echo, which tests the GSM side and
  the module's audio without SIP.

## SMS

- **Received SMS do not reach the softphone**: the softphone must be registered (messages are
  sent to its registered contact). The log shows `sms in ...` when an SMS is received, and
  `message to SIP not delivered` when the softphone or the server did not accept it.
- **Sent SMS**: the log shows `sms out ...` when a message is accepted, `sms out refused` for an
  invalid number or an empty text, and `Error sending message` when the network refused it.
  The gateway sends no failure message back to the softphone.
- **Long SMS**: received parts are joined into one message; outgoing long texts are split into
  several parts automatically.
- Unread SMS left in the module (e.g. received while the gateway was stopped) are read at the
  next start of the driver.

## USSD

- No reply: the code depends on the operator (`*100#` is only an example), and
  `USSD_ENABLED` must be `1`. The log shows `ussd request ...` and `ussd reply ...`.

## Server registration (`register` mode)

`gw-check` shows the `server-reg` line. `Rejected` or `Unregistered`:

- wrong `SERVER_USERNAME` / `SERVER_PASSWORD`, or the account does not exist on the server.
  After a rejected password the gateway stops trying: fix `.env`, then `docker compose up -d`;
- `SERVER_HOST` / `SERVER_PORT` unreachable from the host (DNS, firewall, NAT): retried every
  60 s;
- after a `403` the gateway waits 600 s before trying again; `docker compose restart` retries
  at once.

## More detail

- `GSM_VERBOSE=3` and `docker compose up -d` give a detailed log, **with full numbers and SMS
  texts**: set it back to `0` afterwards.
- The Asterisk console: `docker compose exec gateway asterisk -r`, then for example
  `quectel show devices`, `pjsip show endpoints`, `pjsip show registrations`. Quit with `exit`.
- The generated configuration, passwords hidden: `docker compose exec gateway gw-config show`.
