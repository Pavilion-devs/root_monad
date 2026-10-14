#!/bin/sh
# A one-time stopped SQLite snapshot and restore; touches only this deployment.
set -eu
base=/srv/portable-memory
test -d "$base/data"
test ! -e "$base/backups/verified-checkpoint"
test ! -e "$base/backups/data-before-restore"
docker stop --timeout 30 portable-memory
test "$(docker inspect --format '{{.State.Status}}' portable-memory)" = exited
# Leave an intact source copy and recover it if copying fails.
trap 'if test ! -d "$base/data" && test -d "$base/backups/data-before-restore"; then cp -a "$base/backups/data-before-restore" "$base/data"; fi; docker start portable-memory >/dev/null' EXIT
cp -a "$base/data" "$base/backups/verified-checkpoint"
mv "$base/data" "$base/backups/data-before-restore"
cp -a "$base/backups/verified-checkpoint" "$base/data"
printf 'Stopped database snapshot restored; original data preserved.\n'
