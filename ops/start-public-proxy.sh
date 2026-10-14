#!/bin/sh
set -eu
image=nginx@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
test -f /srv/portable-memory/nginx-public.conf
test "$(docker inspect --format '{{index .Config.Labels "project"}}' portable-memory-proxy)" = portable-memory
! docker container inspect portable-memory-proxy-before-public >/dev/null 2>&1
docker run --rm --network portable-memory-net --user 101:101 --read-only --cap-drop ALL --security-opt no-new-privileges:true --memory 64m --cpus 0.10 --tmpfs /tmp:rw,noexec,nosuid,size=16m --mount type=bind,src=/srv/portable-memory/nginx-public.conf,dst=/etc/nginx/nginx.conf,readonly --entrypoint nginx "$image" -t
docker stop --timeout 15 portable-memory-proxy
docker rename portable-memory-proxy portable-memory-proxy-before-public
if ! docker run -d --name portable-memory-proxy --label project=portable-memory \
  --network portable-memory-net --restart unless-stopped --user 101:101 \
  --read-only --cap-drop ALL --security-opt no-new-privileges:true \
  --memory 64m --memory-swap 64m --cpus 0.10 --pids-limit 32 \
  --tmpfs /tmp:rw,noexec,nosuid,size=16m \
  --log-driver json-file --log-opt max-size=5m --log-opt max-file=2 \
  --mount type=bind,src=/srv/portable-memory/nginx-public.conf,dst=/etc/nginx/nginx.conf,readonly \
  -p 127.0.0.1:3014:8080 -p 10.3.245.2:3014:8080 \
  --entrypoint nginx "$image" -g 'daemon off;'; then
  docker rename portable-memory-proxy portable-memory-proxy-failed-public || true
  docker rename portable-memory-proxy-before-public portable-memory-proxy
  docker start portable-memory-proxy
  exit 1
fi
