#!/bin/sh
set -eu
# Database migrations are a separate release step, never run concurrently by workers.
# Log URL paths only. Query strings and referrers may contain OAuth codes.
exec gunicorn unbound.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers "${WEB_CONCURRENCY:-2}" --timeout 60 --access-logfile - --error-logfile - --access-logformat '%(h)s %(t)s "%(m)s %(U)s %(H)s" %(s)s %(b)s %(L)s'
