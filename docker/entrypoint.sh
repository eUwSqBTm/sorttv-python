#!/bin/sh
set -e

# First run: create a config to edit.
if [ ! -f "$SORTTV_CONFIG" ]; then
    mkdir -p "$(dirname "$SORTTV_CONFIG")"
    { echo "# SORTTV_NOT_CONFIGURED - delete this line once you have edited this file"; cat /app/sorttv.conf.sample; } \
        > "$SORTTV_CONFIG"
    echo "Created $SORTTV_CONFIG from the sample."
fi

# Don't sort anything with the untouched sample settings. Wait instead of exiting, so a
# restart policy doesn't loop.
if grep -q "SORTTV_NOT_CONFIGURED" "$SORTTV_CONFIG"; then
    echo "Edit $SORTTV_CONFIG (directories, tvdb-api-key, tmdb-api-key), delete its first line,"
    echo "then restart the container."
    exec sleep infinity
fi

# No schedule: run once (or poll, if --poll-time was given) and exit.
if [ -z "$SORTTV_RUN_AT" ]; then
    exec python3 /app/sorttv.py "$@"
fi

case "$SORTTV_RUN_AT" in
    [0-2][0-9]:[0-5][0-9]) ;;
    *) echo "SORTTV_RUN_AT must be HH:MM (24-hour), got '$SORTTV_RUN_AT'"; exit 1 ;;
esac

# Stop promptly on `docker stop`, even mid-sleep.
trap 'echo "Stopping."; exit 0' TERM INT

echo "SortTV will run daily at $SORTTV_RUN_AT (${TZ:-UTC})."
while true; do
    now=$(date +%s)
    next=$(date -d "today $SORTTV_RUN_AT" +%s)
    if [ "$next" -le "$now" ]; then
        next=$(date -d "tomorrow $SORTTV_RUN_AT" +%s)
    fi
    echo "Next run: $(date -d "@$next" '+%Y-%m-%d %H:%M %Z')"
    sleep $((next - now)) &
    wait $!
    # a failed run is logged, and the schedule carries on
    python3 /app/sorttv.py "$@" || echo "SortTV exited with status $?"
done
