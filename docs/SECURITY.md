# Security

## Threat model

The gateway places calls and sends SMS on your mobile subscription: anyone who can drive it can
spend your credit, read your SMS and impersonate your number. What must be protected:

- the SIP access to the gateway (softphone account, server address in `ip` mode);
- the gateway's account on your SIP server (`register` mode);
- `.env`, which holds these passwords.

## Network exposure

The container uses the **host network**: Asterisk listens on `SIP_BIND:SIP_PORT` (UDP, every
address of the host by default) and on the RTP range `RTP_START`-`RTP_END` (UDP). Nothing else
is open: the Asterisk manager (AMI) is disabled and no HTTP or ARI module is loaded.

- **Never expose SIP or RTP to the Internet** (no port forwarding on your router). In
  `register` mode the gateway does not need any open port: requests and media from the server
  come back through the NAT mapping of its own outgoing traffic.
- Set `SIP_BIND` to one address of the host to listen on one network only.
- Filter on the **host firewall**. The gateway adds no firewall rule. Example with nftables,
  for a LAN `192.168.1.0/24` and the default ports:

  ```
  table inet gsm_gateway {
      chain input {
          type filter hook input priority filter - 1; policy accept;
          iif "lo" accept
          ct state established,related accept
          # softphones on the LAN; SIP limited to 20 packets/s per address (password guessing)
          udp dport 5060 ip saddr 192.168.1.0/24 meter sip_lan { ip saddr limit rate 20/second burst 40 packets } accept
          udp dport 10000-10100 ip saddr 192.168.1.0/24 accept
          # ip mode: the server only through the VPN interface, never by its address alone
          # iifname "wg0" udp dport { 5060, 10000-10100 } ip saddr 10.8.0.1 accept
          udp dport { 5060, 10000-10100 } drop
      }
  }
  ```

  Load it with `sudo nft -f gsm-gateway.nft`. To keep it across reboots, add it to your
  firewall's configuration **without** a `flush ruleset`, which would also remove Docker's
  rules.

  In `ip` mode, accept the server **only on the interface of the VPN** (`iifname`, here
  `wg0`). A rule on the address alone is not enough: with the reverse path filter in loose
  mode (the default of Ubuntu and Raspberry Pi OS), a device of the LAN can send packets with
  the server's address to the LAN interface; the host accepts them, and the gateway takes them
  for the server and places calls. The `meter` rule slows down password guessing from the LAN
  (packets above the rate fall through to the `drop` rule).

## SIP access control

- **Softphone**: disabled while `SOFTPHONE_PASSWORD` is empty; digest authentication; accepted
  only from `SOFTPHONE_NETWORK` and the loopback (Asterisk ACL); one registered device at a
  time. Use a long random password (`openssl rand -base64 18`).
- **Server, `register` mode**: the gateway accepts requests from the server only on its
  registered line (the `line` parameter of its `Contact`): unsolicited requests are rejected.
  Use a long random password for the gateway's account, and protect the server itself
  (fail2ban or similar if it is on the Internet).
- **Server, `ip` mode**: identified by its IP address only, without a password. Use it only
  on a network where nobody else can send packets with that address: a VPN of the host, or a
  trusted LAN. On a shared LAN any device can take the server's address and place calls: use
  `register` mode there. With a VPN, filter on its interface (example above).
- **Numbers that can be reached**: by default any number, including international and premium
  ones. Set `DIAL_ALLOW` to the numbers you really call (a regular expression, see
  [INSTALL.md](INSTALL.md)), so that a stolen password or a forged request cannot run up a bill on
  premium or international numbers. It applies to calls and SMS; USSD codes are not filtered.
- **No TLS, no SRTP** in this version: SIP and RTP are not encrypted. When the server is not on
  the LAN, carry the traffic in a VPN (WireGuard, OpenVPN...), or accept that calls and SMS
  cross the Internet in clear text.
- **Hang-up safety**: an answered call that receives no RTP for 60 s is hung up, so a GSM call
  is never left open (and charged) after the softphone, the server or the network disappears.

## Untrusted input

SMS texts, SIP `MESSAGE` bodies, dialled numbers and USSD replies come from outside. The
generated dialplan never interprets them:

- numbers are filtered (digits and `+`); a number with anything else is refused
  before it reaches `Dial()` or the driver;
- an SMS text is passed to the driver as a quoted argument, and never placed in an expression
  (`$[...]`) or a command;
- USSD codes are filtered (digits, `*` and `#`).

The bench (`tests/bench.sh`) sends texts with quotes, `${...}`, `$(...)` and commas, and numbers
containing `&`, and checks that they reach the network unchanged or are refused.

## Secrets

- `.env` holds the passwords: `chmod 600 .env`, and keep it out of any repository (it is in
  `.gitignore`).
- The generated Asterisk configuration (`/etc/asterisk` inside the container) contains them
  too; it is rebuilt at every start and is not stored on the host.
- `gw-config show` hides the passwords. `gw-check` prints no password and no identifier (IMEI,
  IMSI, ICCID, phone number).
- Passwords are refused when they contain `;`, `\`, `"` or a newline, which would break the
  generated configuration.

## Privacy of the logs

- With `GSM_VERBOSE=0` (default) the log shows numbers masked to their first four characters
  (`call in +336...`, `sms out 0639...`) and the length of SMS texts, never the texts. USSD codes
  are masked the same way (`ussd request *123...`): a recharge or payment code can be in them.
  Warnings of the driver about an unknown call may still show a number.
- `GSM_VERBOSE` above 0 shows full numbers and SMS texts: use it for a debugging session only.
- `USSD_LOG_TEXT=1` writes the text of USSD replies in the log (balance, menu, sometimes a
  code). Turn it on only for a local tool that needs it, on a host that only you can read.
- Docker keeps at most 3 log files of 5 MB (`logging` in `compose.yaml`).

## Container

- Asterisk runs as root inside the container, which is the known-working set-up for the
  serial and sound devices. The container is not privileged: it may only open serial ports
  (major 188) and sound devices (major 116) among the devices of `/dev`.
- The driver is built from a public fork pinned by commit and checked by Git tree
  ([DRIVER.md](DRIVER.md)).

## Reporting a vulnerability

Please report security issues privately through GitHub's security advisories of the
repository ("Report a vulnerability"), not in a public issue.
