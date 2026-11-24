#!/bin/sh
# Container entrypoint: generates the Asterisk configuration from the environment, checks the
# modem devices, then runs Asterisk in the foreground.
set -eu

# a command given to the container runs instead of the gateway, e.g.
#   docker compose run --rm gateway gw-config check
[ "$#" -eq 0 ] || exec "$@"

gw-config generate || { echo "gateway: fix the settings in .env, then restart the container" >&2; exit 1; }

port=${MODEM_DATA_PORT:-/dev/serial/by-id/usb-Android_Android-if02-port0}
[ -e "$port" ] || echo "gateway: warning: modem port $port not found; the driver retries every 15 s." \
	"Check the USB cable, ls -l /dev/serial/by-id on the host, and that ModemManager is stopped." >&2
# no USB sound card (Docker hides /proc/asound inside containers: /dev/snd/by-id is checked instead)
if [ "${MODEM_AUDIO:-uac}" = uac ] && ! ls /dev/snd/by-id/usb-* >/dev/null 2>&1; then
	echo "gateway: warning: no USB sound card: USB audio of the modem not enabled (AT+QCFG=\"USBCFG\", see docs/HARDWARE.md)" >&2
fi

# USSD_REPLY_FILE (validated by gw-config): its folder, readable by root only (never /run or /tmp
# themselves); no reply left from a previous run
if [ -n "${USSD_REPLY_FILE:-}" ]; then
	d=$(dirname "$USSD_REPLY_FILE")
	mkdir -p "$d"
	case "$d" in /run | /tmp) ;; *) chmod 700 "$d" ;; esac
	rm -f "$USSD_REPLY_FILE"
fi

mkdir -p /var/run/asterisk /var/log/asterisk /var/lib/asterisk /var/spool/asterisk
# Asterisk runs as root in the container: the known-working setup for the serial and ALSA devices.
exec /usr/sbin/asterisk -f
