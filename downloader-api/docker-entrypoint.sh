#!/bin/sh
# Platforms change their sites often, and an old extractor is the most common reason
# downloads break. Unless AUTO_UPDATE=0, pull the newest engines on every start.
set -e

if [ "${AUTO_UPDATE:-1}" != "0" ]; then
    echo "Updating yt-dlp and gallery-dl…"
    pip install --no-cache-dir --quiet --upgrade "yt-dlp[default,curl-cffi]" gallery-dl \
        || echo "Engine update failed; starting with the installed versions."
fi

exec "$@"
