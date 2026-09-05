#!/bin/sh
set -eu

mkdir -p /data
ln -sfn /app/web_run.py /data/web_run.py
ln -sfn /app/web_panel /data/web_panel

persist_file() {
  app_file="$1"
  data_file="$2"
  legacy_dir="${data_file}.legacy-dir"

  if [ -L "$data_file" ]; then
    rm -f "$data_file"
  fi

  if [ -d "$app_file" ] && [ ! -L "$app_file" ]; then
    if ! rmdir "$app_file" 2>/dev/null; then
      if [ -e "$legacy_dir" ]; then
        echo "Cannot migrate $app_file: $legacy_dir already exists" >&2
        exit 1
      fi
      mv "$app_file" "$legacy_dir"
    fi
  fi

  if [ -f "$app_file" ] && [ ! -L "$app_file" ] && [ ! -e "$data_file" ]; then
    cp "$app_file" "$data_file"
  fi

  if [ -L "$app_file" ] || [ -f "$app_file" ]; then
    rm -f "$app_file"
  fi
  ln -s "$data_file" "$app_file"
}

persist_file /app/ToolDelta基本配置.json /data/ToolDelta基本配置.json
persist_file /app/fbtoken /data/fbtoken

if [ "$#" -eq 0 ]; then
  set -- python web_run.py --host 0.0.0.0 --port 5101
fi

exec "$@"
