# Connecting a SIP server or PBX

This page shows how to connect the gateway to an **Asterisk** server with `chan_pjsip`
(Asterisk 16 or later), in both modes, with notes for FreePBX. It also lists the exact SIP
requests the gateway sends and accepts, so that you can adapt it to another server.

Example values on this page:

| Value | Example |
|---|---|
| SIP server | `pbx.example.com` |
| Gateway account on the server (`register` mode) | `gw1` |
| Extension of the user's phone, which receives GSM calls and SMS | `101` |
| `ip` mode: server and gateway addresses (same LAN, or a VPN of the host) | server `10.8.0.1`, gateway `10.8.0.2` |

## What the gateway sends and accepts

| Direction | Request | Details |
|---|---|---|
| Gateway -> server: **incoming GSM call** | `INVITE sip:<SERVER_EXTENSION>@<SERVER_HOST>:<SERVER_PORT>` | **register**: `From: "<caller number>" <sip:<SERVER_USERNAME>@<SERVER_HOST>>`, plus `P-Asserted-Identity` with the caller number; the gateway answers digest challenges with its account. **ip**: `From: <sip:<caller number>@...>`. The server rings for up to 60 s; the GSM call is answered only when the server answers. If the server replies busy, is unreachable or congested, the GSM call is rejected as **busy** (cause 17), so the operator's forward-on-busy or voicemail applies. No answer: normal hang-up. |
| Server -> gateway: **outgoing call** | `INVITE sip:<number>@<gateway>` | Number: digits and `+` (e.g. `0612...`, `+33612...`). Anything else in the number is refused. Dialled for up to 120 s. Ringback: `RINGBACK`. |
| Server -> gateway: **USSD** | `INVITE sip:*<code>#@<gateway>` | Starts with `*` or `#`, only digits, `*` and `#` (`%23` is read as `#`). The gateway answers, plays a short tone, hangs up, and sends the network's reply as a `MESSAGE` from `ussd` to `SERVER_EXTENSION`. `USSD_ENABLED=0` refuses it. |
| Server -> gateway: **echo test** | `INVITE sip:9600@<gateway>` | Answered and echoed back without any GSM call: checks the audio path between the server and the gateway. |
| Gateway -> server: **received SMS** | `MESSAGE sip:<SERVER_EXTENSION>@<SERVER_HOST>` | Body: the text of the SMS, as received (long SMS joined). **register**: `From: "<sender>" <sip:<SERVER_USERNAME>@<SERVER_HOST>>`, the sender is the display name; the gateway answers digest challenges. **ip**: `From: <sip:<sender>@<SERVER_LOCAL_ADDRESS>>`. |
| Server -> gateway: **SMS to send** | `MESSAGE sip:<number>@<gateway>` | The body is sent as an SMS to `<number>` (digits and an optional `+`), split in several parts if it is long, valid 1 day, without delivery report. The gateway answers `202 Accepted`; a sending failure is written to the gateway's log only. |
| Gateway -> server | `REGISTER` (**register** mode) | Every 300 s, `Contact` with a `line` parameter. Retried every 60 s after a temporary failure (no answer, 5xx), every 600 s after a 403. A rejected password stops the registration until the gateway restarts. |
| Gateway -> server | `OPTIONS` | Every 60 s (qualify). |

Media: RTP/AVP, G.711 (`SERVER_CODEC`: `ulaw` and/or `alaw`), DTMF RFC 4733, no SRTP. The gateway
hangs up an answered call after **60 s without RTP**, so a GSM call is never left open after
the server or the network disappears. Use the same setting on the server (`rtp_timeout`).

### How the gateway recognises its server

- **register mode**: the gateway accepts a request from the server only when it arrives on
  the **registered line**: the request URI must carry the `line` parameter of the `Contact`
  that the gateway registered. Any other request is rejected, so nobody else can call or send
  SMS through the gateway's server account.
  - Calls: dialling `PJSIP/<number>@gw1` on the server sends the call to the registered
    contact, with the user part replaced by the number. Nothing special is needed.
  - **SIP MESSAGE: `MessageSend()` must target the registered contact explicitly**, with the
    user part replaced by the destination number. A message to `sip:<number>@<gateway>`
    without the `line` parameter is rejected. See the example below.
- **ip mode**: the gateway identifies the server by its source address (`SERVER_HOST`),
  without authentication. Use it only on a network where nobody else can use that address: a
  VPN of the host, or a trusted LAN. See [SECURITY.md](SECURITY.md).

## Register mode (recommended)

The gateway registers with the server like a phone. This works through NAT, for example when
the server is on the Internet and the gateway behind a home router.

`.env` of the gateway:

```
SERVER_ENABLED=1
SERVER_MODE=register
SERVER_HOST=pbx.example.com
SERVER_PORT=5060
SERVER_USERNAME=gw1
SERVER_PASSWORD=<long random secret>
SERVER_EXTENSION=101
SERVER_CODEC=ulaw
```

### `pjsip.conf` (server)

```ini
; ---- the gateway: registers as gw1
[gw1]
type = endpoint
context = from-gw1                 ; incoming GSM calls
message_context = from-gw1-msg     ; received SMS and USSD replies
disallow = all
allow = ulaw                       ; same as SERVER_CODEC
auth = gw1-auth
aors = gw1
direct_media = no
rtp_symmetric = yes                ; the gateway may be behind NAT
force_rport = yes
rewrite_contact = yes              ; see "NAT" below
rtp_timeout = 60
dtmf_mode = rfc4733

[gw1-auth]
type = auth
auth_type = userpass
username = gw1
password = <long random secret>

[gw1]
type = aor
max_contacts = 1                   ; one contact: MessageSend targets it
remove_existing = yes
qualify_frequency = 60

; ---- the user's phone
[101]
type = endpoint
context = from-phones
message_context = from-phones-msg
disallow = all
allow = ulaw,alaw
auth = 101-auth
aors = 101
direct_media = no
rtp_symmetric = yes
force_rport = yes
rewrite_contact = yes
rtp_timeout = 60
dtmf_mode = rfc4733

[101-auth]
type = auth
auth_type = userpass
username = 101
password = <another secret>

[101]
type = aor
max_contacts = 1
remove_existing = yes
```

### `extensions.conf` (server)

```ini
; ---- incoming GSM calls from the gateway: request URI user = SERVER_EXTENSION
[from-gw1]
exten => 101,1,NoOp(GSM call from ${CALLERID(name)})
 ; register mode: the From user is gw1, the caller number is the display name
 same => n,Set(CALLERID(num)=${CALLERID(name)})
 same => n,Dial(PJSIP/101,60)
 ; busy or unreachable: answer "busy", the gateway rejects the GSM call as busy
 same => n,GotoIf($["${DIALSTATUS}" = "NOANSWER"]?done)
 same => n,Hangup(17)
 same => n(done),Hangup()

; ---- SMS and USSD replies from the gateway -> phone 101
[from-gw1-msg]
exten => 101,1,Set(F=${MESSAGE(from)})
 ; register mode: the sender (number or "ussd") is the display name
 same => n,Set(SENDER=${FILTER(0-9a-zA-Z+,${CUT(F,<,1)})})
 ; From = <sip:sender@pbx>, so that the phone's reply goes back to that number
 same => n,MessageSend(pjsip:101,<sip:${SENDER}@pbx.example.com>)
 same => n,Hangup()

; ---- calls from the phone
[from-phones]
exten => 101,1,Dial(PJSIP/101,30)
; echo test of the gateway (server <-> gateway audio, no GSM call)
exten => 9600,1,Dial(PJSIP/9600@gw1,30)
; USSD: *code# (the reply comes back as a message)
exten => _[*#].,1,Dial(PJSIP/${EXTEN}@gw1,30)
; mobile numbers, national (0...) and international (+...); adapt to your numbering plan
exten => _0X.,1,Dial(PJSIP/${EXTEN}@gw1,120)
exten => _+X.,1,Dial(PJSIP/${EXTEN}@gw1,120)

; ---- messages from the phone to a number -> SMS through the gateway
[from-phones-msg]
exten => _[+0-9].,1,NoOp(SMS to ${EXTEN})
 ; the registered contact of the gateway, e.g. sip:gw1@203.0.113.7:5060;line=abcdefg
 same => n,Set(CONTACT=${PJSIP_CONTACT(${PJSIP_AOR(gw1,contact)},uri)})
 ; same contact (it carries the "line" parameter), user part replaced by the number
 same => n,MessageSend(pjsip:gw1/${STRREPLACE(CONTACT,gw1@,${EXTEN}@)},<sip:101@pbx.example.com>)
 same => n,NoOp(MessageSend: ${MESSAGE_SEND_STATUS})
 same => n,Hangup()
```

`STRREPLACE()` takes a **variable name** as its first argument, which is why the contact is
stored in `CONTACT` first. Restrict who may send SMS: every message becomes an SMS paid on the
SIM's subscription.

## IP mode (trusted peer)

Use this mode when the server and the gateway share a private network that nobody else can
use: a VPN configured on the host (WireGuard, OpenVPN...), or a trusted LAN. No password is
used.

`.env` of the gateway:

```
SERVER_ENABLED=1
SERVER_MODE=ip
SERVER_HOST=10.8.0.1
SERVER_PORT=5060
SERVER_EXTENSION=101
SERVER_LOCAL_ADDRESS=10.8.0.2
```

`SERVER_LOCAL_ADDRESS` is the address of the gateway as the server sees it; it is the host
part of the `From` of the SMS and USSD replies sent to the server (`gateway` when empty). The
gateway does not configure the VPN.

### `pjsip.conf` (server)

```ini
[gw1]
type = endpoint
context = from-gw1
message_context = from-gw1-msg
disallow = all
allow = ulaw
aors = gw1
direct_media = no
rtp_symmetric = yes
rtp_timeout = 60
dtmf_mode = rfc4733

[gw1]
type = aor
contact = sip:10.8.0.2:5060
qualify_frequency = 60

[gw1-identify]
type = identify
endpoint = gw1
match = 10.8.0.2
```

The phone `101` is the same as in register mode.

### `extensions.conf` (server)

The differences from register mode: the caller number is the `From` user part, so
`CALLERID(num)` is already right, and messages go to the fixed address of the gateway.

```ini
[from-gw1]
exten => 101,1,Dial(PJSIP/101,60)
 same => n,GotoIf($["${DIALSTATUS}" = "NOANSWER"]?done)
 same => n,Hangup(17)
 same => n(done),Hangup()

[from-gw1-msg]
exten => 101,1,Set(F=${MESSAGE(from)})
 ; ip mode: From = <sip:sender@10.8.0.2>; keep the user part
 same => n,Set(U=${CUT(F,@,1)})
 same => n,Set(SENDER=${CUT(U,:,2)})
 same => n,MessageSend(pjsip:101,<sip:${SENDER}@10.8.0.1>)
 same => n,Hangup()

[from-phones-msg]
exten => _[+0-9].,1,MessageSend(pjsip:gw1/sip:${EXTEN}@10.8.0.2:5060,<sip:101@10.8.0.1>)
 same => n,Hangup()
```

The `[from-phones]` context is the same as in register mode (`Dial(PJSIP/<number>@gw1)`).

## NAT

- **Gateway behind NAT** (register mode): the gateway opens no port on the Internet.
  Signalling from the server comes back through the mapping created by the gateway's own
  `REGISTER` (every 300 s) and `OPTIONS` (every 60 s), and media through the mapping created
  by its own RTP. The server's endpoint for the gateway therefore needs `rtp_symmetric = yes`,
  `force_rport = yes` and `direct_media = no`.
- **`rewrite_contact = yes`** makes the server use the source address of the `REGISTER`
  instead of the gateway's private address. It only works when the server sees the gateway's
  real (public, NATed) address. If something in front of the server rewrites source addresses
  (Docker's userland proxy, a load balancer that does not understand SIP), the stored contact
  is wrong: run the server with host networking.
- **Server behind NAT** (`external_media_address`, `external_signaling_address`, `local_net`
  on its transport): in register mode, `local_net` must not include the address the server
  sees for the gateway, or the server sends its internal address to the gateway (no audio
  towards the mobile, lost hang-ups). In ip mode over a VPN, add the VPN subnet to `local_net`.
- Symptoms of a NAT problem: the call connects but there is no audio in one or both
  directions, or a hang-up is not passed on. See [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## FreePBX

The same logic applies. These steps have not been tested by the project, and menu names vary
between versions.

- **Register mode**: create a PJSIP trunk for the gateway with *Authentication: Inbound*,
  *Registration: Receive*, the gateway's username and secret, and *Max contacts* 1. Enable
  *Rewrite Contact*, *RTP Symmetric* and *Force rport*. Route outgoing calls (`0X.`, `+X.` and
  the `*`/`#` USSD codes) to that trunk. Add an inbound route whose DID is `SERVER_EXTENSION`.
- **IP mode**: PJSIP trunk with *Authentication: None*, *Registration: None*, *SIP Server*
  `10.8.0.2`, *Match (Permit)* `10.8.0.2`.
- **SIP MESSAGE** is not routed by the FreePBX interface. Put the message contexts above in
  `extensions_custom.conf` and set the `message_context` of the trunk and of the extensions
  (for example through `pjsip.endpoint_custom_post.conf`).

## Checking

1. On the gateway: `docker compose exec gateway gw-check`. In register mode, the `server-reg`
   line must show `Registered`. On the server, `pjsip show contacts` lists the gateway's
   contact with its `line` parameter.
2. From the phone, call **9600**: you should hear yourself, without any GSM call.
3. Call a mobile number, then call the SIM's number from a mobile.
4. Send a message from the phone to a mobile number, then reply with an SMS.
5. Dial a USSD code such as `*100#` (it depends on the operator).

The bench of the project (`tests/bench.sh`) checks the gateway's side of both modes against a
fake server: registration with digest authentication, incoming call relayed as busy, SMS in
both directions (with and without the `line` parameter), calls from the server.
