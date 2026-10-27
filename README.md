# SortTV: Python port

This is a Python 3 port of [SortTV](https://sourceforge.net/projects/sorttv/) 1.38 by Z. Cliffe Schreuders. SortTV sorts TV episodes, movies and music from a downloads folder into an organised library (`TV/Show/Season 1/Show - S01E01 - Title.avi`). It can also rename files, download artwork and tell Kodi/XBMC to update its library.

The port follows the Perl original closely: it has the same options, the same config file format, the same matching regexes and the same renaming rules. You can reuse your existing `sorttv.conf`; just add your API keys (see below).

## Requirements

- Python 3.8 or newer. Only the standard library is used, so there's nothing to `pip install`.
- Optional: `unrar`/`rar`, `unzip` or `7z` on your PATH, for extracting archives before sorting (same as the original).

## Quick start

1. Put `sorttv.py` and `sorttv.conf` in the same folder.
2. Edit `sorttv.conf` and set at least `directory-to-sort` and `tv-directory`.
3. Add your API keys if you want online lookups (next section).
4. Run `python3 sorttv.py`.

Command-line options override the config file, exactly as before:

```
python3 sorttv.py /home/me/Downloads /home/me/Videos/TV
python3 sorttv.py --directory-to-sort=/home/me/Downloads --tv-directory=/home/me/Videos/TV --dry-run
python3 sorttv.py --help
```

Everything in the original README still applies once you replace `perl sorttv.pl` with `python3 sorttv.py`. That includes cron and Task Scheduler setups.

## API keys (the one real change)

The Perl version relied on the old TheTVDB XML API and TMDb API v2 through CPAN modules. Both APIs have since been shut down, so those features no longer work in the original. The port uses the current APIs instead, and each needs a free key of your own:

| Setting | Used for | Get one at |
|---|---|---|
| `tvdb-api-key` (plus `tvdb-pin` if your key needs one) | Proper show titles, episode names (`[EP_NAME1]`), matching `Show - Episode Title.avi` or `Show 2010-06-16.avi`, show/season/episode images | https://thetvdb.com/api-information |
| `tmdb-api-key` (v3 "API Key" or v4 "Read Access Token") | Identifying and sorting movies, movie posters/fanart, `[RATING]` | https://www.themoviedb.org/settings/api |

You can set them in `sorttv.conf`, on the command line (`--tvdb-api-key=...`) or as the environment variables `TVDB_API_KEY`, `TVDB_PIN` and `TMDB_API_KEY`.

Without a TVDB key, TV sorting still works; the names just come from the file names, the same as the original's `--no-network` mode. Without a TMDb key, movies can't be identified, so they're treated as "other" files, the same as the original when a lookup fails. SortTV prints a warning at startup when a key is missing.

TVDB responses are cached for 12 hours in `.cache/` next to the script. That helps a lot in polling mode.

## Running in Docker

The folder includes a `Dockerfile` and `docker-compose.yml`. The image is based on Debian with Python 3.12 and includes `unrar`, `unzip` and `7z`, so archive extraction works (including RAR).

1. Edit `docker-compose.yml`:
   - Replace `/srv/media` with the host folder that contains your downloads and library.
   - Set `user:` to your UID:GID (run `id` on the host).
   - Check `TZ` and `SORTTV_RUN_AT` (see below).
2. Run `docker compose up -d --build`. On the first start the container creates `./config/sorttv.conf` from a sample and waits.
3. Edit `./config/sorttv.conf`:
   - Set the directories and add your API keys (you can also put the keys in `docker-compose.yml`).
   - Delete the file's first line (`# SORTTV_NOT_CONFIGURED`).
4. Run `docker compose restart`. Follow it with `docker compose logs -f sorttv`.

**When it runs:** the container sorts once a day at `SORTTV_RUN_AT` (default `03:00`), in the time zone set by `TZ` (default `America/Edmonton`). Daylight saving changes are handled. Between runs the container stays up and sleeps.
- **Change the time:** edit `SORTTV_RUN_AT` (24-hour `HH:MM`) and run `docker compose up -d`.
- **Sort right now:** run `docker compose exec sorttv python3 /app/sorttv.py --display-license=FALSE`.
- **Use an interval instead of a fixed time:** set `SORTTV_RUN_AT=` (empty) and `command: ["--poll-time=1h"]`.

Paths in `sorttv.conf` are paths inside the container. The sample expects `/data/downloads`, `/data/tv`, `/data/movies`, `/data/music` and `/data/other`, all under the one folder mounted at `/data`. Keeping everything under one mount means moves are instant renames, and `sort-by=PLACE-HARDLINK` works.

Some things are different inside a container:

- **Symlink modes:** `PLACE-SYMLINK`, `MOVE-AND-LEAVE-SYMLINK-BEHIND` and `duplicate-images=SYMLINK` create links that use container paths. The links only resolve on the host (or in Kodi) if you mount your media at the same path inside the container as on the host, e.g. `- /srv/media:/srv/media`, and use those paths in the config. `MOVE` (the default), `COPY` and `PLACE-HARDLINK` aren't affected.
- **Kodi on the same machine:** set `xbmc-remote-control=host.docker.internal` (the compose file already maps that name to the host).
- **Where the files go:** the log (`sorttv.log`) and TVDB cache (`.cache/`) are written to `./config`. Outside Docker, the `SORTTV_CONFIG` and `SORTTV_DATA_DIR` environment variables let you move them in the same way.

## Publishing the image on GitHub and running it on Unraid

`.github/workflows/docker.yml` runs the tests on every push to `main`. If they pass, it builds the image and publishes it as `ghcr.io/<your-github-username>/sorttv-python:latest`.

1. Push this repo to GitHub. The first push starts the build; it takes a few minutes and you can watch it on the repo's **Actions** tab.
2. Make the image public so Unraid can pull it without logging in: on your GitHub profile go to **Packages**, open **sorttv-python**, then **Package settings**, and set the visibility to **Public**.
3. Add it to Unraid using the template:
   - Copy `unraid/sorttv-python.xml` to `/boot/config/plugins/dockerMan/templates-user/my-sorttv-python.xml` on the server.
   - In the file, replace `YOUR-GITHUB-USERNAME` with your username in lowercase.
   - In Unraid, go to **Docker**, **Add Container**, and pick **sorttv-python** from the template list.
4. Check the paths, run time and time zone in the form, then hit **Apply**.
5. The first start creates `/mnt/user/appdata/sorttv/sorttv.conf`. Edit it, delete its first line, and restart the container.

To update later, push the change to GitHub, wait for the build to finish, then use **Check for Updates** in Unraid's Docker tab.

## How faithful is it?

I checked it with a differential test. The original `sorttv.pl` (with its network modules stubbed out) and `sorttv.py` were run on the same set of about 70 tricky file names under 35 different option combinations: every sort mode, directory treatment, rename format, list/size/age filter, dry run, config-file parsing and so on. The resulting folder trees were identical in every case.

The online features can't be compared that way, because the old APIs are gone. They are covered by `tests/test_sorttv.py` instead, which ports the scenarios from the original `sorttv-tests.pl` and runs them against a local mock of the TVDB and TMDb APIs:

```
python3 -m unittest discover -s tests -v
```

## Deliberate differences

Quirks of the original that affect which files get matched and where they go are kept on purpose. For example, `house.m.d.s08e01.avi` still becomes `house m d`. Use `show-name-substitute` for those cases, as before. What changed:

- **Online lookups** use TheTVDB v4 and TMDb v3 and need your own keys (see above). The old per-module workarounds are gone, including "no TV images on Windows" and the episode-number-over-49 hack.
- **Polling times:** `--poll-time=2days` and `3hrs` now mean what they say. The original checked for a trailing "s" first, so it read `2days` as 2 seconds.
- **Age filter while polling:** `sort-only-older-than-days` now measures age from the current time, not from when the script started. Before, a long-running poller would never sort files that arrived after it started.
- **Dry run** no longer extracts archives or removes empty folders in the to-sort directory.
- **Kodi notification:** the notifications are sent as valid JSON-RPC, and the list of new items is reset on each poll. Before, the same items were re-announced every cycle.
- **Non-ASCII file names** (`Café`, `東京`) are handled correctly. Perl read them as raw bytes and mangled accented characters.
- **Config lines containing apostrophes** (e.g. `It's Always Sunny`) now work. In Perl they broke the option parser.
- **Movie search** stops after 10 pages of TMDb results instead of walking every page.
- **`check-for-updates`** is accepted but does nothing, since it checked for new Perl releases.
- **Show name substitutes are final:** a name set with `show-name-substitute` is used exactly as written, and TheTVDB's title no longer replaces it. To keep online lookups working, pair it with a `tvdb-id-substitute` for the new name, e.g.
  ```
  show-name-substitute=WWE Raw-->WWE.Monday.Night.Raw
  show-name-substitute=WWE Monday Night Raw-->WWE.Monday.Night.Raw
  tvdb-id-substitute=WWE Monday Night Raw-->76779
  ```
  `tvdb-id-substitute` IDs are also now used for air-date/episode-title matching and artwork, not just show titles.
- **Aliases added:** `--polling-time` and `--xbmc-webserver`, the spellings the original README used, now work.

## License

GPL v3 or later, like the original. All credit for SortTV's design and matching logic goes to Z. Cliffe Schreuders and the contributors listed in `sorttv.py`.
