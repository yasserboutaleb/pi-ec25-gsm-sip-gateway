# The chan_quectel driver

The gateway uses [chan_quectel](https://github.com/yasserboutaleb/asterisk-chan-quectel), the
Asterisk channel driver for Quectel modules, from a fork maintained with this project. The
original driver ([RoEdAl/asterisk-chan-quectel](https://github.com/RoEdAl/asterisk-chan-quectel),
itself derived from chan_dongle) is archived.

## What the fork changes

The fork's README lists every change. Those that matter for this gateway:

- **call tracking** with call state notifications (`+QIND "ccinfo"`) and `AT+CLCC` polling
  together (`MODEM_CLCC_POLL`): an outgoing call whose "dialing" notification arrives before
  the `OK` of `ATD` is no longer hung up as unknown; a call left open in the module (after a
  crash of Asterisk during a call) is hung up;
- **refused hang-ups** retried with another command instead of blocking the line;
- **voice enabled again** after a crash of Asterisk during a call, and a module restarted
  when it refuses its voice settings right after a reset;
- **SMS announced while another one is read** are queued instead of being lost until the next
  start;
- **`quectel show device state`** no longer crashes Asterisk on 64-bit hosts before the module
  registers.

## How the image builds it

The `Dockerfile` fetches the fork **at a pinned commit** and checks its **Git tree id**, then
builds the driver against the `asterisk-dev` package of Ubuntu 22.04 (Asterisk 18):

```
ARG CHAN_QUECTEL_REPO=https://github.com/yasserboutaleb/asterisk-chan-quectel.git
ARG CHAN_QUECTEL_COMMIT=<full commit id>
ARG CHAN_QUECTEL_TREE=<tree id of that commit>
```

The tree id identifies the exact source files: if the commit were replaced by other content,
the build stops. The image records what it was built from:

```
docker compose exec gateway cat /usr/share/gsm-gateway/chan_quectel.source
```

`gw-check` prints the same lines.

## Updating the driver

1. Choose the commit of the fork and get its tree id:

   ```
   git clone https://github.com/yasserboutaleb/asterisk-chan-quectel.git
   cd asterisk-chan-quectel
   git rev-parse <commit>              # full commit id
   git rev-parse '<commit>^{tree}'     # tree id
   ```

2. Put both in the `ARG` lines of the `Dockerfile`.
3. Run the bench, which builds the image and tests it against a simulated module:

   ```
   sh tests/bench.sh
   ```

4. Rebuild and restart: `docker compose up -d --build`.

To try another fork or a local change, pass the three values as build arguments, for example
`docker compose build --build-arg CHAN_QUECTEL_REPO=... --build-arg CHAN_QUECTEL_COMMIT=...
--build-arg CHAN_QUECTEL_TREE=...`.

## Driver settings used by the gateway

`gw-config` writes `quectel.conf` from `.env`. The fixed choices:

| Setting | Value | Why |
|---|---|---|
| `context` | `from-gsm` | dialplan of incoming calls, SMS and USSD replies |
| `uac` / `alsadev` | `on`, `MODEM_ALSA_DEVICE` | voice over the module's USB audio (`MODEM_AUDIO=uac`) |
| `slin16` | `off` | the EC25's voice is 8 kHz |
| `clcc_poll` | `MODEM_CLCC_POLL` | polling of the call states, in addition to the notifications. The fixes above need it: with `0`, refused hang-ups, unknown calls and voice are no longer retried or recovered |
| `qhup` | `on` | hang up a call by its index (`AT+QHUP`) |
| `msg_direct` | `off` | SMS announced by `+CMTI`, read with `AT+CMGR` |
| `autodeletesms` | `yes` | SMS deleted from the module once read: the storage never fills up |
| `resetmodem` | `no` | no `ATZ` at start: the module keeps its settings |
| `smsdb` | `:memory:` | parts of long SMS kept in memory until complete |
| `interval` | `15` | seconds between two attempts to open a missing module |
