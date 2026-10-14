#!/bin/sh
# Run on the target VPS after image loading and first-time private provisioning.
# This script only creates explicitly named portable-memory resources.
set -eu
test -f /srv/portable-memory/secrets/startup.json
test -f /srv/portable-memory/data/memory.sqlite
! docker container inspect portable-memory >/dev/null 2>&1
! docker container inspect portable-memory-proxy >/dev/null 2>&1
! docker network inspect portable-memory-net >/dev/null 2>&1
! ss -ltnH | awk '{print $4}' | grep -q ':3014$'
docker image inspect portable-memory:hosted-v0 >/dev/null
docker pull nginx:stable-alpine
chmod 644 /srv/portable-memory/nginx.conf
docker network create --label project=portable-memory portable-memory-net
docker run -d --name portable-memory --label project=portable-memory \
  --network portable-memory-net --restart unless-stopped \
  --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --memory 256m --memory-swap 256m --cpus 0.25 --pids-limit 64 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --log-driver json-file --log-opt max-size=5m --log-opt max-file=2 \
  --mount type=bind,src=/srv/portable-memory/data,dst=/data \
  --mount type=bind,src=/srv/portable-memory/secrets/startup.json,dst=/run/secrets/startup.json,readonly \
  --health-cmd 'python -c "import urllib.request; r=urllib.request.urlopen(\"http://127.0.0.1:8080/healthz\",timeout=4); assert r.status==200"' \
  --health-interval 30s --health-timeout 5s --health-retries 3 --health-start-period 30s \
  portable-memory:hosted-v0
docker run -d --name portable-memory-proxy --label project=portable-memory \
  --network portable-memory-net --restart unless-stopped --user 101:101 \
  --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --memory 64m --memory-swap 64m --cpus 0.10 --pids-limit 32 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --log-driver json-file --log-opt max-size=5m --log-opt max-file=2 \
  --mount type=bind,src=/srv/portable-memory/nginx.conf,dst=/etc/nginx/nginx.conf,readonly \
  -p 127.0.0.1:3014:8080 --entrypoint nginx nginx:stable-alpine -g 'daemon off;'
