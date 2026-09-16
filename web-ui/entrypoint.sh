#!/bin/sh
set -eu

envsubst < /etc/nginx/templates/config.js.template > /usr/share/nginx/html/config.js
exec "$@"