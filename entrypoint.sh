#!/bin/sh
set -eu
if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/data
  chown -R radar:radar /app/data
  exec gosu radar "$@"
fi
exec "$@"
