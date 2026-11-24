# pi-ec25-gsm-sip-gateway — Asterisk 18 (Ubuntu 22.04) with the chan_quectel driver.
#
# The driver is built from the public fork, pinned by commit, and its Git tree is checked
# (a GitHub tarball is not byte-stable, a Git tree id is). To update the driver, change the
# two ARG lines below and run the bench (tests/bench.sh).

ARG UBUNTU=ubuntu:22.04

# ---------------------------------------------------------------- driver build
FROM ${UBUNTU} AS driver
ARG CHAN_QUECTEL_REPO=https://github.com/yasserboutaleb/asterisk-chan-quectel.git
ARG CHAN_QUECTEL_COMMIT=a6454332d8f7331b10ea266d3e8ff1f0b02d5aa6
ARG CHAN_QUECTEL_TREE=92b881966a403c42d5b6154558e12caba1c1d182
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      asterisk-dev build-essential cmake pkg-config git ca-certificates \
      libsqlite3-dev libasound2-dev \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /usr/src/chan_quectel
RUN git init -q . \
 && git fetch -q --depth 1 "$CHAN_QUECTEL_REPO" "$CHAN_QUECTEL_COMMIT" \
 && git checkout -q --detach FETCH_HEAD \
 && [ "$(git rev-parse HEAD)" = "$CHAN_QUECTEL_COMMIT" ] \
 && tree="$(git rev-parse 'HEAD^{tree}')" \
 && { [ "$tree" = "$CHAN_QUECTEL_TREE" ] || { echo "chan_quectel: tree $tree, expected $CHAN_QUECTEL_TREE" >&2; exit 1; }; } \
 && rm -rf .git
# (without .git, CMake does not try "git describe", which needs the whole history)
RUN ASTH="$(dpkg -L asterisk-dev | grep -m1 '/asterisk\.h$')" \
 && cmake -S . -B build \
      -DCMAKE_BUILD_TYPE=Release \
      -DCMAKE_INSTALL_PREFIX=/usr \
      -DAST_HEADER_DIR="$(dirname "$ASTH")" \
      -DBUILD_TESTING=OFF \
 && cmake --build build --parallel "$(nproc)" \
 && DESTDIR=/out cmake --install build \
 && find /out -name chan_quectel.so | grep -q . \
 && mkdir -p /out/usr/share/gsm-gateway \
 && printf 'repository %s\ncommit %s\ntree %s\n' "$CHAN_QUECTEL_REPO" "$CHAN_QUECTEL_COMMIT" "$CHAN_QUECTEL_TREE" \
      > /out/usr/share/gsm-gateway/chan_quectel.source \
 && rm -rf /out/etc

# ---------------------------------------------------------------- runtime image
FROM ${UBUNTU}
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      asterisk libsqlite3-0 libasound2 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=driver /out/ /
# The configuration is generated at every start from the environment (gateway/gw-config):
# the sample files of the Ubuntu package are kept aside, only for the tone tables and paths.
RUN mkdir -p /usr/share/gsm-gateway/asterisk-samples \
 && mv /etc/asterisk/* /usr/share/gsm-gateway/asterisk-samples/ \
 && ldd "$(find /usr/lib -name chan_quectel.so -print -quit)" | grep -q 'libasound' \
 && find /usr/lib -name func_json.so | grep -q .
COPY gateway/templates/ /usr/share/gsm-gateway/templates/
COPY gateway/gw-config gateway/gw-check gateway/entrypoint.sh /usr/local/sbin/
RUN sed -i 's/\r$//' /usr/local/sbin/gw-* /usr/local/sbin/entrypoint.sh /usr/share/gsm-gateway/templates/* \
 && chmod 0755 /usr/local/sbin/gw-* /usr/local/sbin/entrypoint.sh

HEALTHCHECK --interval=60s --timeout=10s --start-period=90s --retries=3 CMD ["/usr/local/sbin/gw-check", "--health"]
ENTRYPOINT ["/usr/local/sbin/entrypoint.sh"]
