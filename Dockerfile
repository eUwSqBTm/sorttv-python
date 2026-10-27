# SortTV (Python port) container image
#
# Build:  docker build -t sorttv .
# Run:    see docker-compose.yml
#
# Debian (not Alpine) so that RAR archives can be unpacked: Alpine's 7-Zip is built without RAR support
# and Alpine has no unrar package.
FROM python:3.12-slim-bookworm

# unrar lives in Debian's non-free component; tzdata makes the TZ setting (and so the run time) work
RUN sed -i 's/^Components: main$/Components: main non-free/' /etc/apt/sources.list.d/debian.sources \
 && apt-get update \
 && apt-get install -y --no-install-recommends unrar unzip p7zip-full tini tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY sorttv.py /app/sorttv.py
# Sample config with container paths (/data/...) instead of /home/me/...
COPY sorttv.conf /app/sorttv.conf.sample
RUN sed -i \
      -e 's#/home/me/Downloads/Complete#/data/downloads#' \
      -e 's#/home/me/Videos/TV#/data/tv#' \
      -e 's#/home/me/Videos/Movies#/data/movies#' \
      -e 's#/home/me/Music#/data/music#' \
      -e 's#/home/me/Downloads/Other#/data/other#' \
      /app/sorttv.conf.sample
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod 755 /app/entrypoint.sh /app/sorttv.py && chmod 644 /app/sorttv.conf.sample

# /config holds sorttv.conf, the log file and the TVDB cache
# SORTTV_RUN_AT: sort once a day at this local time (HH:MM, uses TZ). Set it empty to run once and exit.
ENV SORTTV_CONFIG=/config/sorttv.conf \
    SORTTV_DATA_DIR=/config \
    SORTTV_RUN_AT=03:00 \
    TZ=America/Edmonton \
    PYTHONUNBUFFERED=1
VOLUME ["/config"]

ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]
# Options passed to every run
CMD ["--display-license=FALSE"]
