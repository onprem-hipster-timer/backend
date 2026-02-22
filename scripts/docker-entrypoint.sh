#!/bin/sh
set -e
# SQLite DB용 디렉터리: 볼륨 마운트 시 root 소유가 되므로 appuser에 쓰기 권한 부여
mkdir -p /app/data
chown -R appuser:appuser /app/data
exec gosu appuser "$@"
