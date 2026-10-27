#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# SortTV (Python port)
#
# A port of SortTV 1.38 by Z. Cliffe Schreuders from Perl to Python 3.
# Original: https://sourceforge.net/projects/sorttv/
#
# Sorts TV show episodes, movies and music into an organised directory
# structure, e.g. TV/[show]/[season x]/[eps], optionally renaming them using
# information from TheTVDB and TMDb, downloading artwork, and notifying
# Kodi/XBMC.
#
# Original SortTV copyleft (ↄ) 2010-2015 Z. Cliffe Schreuders, with
# contributions from: salithus, schmoko, CoinTos, gardz, Patrick Cole,
# Martin Guillon (farfromrefug), red_five, Fox, TechLife, frozenesper,
# deranjer, iamwudu, Nicolas Leclercq, Justin Metheny.
#
# This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
# Requires only the Python 3.8+ standard library.

import errno
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

try:
    import fcntl  # POSIX only; used to stop two copies running at once
except ImportError:  # pragma: no cover - Windows
    fcntl = None

VERSION = "1.38-py1"
IS_WINDOWS = sys.platform.startswith("win")
SCRIPT_PATH = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
# Where the default config file lives, and where the .cache dir and default log go.
# Both default to the script's own folder; the Docker image points them at /config.
CONFIG_FILE = os.environ.get("SORTTV_CONFIG", SCRIPT_PATH + "/sorttv.conf")
DATA_DIR = os.environ.get("SORTTV_DATA_DIR", SCRIPT_PATH).rstrip("/")

TVDB_API_URL = os.environ.get("SORTTV_TVDB_URL", "https://api4.thetvdb.com/v4")
TVDB_ARTWORK_URL = "https://artworks.thetvdb.com"
TMDB_API_URL = os.environ.get("SORTTV_TMDB_URL", "https://api.themoviedb.org/3")
TMDB_IMAGE_URL = os.environ.get("SORTTV_TMDB_IMG_URL", "https://image.tmdb.org/t/p/original")
HTTP_TIMEOUT = 20
USER_AGENT = "SortTV-Python/%s" % VERSION

MUSIC_EXT = ["aac", "aif", "iff", "m3u", "mid", "midi", "mp3", "mpa", "ra", "ram", "wave", "wav", "wma",
             "ogg", "oga", "ogx", "spx", "flac", "m4a", "pls"]
VIDEO_EXT = [
    "avi", "mpg", "mpe", "mpeg-1", "mpeg-2", "m4v", "mkv", "mov", "mp4", "mpeg", "ogm", "wmv", "divx", "dvr-ms",
    "3gp", "m1s", "mpa", "mp2", "m2a", "mp2v", "m2v", "m2s", "qt", "asf", "asx", "wmx", "rm", "ram", "rmvb", "3g2",
    "flv", "swf", "aepx", "ale", "avp", "avs", "bdm", "bik", "bin", "bsf", "camproj", "cpi", "dat", "dmsm", "dream",
    "dvdmedia", "dzm", "dzp", "edl", "f4v", "fbr", "fcproject", "hdmov", "imovieproj", "ism", "ismv", "m2p", "mod",
    "moi", "mts", "mxf", "ogv", "pds", "prproj", "psh", "r3d", "rcproject", "scm", "smil", "sqz", "stx", "swi",
    "tix", "trp", "ts", "veg", "vf", "vro", "webm", "wlmp", "wtv", "xvid", "yuv", "3gp2", "3gpp", "3p2", "aaf",
    "aep", "aetx", "ajp", "amc", "amv", "amx", "arcut", "arf", "avb", "axm", "bdmv", "bdt3", "bmk", "camrec", "cine",
    "clpi", "cmmp", "cmmtpl", "cmproj", "cmrec", "cst", "d2v", "d3v", "dce", "dck", "dcr", "dcr", "dir", "dmb",
    "dmsd", "dmsd3d", "dmss", "dpa", "dpg", "dv", "dv-avi", "dvr", "dvx", "dxr", "dzt", "evo", "eye", "f4p", "fbz",
    "fcp", "flc", "flh", "fli", "gfp", "gts", "hkm", "ifo", "imovieproject", "ircp", "ismc", "ivf", "ivr", "izz",
    "izzy", "jts", "jtv", "m1pg", "m21", "m21", "m2t",
    "m2ts", "m2v", "mgv", "mj2", "mjp", "mk3d", "mnv", "mp21", "mp21", "mpgindex", "mpl", "mpls", "mpv", "mqv",
    "msdvd", "mse", "mswmm", "mtv", "mvd", "mve", "mvp", "mvp", "mvy", "ncor", "nsv", "nuv", "nvc", "ogx", "pgi",
    "photoshow", "piv", "plproj", "pmf", "ppj", "prel", "pro", "prtl", "pxv", "qtl", "qtz", "rcd", "rdb", "rec",
    "rmd", "rmp", "rms", "roq", "rsx", "rum", "rv", "rvl", "sbk", "scc", "screenflow", "seq", "sfvidcap", "siv",
    "smi", "smk", "stl", "svi", "swt", "tda3mt", "tivo", "tod", "tp", "tp0", "tpd", "tpr", "tsp", "tvs", "usm",
    "vc1", "vcpf", "vcv", "vdo", "vdr", "vep", "vfz", "vgz", "viewlet", "vlab", "vp6", "vp7", "vpj", "vsp", "wcp",
    "wmd", "wmmp", "wmx", "wp3", "wpl", "wvx", "xej", "xel", "xesc", "xfl", "xlmv", "zm1", "zm2", "zm3", "zmv"]
SUBTITLE_EXT = ["ssa", "srt", "sub"]
IMAGE_EXT = ["jpg", "jpeg", "tbn"]

# TheTVDB v4 uses ISO 639-2 (three letter) language codes; SortTV config uses two letter codes
LANG_2_TO_3 = {
    "en": "eng", "it": "ita", "zh": "zho", "es": "spa", "hu": "hun", "nl": "nld", "pl": "pol", "sl": "slv",
    "da": "dan", "de": "deu", "el": "ell", "he": "heb", "sv": "swe", "fi": "fin", "no": "nor", "fr": "fra",
    "ru": "rus", "cs": "ces", "ja": "jpn", "hr": "hrv", "tr": "tur", "ko": "kor", "pt": "por",
}
LANG_3_TO_2 = dict((v, k) for k, v in LANG_2_TO_3.items())

# Regex building blocks shared by the TV and movie matchers (identical to the Perl originals)
DASHSPACE_RE = r"(?:\.|\s|-|_)"
URLATSTART_RE = r"(?:^\[\swww\.\w*\.\w*\s\]" + DASHSPACE_RE + r"*)"
# NB: in the Perl source this was a single-quoted string, so '\\|-' became the regex '\|-' (a literal "|-").
# Kept byte-for-byte so that matching behaves exactly as it did in the original.
SPACESLASHDASH_OR_FIRSTCAPTURED_RE = r"(?:\.|\s|\/|\|-|\1)"
MOVIE_TAGS_RE = r"BDRip|\[Eng\]|DVDRip|DVD|Bluray|XVID|XvidHD|DIVX|720|1080|HQ|ITA|AC3|x264|x265|R5"


# ---------------------------------------------------------------------------
# Small string helpers (direct equivalents of the Perl subs of the same name)
# ---------------------------------------------------------------------------

def remdot(title):
    """Replace dots/underscores/dashes and unicode spacing with spaces, strip punctuation and symbols."""
    chars = []
    for c in title:
        cat = unicodedata.category(c)
        if cat[0] in ("Z", "M") or c in "._-":
            chars.append(" ")
        else:
            chars.append(c)
    title = "".join(c for c in chars if unicodedata.category(c)[0] not in ("P", "S", "C"))
    title = re.sub(r"\s+", " ", title)
    title = re.sub(r"\s$", "", title)
    title = re.sub(r"^\s", "", title)
    return title


def cleanup_filename(title):
    """Removes slashes for creating files."""
    title = re.sub(r"\\|/", "-", title)
    title = re.sub(r"\s\s", " ", title)
    title = re.sub(r"\s$", "", title)
    title = re.sub(r"^\s", "", title)
    return title


def first_letter(title):
    """The upper case first letter of the title, or "#" if it starts with something other than a letter."""
    return title[0].upper() if title and title[0].isalpha() else "#"


def filename(path):
    """Removes the path."""
    return path.rsplit("/", 1)[-1]


def filename_without_ext(path):
    """Removes path and extension."""
    name = filename(path)
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return name


def path_of(path):
    """Removes the filename (returns the directory with a trailing slash, or '')."""
    m = re.match(r"(.*)(?:/|\\)(.*)", path)
    if m:
        return m.group(1) + "/"
    return ""


def glob2pat(globstr):
    """Turns a simple shell wildcard pattern into a regex (from the Perl Cookbook)."""
    patmap = {"*": ".*", "?": ".", "[": "[", "]": "]"}
    return "^" + "".join(patmap.get(c, re.escape(c)) for c in globstr) + "$"


def matches_type(name, extensions):
    """Whether the file name ends in one of the extensions (case sensitive, as in the original)."""
    for ext in extensions:
        if name.endswith(ext):
            return True
    return False


def list_dir(directory):
    """Equivalent of bsd_glob("$dir*"): non-hidden entries, full paths, sorted."""
    if not directory:
        return []
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    names = [n for n in names if not n.startswith(".")]
    names.sort(key=lambda n: (n.lower(), n))
    return [directory + n for n in names]


def to_number(value):
    """Perl-style numification of a string like '345', '1.5' or '1.05 '."""
    m = re.match(r"\s*([+-]?(?:\d+\.?\d*|\.\d+))", str(value))
    return float(m.group(1)) if m else 0.0


def is_true(value):
    return str(value).upper() == "TRUE"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class HTTPError(Exception):
    def __init__(self, status, message):
        Exception.__init__(self, message)
        self.status = status


def http_request(url, params=None, headers=None, data=None, timeout=HTTP_TIMEOUT):
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    hdrs = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise HTTPError(e.code, "HTTP %s for %s" % (e.code, url.split("?")[0]))
    except (urllib.error.URLError, socket.timeout, OSError) as e:
        raise HTTPError(0, "network error for %s: %s" % (url.split("?")[0], e))


def http_get_json(url, params=None, headers=None):
    return json.loads(http_request(url, params=params, headers=headers).decode("utf-8"))


def download_file(url, dest, tries=2):
    """Download url to dest, retrying once; returns True on success."""
    for _ in range(tries):
        try:
            content = http_request(url, headers={"Accept": "*/*"})
            with open(dest, "wb") as fh:
                fh.write(content)
            return True
        except (HTTPError, OSError):
            continue
    return False


# ---------------------------------------------------------------------------
# TheTVDB v4 client (replaces the Perl TVDB::API module, whose API was retired)
# ---------------------------------------------------------------------------

class TVDB(object):
    CACHE_TTL = 12 * 3600

    def __init__(self, apikey, pin, language, cache_dir, fixtitle):
        self.apikey = apikey
        self.pin = pin
        self.lang3 = LANG_2_TO_3.get(language, language if len(language) == 3 else "eng")
        self.cache_dir = cache_dir
        self.fixtitle = fixtitle
        self.token = None
        self.memo = {}
        self._artwork_types = None

    # -- transport --
    def _login(self):
        token_file = os.path.join(self.cache_dir, "tvdb_token.json")
        try:
            with open(token_file) as fh:
                saved = json.load(fh)
            if saved.get("apikey_hash") == self._key_hash() and saved.get("expires", 0) > time.time():
                self.token = saved["token"]
                return
        except (OSError, ValueError, KeyError):
            pass
        payload = {"apikey": self.apikey}
        if self.pin:
            payload["pin"] = self.pin
        result = json.loads(http_request(TVDB_API_URL + "/login", data=payload).decode("utf-8"))
        self.token = result["data"]["token"]
        try:
            with open(token_file, "w") as fh:
                # tokens are valid for a month; refresh well before that
                json.dump({"token": self.token, "expires": time.time() + 25 * 86400,
                           "apikey_hash": self._key_hash()}, fh)
        except OSError:
            pass

    def _key_hash(self):
        return hashlib.sha1(self.apikey.encode("utf-8")).hexdigest()

    def get(self, path, params=None):
        """GET an API path, using a small on-disk cache. Returns the 'data' member."""
        key = path + "?" + urllib.parse.urlencode(sorted((params or {}).items()))
        if key in self.memo:
            return self.memo[key]
        cache_file = os.path.join(self.cache_dir, "tvdb_" + hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json")
        try:
            if time.time() - os.path.getmtime(cache_file) < self.CACHE_TTL:
                with open(cache_file, encoding="utf-8") as fh:
                    result = json.load(fh)
                self.memo[key] = result
                return result
        except (OSError, ValueError):
            pass
        if not self.token:
            self._login()
        try:
            result = http_get_json(TVDB_API_URL + path, params, {"Authorization": "Bearer " + self.token})
        except HTTPError as e:
            if e.status != 401:
                raise
            self.token = None
            try:
                os.remove(os.path.join(self.cache_dir, "tvdb_token.json"))
            except OSError:
                pass
            self._login()
            result = http_get_json(TVDB_API_URL + path, params, {"Authorization": "Bearer " + self.token})
        self.memo[key] = result
        try:
            with open(cache_file, "w", encoding="utf-8") as fh:
                json.dump(result, fh)
        except OSError:
            pass
        return result

    def _safe_get(self, path, params=None):
        try:
            return self.get(path, params)
        except HTTPError as e:
            if e.status in (400, 404):
                return None
            raise

    # -- series --
    def series_id(self, name_or_id):
        """Returns the TVDB series id for a show name (or numeric id), or None."""
        name_or_id = str(name_or_id)
        if re.match(r"^[+-]?\d+$", name_or_id):
            return int(name_or_id)
        memo_key = ("sid", name_or_id.lower())
        if memo_key in self.memo:
            return self.memo[memo_key]
        result = self._safe_get("/search", {"query": name_or_id, "type": "series"})
        sid = None
        results = (result or {}).get("data") or []
        wanted = self.fixtitle(name_or_id).lower()
        for item in results:
            names = [item.get("name") or ""]
            names += list((item.get("translations") or {}).values())
            names += item.get("aliases") or []
            if any(n and self.fixtitle(n).lower() == wanted for n in names):
                sid = item.get("tvdb_id") or item.get("id")
                break
        if sid is None and results:
            sid = results[0].get("tvdb_id") or results[0].get("id")
        if sid is not None:
            sid = int(re.sub(r"\D", "", str(sid)))
        self.memo[memo_key] = sid
        return sid

    def series_name_by_id(self, sid):
        """The series title in the configured language (falls back to the primary title)."""
        translation = self._safe_get("/series/%s/translations/%s" % (sid, self.lang3))
        if translation and (translation.get("data") or {}).get("name"):
            return translation["data"]["name"]
        base = self._safe_get("/series/%s" % sid)
        if base and (base.get("data") or {}).get("name"):
            return base["data"]["name"]
        return None

    def series_name(self, name_or_id):
        sid = self.series_id(name_or_id)
        if sid is None:
            return None
        return self.series_name_by_id(sid)

    # -- episodes --
    def episodes(self, sid):
        """All episodes (default/aired order) with names in the configured language where available."""
        memo_key = ("eps", sid)
        if memo_key in self.memo:
            return self.memo[memo_key]

        def fetch(path):
            eps = []
            for page in range(0, 100):
                result = self._safe_get(path, {"page": page})
                if not result:
                    break
                batch = (result.get("data") or {}).get("episodes") or []
                eps.extend(batch)
                links = result.get("links") or {}
                if not batch or not links.get("next"):
                    break
            return eps

        eps = fetch("/series/%s/episodes/default/%s" % (sid, self.lang3))
        base = fetch("/series/%s/episodes/default" % sid) if (not eps or any(not e.get("name") for e in eps)) else []
        if not eps:
            eps = base
        elif base:
            base_names = dict((e.get("id"), e.get("name")) for e in base)
            for e in eps:
                if not e.get("name"):
                    e["name"] = base_names.get(e.get("id"))
        self.memo[memo_key] = eps
        return eps

    def episode(self, name_or_id, season, number):
        sid = self.series_id(name_or_id)
        if sid is None:
            return None
        for e in self.episodes(sid):
            if e.get("seasonNumber") is not None and e.get("number") is not None \
                    and int(e["seasonNumber"]) == int(season) and int(e["number"]) == int(number):
                return e
        return None

    def episode_name(self, name_or_id, season, number):
        e = self.episode(name_or_id, season, number)
        return e.get("name") if e else None

    def episode_by_airdate(self, name_or_id, airdate):
        sid = self.series_id(name_or_id)
        if sid is None:
            return None
        for e in self.episodes(sid):
            if e.get("aired") == airdate and e.get("seasonNumber"):
                return e
        return None

    def episode_by_title(self, name_or_id, fixed_title):
        """Finds an episode whose fixtitle()'d name equals fixed_title (specials/season 0 ignored, as before)."""
        sid = self.series_id(name_or_id)
        if sid is None:
            return None
        for e in sorted(self.episodes(sid), key=lambda x: (x.get("seasonNumber") or 0, x.get("number") or 0)):
            if not e.get("seasonNumber") or not e.get("name"):
                continue
            if self.fixtitle(e["name"]) == fixed_title:
                return e
        return None

    # -- artwork --
    def artwork_type_ids(self):
        if self._artwork_types is None:
            types = {("series", "banner"): 1, ("series", "poster"): 2, ("series", "background"): 3,
                     ("season", "banner"): 6, ("season", "poster"): 7}
            try:
                result = self._safe_get("/artwork/types")
                for t in (result or {}).get("data") or []:
                    record, name = (t.get("recordType") or "").lower(), (t.get("name") or "").lower()
                    if (record, name) in types:
                        types[(record, name)] = t.get("id")
            except HTTPError:
                pass
            self._artwork_types = types
        return self._artwork_types

    def _best_artwork(self, artworks, type_id):
        candidates = [a for a in artworks or [] if a.get("type") == type_id and a.get("image")]
        if not candidates:
            return None
        preferred = [a for a in candidates if a.get("language") == self.lang3] or \
                    [a for a in candidates if not a.get("language")] or candidates
        preferred.sort(key=lambda a: a.get("score") or 0, reverse=True)
        return self.full_image_url(preferred[0]["image"])

    @staticmethod
    def full_image_url(image):
        if not image:
            return None
        if image.startswith("http"):
            return image
        if not image.startswith("/"):
            image = "/banners/" + image
        return TVDB_ARTWORK_URL + image

    def series_extended(self, name_or_id):
        sid = self.series_id(name_or_id)
        if sid is None:
            return None
        result = self._safe_get("/series/%s/extended" % sid)
        return (result or {}).get("data")

    def series_images(self, name_or_id):
        """Returns (poster_url, fanart_url, banner_url)."""
        ext = self.series_extended(name_or_id)
        if not ext:
            return None, None, None
        types = self.artwork_type_ids()
        arts = ext.get("artworks") or []
        poster = self._best_artwork(arts, types[("series", "poster")]) or self.full_image_url(ext.get("image"))
        fanart = self._best_artwork(arts, types[("series", "background")])
        banner = self._best_artwork(arts, types[("series", "banner")])
        return poster, fanart, banner

    def season_images(self, name_or_id, season):
        """Returns (season_poster_url, season_wide_banner_url)."""
        ext = self.series_extended(name_or_id)
        if not ext:
            return None, None
        types = self.artwork_type_ids()
        season_rec = None
        for s in ext.get("seasons") or []:
            stype = (s.get("type") or {}).get("type")
            if s.get("number") is not None and int(s["number"]) == int(season) and stype in (None, "official", "default"):
                season_rec = s
                break
        if not season_rec:
            return None, None
        poster = banner = None
        detail = self._safe_get("/seasons/%s/extended" % season_rec.get("id"))
        arts = ((detail or {}).get("data") or {}).get("artwork") or []
        poster = self._best_artwork(arts, types[("season", "poster")]) or self.full_image_url(season_rec.get("image"))
        banner = self._best_artwork(arts, types[("season", "banner")])
        return poster, banner

    def episode_image(self, name_or_id, season, number):
        e = self.episode(name_or_id, season, number)
        return self.full_image_url(e.get("image")) if e else None


# ---------------------------------------------------------------------------
# TMDb v3 client (replaces the Perl WWW::TheMovieDB module)
# ---------------------------------------------------------------------------

class TMDB(object):
    def __init__(self, key, language):
        self.key = key
        if len(language) == 3:
            language = LANG_3_TO_2.get(language, "en")
        self.language = language

    def _get(self, path, params):
        params = dict(params)
        headers = {}
        if self.key.startswith("eyJ"):  # a v4 "API read access token"
            headers["Authorization"] = "Bearer " + self.key
        else:
            params["api_key"] = self.key
        return http_get_json(TMDB_API_URL + path, params, headers)

    def search_movie(self, query, page=1):
        return self._get("/search/movie", {"query": query, "page": page, "language": self.language,
                                           "include_adult": "false"})

    def us_certification(self, movie_id):
        result = self._get("/movie/%s/release_dates" % movie_id, {})
        for country in result.get("results") or []:
            if country.get("iso_3166_1") == "US":
                for rel in country.get("release_dates") or []:
                    if rel.get("certification"):
                        return rel["certification"]
                return ""
        return None


# ---------------------------------------------------------------------------
# The sorter
# ---------------------------------------------------------------------------

class SortTV(object):

    def __init__(self):
        # Global config variables (same names/defaults as the Perl version)
        self.help = self.man = False
        self.sortdir = self.tvdir = self.miscdir = self.musicdir = self.moviedir = None
        self.matchtype = None
        self.xbmcoldwebserver = self.xbmcaddress = None
        self.xbmcport = 9090
        self.newshows = ""
        self.new = ""
        self.log = None
        self.musicext = list(MUSIC_EXT)
        self.whitelist, self.blacklist, self.deletelist, self.sizerange = [], [], [], []
        self.filestosort, self.nonmediaext = [], []
        self.showrenames, self.showtvdbids = {}, {}
        self.checkforupdates = self.windowsnames = self.tvdbrename = self.lookupseasonep = "TRUE"
        self.extractrar = self.useseasondirs = self.displaylicense = self.useextensions = "TRUE"
        self.usedots = self.rename = self.seasondoubledigit = self.removesymlinks = "FALSE"
        self.needshowexist = self.flattennonepisodefiles = self.tvdbrequired = self.sort_movie_dir = "FALSE"
        self.dryrun = ""
        self.seasontitle = "Season "
        self.sortby = "MOVE"
        self.duplicateimages = "SYMLINK"
        self.sortolderthandays = self.poll = 0
        self.verbose = False
        self.ifexists = "SKIP"
        self.renameformat = "[SHOW_NAME] - [EP1][EP_NAME1]"
        self.movierenameformat = "[MOVIE_TITLE] [YEAR2]/[MOVIE_TITLE] [YEAR1]"
        self.fetchmovieimages = "TRUE"
        self.treatdir = "RECURSIVELY_SORT_CONTENTS"
        self.fetchimages = "NEW_SHOWS"
        self.imagesformat = "POSTER"
        self.logfile = DATA_DIR + "/sorttv.log"
        self.tvdblanguage = "en"
        self.movielanguage = "en"
        self.tvdbapikey = os.environ.get("TVDB_API_KEY", "")
        self.tvdbpin = os.environ.get("TVDB_PIN", "")
        self.tmdbapikey = os.environ.get("TMDB_API_KEY", "")
        self.tvdb = None
        self.tmdb = None
        self.yeartoleranceforerror = 1
        self.dir_perms = None
        self.lockhandle = None
        self.positional = []
        # current episode being sorted
        self.showname = self.year = self.series = self.episode = self.pureshowname = ""
        self.optionlist = self._build_options()

    # -----------------------------------------------------------------------
    # Option handling (replaces Getopt::Long)
    # -----------------------------------------------------------------------

    def _build_options(self):
        def setter(attr):
            return lambda v: setattr(self, attr, v)

        def appender(lst):
            return lambda v: lst.append(v)

        spec = [
            ("misc-dir|non-episode-dir|misc", "s", lambda v: self.set_directory(v, "miscdir")),
            ("xbmc-old-web-server|xbmc-web-server|xbmc-webserver|xo", "s", setter("xbmcoldwebserver")),
            ("xbmc-remote-control|xr", "s", setter("xbmcaddress")),
            ("xbmc-remote-control-port|xrp", "i", setter("xbmcport")),
            ("match-type|ms", "s", setter("matchtype")),
            ("flatten-non-eps|fne", "s", setter("flattennonepisodefiles")),
            ("check-for-updates|up", "s", setter("checkforupdates")),
            ("treat-directories|td", "s", setter("treatdir")),
            ("consider-media-file-extensions|ext", "s", setter("useextensions")),
            ("if-file-exists|e", "s", setter("ifexists")),
            ("extract-compressed-before-sorting|rar", "s", setter("extractrar")),
            ("show-name-substitute", "s", self._opt_show_name_substitute),
            ("whitelist|white", "s", lambda v: self.whitelist.append(glob2pat(v))),
            ("blacklist|black|ignore", "s", lambda v: self.blacklist.append(glob2pat(v))),
            ("deletelist|delete", "s", lambda v: self.deletelist.append(glob2pat(v))),
            ("tvdb-id-substitute|tis", "s", self._opt_tvdb_id_substitute),
            ("tvdb-episode-name-required|nreq", "s", setter("tvdbrequired")),
            ("display-license|dl", "s", setter("displaylicense")),
            ("log-file|o", "s", setter("logfile")),
            ("fetch-show-title|fst", "s", setter("tvdbrename")),
            ("rename-media|rename-episodes|rn", "s", setter("rename")),
            ("tv-lookup-language|lookup-language|lang", "s", setter("tvdblanguage")),
            ("movie-lookup-language|lang", "s", setter("movielanguage")),
            ("fetch-tv-images|fetch-images|fi", "s", setter("fetchimages")),
            ("fetch-movie-images|fmi", "s", setter("fetchmovieimages")),
            ("images-format|im", "s", setter("imagesformat")),
            ("duplicate-images|csi", "s", setter("duplicateimages")),
            ("require-show-directories-already-exist|rs", "s", setter("needshowexist")),
            ("force-windows-compatible-filenames|fw", "s", setter("windowsnames")),
            ("rename-tv-format|rename-format|rf", "s", setter("renameformat")),
            ("rename-movie-format|rf", "s", setter("movierenameformat")),
            ("remove-symlinks|rs", "s", setter("removesymlinks")),
            ("use-dots-instead-of-spaces|dots", "s", setter("usedots")),
            ("sort-by|by", "s", setter("sortby")),
            ("sort-only-older-than-days|age", "i", setter("sortolderthandays")),
            ("year-tolerance-for-error|yerr", "i", setter("yeartoleranceforerror")),
            ("poll-time|polling-time|poll", "s", self._opt_poll_time),
            ("season-double-digits|sd", "s", setter("seasondoubledigit")),
            ("match-files-based-on-tvdb-lookups|tlookup", "s", setter("lookupseasonep")),
            ("use-season-directories|sd", "s", setter("useseasondirs")),
            ("season-title|st", "s", setter("seasontitle")),
            ("verbose|v", "flag", setter("verbose")),
            ("dry-run|n", "flag", self._opt_dry_run),
            ("filesize-range|fsrange", "s", self._opt_filesize_range),
            ("no-network|nn", "flag", self._opt_no_network),
            ("read-config-file|conf", "s", lambda v: self.get_config_from_file(v)),
            ("file-to-sort|file", "s", self._opt_file_to_sort),
            ("directory-to-sort|sort", "s", lambda v: self.set_directory(v, "sortdir")),
            ("tv-directory|directory-to-sort-into|tvdir", "s", self._opt_tv_directory),
            ("movie-directory|movie", "s", lambda v: self.set_directory(v, "moviedir")),
            ("sort-movie-directories|mdsort", "s", setter("sort_movie_dir")),
            ("movie-language|mlang", "s", setter("movielanguage")),
            ("music-directory|music", "s", lambda v: self.set_directory(v, "musicdir")),
            ("music-extension|me", "s", appender(self.musicext)),
            ("non-media-extension|nm", "s", appender(self.nonmediaext)),
            ("dir-permissions|dp", "s", setter("dir_perms")),
            # new in the Python port: API credentials for the current TheTVDB / TMDb APIs
            ("tvdb-api-key|tvdbkey", "s", setter("tvdbapikey")),
            ("tvdb-pin", "s", setter("tvdbpin")),
            ("tmdb-api-key|tmdbkey", "s", setter("tmdbapikey")),
            ("h|help|?", "flag", setter("help")),
            ("man", "flag", setter("man")),
        ]
        options = {}
        for names, kind, handler in spec:
            canonical = names.split("|")[0]
            for name in names.split("|"):
                # as with Getopt::Long, a later duplicate alias replaces an earlier one
                options[name.lower()] = (canonical, kind, handler)
        return options

    def _lookup_option(self, name):
        name = name.lower()
        if name in self.optionlist:
            return self.optionlist[name]
        # Getopt::Long style unique abbreviations
        matches = dict((opt[0], opt) for key, opt in self.optionlist.items() if key.startswith(name))
        if len(matches) == 1:
            return list(matches.values())[0]
        if len(matches) > 1:
            self.out("warn", "Option %s is ambiguous (%s)\n" % (name, ", ".join(sorted(matches))))
        return None

    def get_options(self, args):
        """Processes a list of arguments; returns the arguments that are not options."""
        rest = []
        i = 0
        while i < len(args):
            arg = args[i]
            i += 1
            if arg == "--":
                rest.extend(args[i:])
                break
            if not arg.startswith("-") or arg == "-":
                rest.append(arg)
                continue
            body = arg.lstrip("-")
            if "=" in body:
                name, value = body.split("=", 1)
                has_value = True
            else:
                name, value, has_value = body, None, False
            opt = self._lookup_option(name)
            if opt is None:
                self.out("warn", "Unknown option: %s\n" % name)
                continue
            canonical, kind, handler = opt
            if kind == "flag":
                handler(not (has_value and value.upper() in ("FALSE", "0", "")))
                continue
            if not has_value:
                if i < len(args):
                    value = args[i]
                    i += 1
                else:
                    self.out("warn", "Option %s requires an argument\n" % name)
                    continue
            if kind == "i":
                if not re.match(r"^[+-]?\d+$", value.strip()):
                    self.out("warn", 'Value "%s" invalid for option %s (number expected)\n' % (value, name))
                    continue
                value = int(value)
            handler(value)
        return rest

    # option callbacks -----------------------------------------------------

    def _opt_show_name_substitute(self, value):
        m = re.match(r"(.*)-->(.*)", value)
        if m:
            self.showrenames[self.fixtitle(m.group(1))] = m.group(2)

    def _opt_tvdb_id_substitute(self, value):
        m = re.match(r"(.*)-->(.*)", value)
        if m:
            self.showtvdbids[self.fixtitle(m.group(1))] = m.group(2)

    def _opt_poll_time(self, ptime):
        # convert times to seconds
        for pattern, mult in ((r"^(.*)(?:secs?|s)$", 1), (r"^(.*)(?:mins?|m)$", 60),
                              (r"^(.*)(?:hrs?|hours?|h)$", 3600), (r"^(.*)(?:days?|d)$", 86400)):
            m = re.match(pattern, ptime)
            if m:
                self.poll = to_number(m.group(1)) * mult
                return
        m = re.search(r"(\d+)", ptime)
        if m:
            self.out("warn", "WARN: interpreting %s as %s seconds\n" % (ptime, m.group(1)))
            self.poll = int(m.group(1))
        else:
            self.out("warn", "WARN: invalid poll time: %s. Must be secs, hrs, days etc.\n" % ptime)
            self.poll = 0

    def _opt_dry_run(self, value):
        if value:
            self.dryrun = "DRYRUN "
            self.out("std", "DRY RUN MODE: No file operations will occur on the to-sort directory, "
                            "some directories may be created at the destination.\n")

    def _opt_filesize_range(self, value):
        m = re.match(r"(.*)-(.*)", value)
        if not m:
            self.out("warn", "WARN: invalid filesize range format. Must be 125MB-350MB, etc. Received: %s\n" % value)
            return
        sizes = []
        for size in (m.group(1), m.group(2)):
            size = size.replace("MB", "", 1)
            g = re.match(r"(.*)GB", size)
            sizes.append(to_number(g.group(1)) * 1024 if g else to_number(size))
        self.sizerange.append((sizes[0], sizes[1]))

    def _opt_no_network(self, value):
        if not value:
            return
        self.out("verbose", "INFO: Disabling all network enabled features\n")
        self.xbmcoldwebserver = self.xbmcaddress = self.moviedir = ""
        self.tvdbrename = self.fetchimages = self.lookupseasonep = self.checkforupdates = "FALSE"
        self.renameformat = re.sub(r"\[EP_NAME\d\]", "", self.renameformat, count=1)

    def _opt_file_to_sort(self, value):
        if os.access(value, os.R_OK):
            self.filestosort.append(value)
        else:
            self.out("warn", "WARN: file %s does not exist\n" % value)
        self.out("verbose", "@filestosort: %s\n" % " ".join(self.filestosort))

    def _opt_tv_directory(self, value):
        if value == "KEEP_IN_SAME_DIRECTORIES":
            self.out("std", "INFO: disabling everything except tv sorts within the same directory\n")
            self.miscdir = self.musicdir = self.moviedir = ""
            self.tvdir = "KEEP_IN_SAME_DIRECTORIES"
        else:
            self.set_directory(value, "tvdir")

    # -----------------------------------------------------------------------
    # Main
    # -----------------------------------------------------------------------

    def main(self, argv):
        self.out("std", "SortTV\n", "~" * 6, "\n")

        # ensure only one copy running at a time
        if fcntl is not None:
            try:
                self.lockhandle = open(os.path.abspath(__file__), "r")
                fcntl.flock(self.lockhandle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError) as e:
                if e.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
                    sys.stderr.write("SortTV is already running, exiting.\n")
                    sys.exit(1)

        self.get_config_from_file(CONFIG_FILE)

        # command line options override the config file
        self.process_args(argv)

        if self.displaylicense == "TRUE":
            self.display_license()

        if self.help or self.man:
            self.showhelp()

        # ensure at least one input and one output
        if (self.sortdir is None and not self.filestosort) or \
                (self.tvdir is None and self.moviedir is None and self.musicdir is None and self.miscdir is None):
            self.out("warn", "Incorrect usage or configuration (missing sort or sort-to directories)\n")
            self.out("warn", "run 'python3 sorttv.py --help' for more information about how to use SortTV\n")
            sys.exit(0)

        # if uses thetvdb, set it up
        if re.search(r"\[EP_NAME\d\]", self.renameformat, re.I) or self.fetchimages != "FALSE" \
                or self.lookupseasonep != "FALSE" or self.tvdbrename == "TRUE":
            if self.tvdbapikey:
                cache_dir = DATA_DIR + "/.cache"
                if not os.path.exists(cache_dir):
                    try:
                        os.mkdir(cache_dir)
                    except OSError as e:
                        self.out("warn", "WARN: Could not create cache dir: %s %s\n" % (cache_dir, e))
                        sys.exit(1)
                self.tvdb = TVDB(self.tvdbapikey, self.tvdbpin, self.tvdblanguage, cache_dir, self.fixtitle)
            elif self.tvdir:
                self.out("warn", "WARN: no tvdb-api-key configured, so thetvdb.com lookups (show titles, episode "
                                 "names, images) are disabled. Get a key at https://thetvdb.com/api-information\n")

        # if uses moviedb, set it up
        if self.moviedir:
            if self.tmdbapikey:
                self.tmdb = TMDB(self.tmdbapikey, self.movielanguage)
            else:
                self.out("warn", "WARN: no tmdb-api-key configured, so movies cannot be identified and will not be "
                                 "sorted. Get a key at https://www.themoviedb.org/settings/api\n")

        if self.logfile:
            try:
                self.log = open(self.logfile, "a", encoding="utf-8")
            except OSError as e:
                self.out("warn", "WARN: Could not open log file %s: %s\n" % (self.logfile, e))
        self.display_sortdirs()
        if self.poll:
            self.out("std", "Polling every %s seconds...\n" % self.poll)

        while True:
            self.display_time()
            self.newshows = ""
            self.sort_directory(self.sortdir, self.filestosort)

            if self.xbmcoldwebserver and self.newshows:
                time.sleep(4)
                # update xbmc video library
                self.xbmc_old_get("ExecBuiltIn(updatelibrary(video))")
                # notification of update
                self.xbmc_old_get("ExecBuiltIn(Notification(,NEW EPISODES NOW AVAILABLE TO WATCH\n%s, 7000))"
                                  % self.newshows)
            if self.xbmcaddress and self.newshows:
                self.update_xbmc()

            if not self.poll:
                break
            time.sleep(self.poll)

        if self.log:
            self.log.close()

    def xbmc_old_get(self, command):
        url = "http://%s/xbmcCmds/xbmcHttp?command=%s" % (self.xbmcoldwebserver, urllib.parse.quote(command, safe="(),"))
        try:
            return http_request(url, timeout=HTTP_TIMEOUT)
        except HTTPError:
            return None

    def update_xbmc(self):
        """Tell Kodi/XBMC (JSON-RPC over TCP) to scan the library and show a notification."""
        messages = [
            {"jsonrpc": "2.0", "method": "VideoLibrary.Scan", "id": 1},
            {"jsonrpc": "2.0", "method": "GUI.ShowNotification", "id": 2,
             "params": {"title": "New Shows Available to Watch", "message": self.new or "",
                        "displaytime": 10000}},
        ]
        try:
            sock = socket.create_connection((self.xbmcaddress, int(self.xbmcport)), timeout=6)
            try:
                for message in messages:
                    sock.sendall((json.dumps(message) + "\n").encode("utf-8"))
            finally:
                sock.close()
        except (OSError, socket.timeout) as e:
            self.out("warn", "WARN: Could not connect to xbmc server: %s\n" % e)

    def process_args(self, argv):
        # checks for the old "option:value" style and converts to "option=value"
        converted = []
        for arg in argv:
            m = re.match(r"^(-[^:= \t]+):(.+)$", arg)
            converted.append("%s=%s" % (m.group(1), m.group(2)) if m else arg)
        rest = self.get_options(converted)
        if len(rest) > 0:
            self.set_directory(rest[0], "sortdir")
        if len(rest) > 1:
            self.set_directory(rest[1], "tvdir")

    def display_sortdirs(self):
        if self.sortdir:
            self.out("std", "Sorting:\n\tFrom %s\n" % self.sortdir)
        if self.tvdir:
            self.out("std", "\tTV episodes into %s\n" % self.tvdir)
        if self.moviedir:
            self.out("std", "\tMovies into %s\n" % self.moviedir)
        if self.musicdir:
            self.out("std", "\tMusic into %s\n" % self.musicdir)
        if self.miscdir:
            self.out("std", "\tEverything else into %s\n" % self.miscdir)

    def display_license(self):
        self.out("std", "SortTV is copyleft free open source software.\nYou are free to make modifications and "
                        "share, as defined by version 3 of the GNU General Public License\n")
        self.out("std", "This is a Python port of SortTV by Z. Cliffe Schreuders. If you find it helpful, "
                        "donations to the original author are welcomed:\n"
                        "http://sourceforge.net/donate/index.php?group_id=330009\n")
        self.out("std", "~" * 6, "\n")

    def set_directory(self, directory, attr):
        """Checks that a dir exists, then sets the corresponding variable (with a trailing /)."""
        directory = directory.replace("\\", "/")
        if os.path.exists(directory):
            if not directory.endswith("/"):
                directory += "/"
            setattr(self, attr, directory)
        else:
            self.out("warn", "WARN: directory does not exist (%s)\n" % directory)

    def get_config_from_file(self, fname):
        try:
            fh = open(fname, encoding="utf-8")
        except OSError as e:
            self.out("warn", "WARN: Couldn't open config file '%s': %s\n" % (fname, e.strerror))
            self.out("warn", "INFO: An example config file is available and can make using SortTV easier\n")
            return
        self.out("verbose", "INFO: Reading configuration settings from '%s'\n" % fname)
        with fh:
            for line in fh:
                line = line.rstrip("\r\n")
                line = line.replace("\\", "/")
                if re.match(r"^\s*#", line) or re.match(r"^\s*$", line):
                    continue  # ignores comments and whitespace
                # convert from ':' to '=' assignment format
                m = re.match(r"(^[^:= \t]+):(.+)$", line)
                if m:
                    line = "%s=%s" % (m.group(1), m.group(2))
                self.get_options(["--" + line])

    # -----------------------------------------------------------------------
    # Sorting
    # -----------------------------------------------------------------------

    def sort_directory(self, sortd, files=()):
        """Sorts the contents of sortd, plus any additional files."""
        entries = []
        if sortd:
            if self.extractrar == "TRUE":
                self.extract_archives(sortd)
            entries = list_dir(sortd)

        for file in entries + list(files):
            self.showname = ""
            fname = filename(file)
            self.out("verbose", "INFO: Currently checking file: %s\n" % fname)
            # check white and black lists
            if self.check_lists(file) == "NEXT":
                continue
            # check size
            if self.check_filesize(file) == "NEXT":
                continue
            # check age
            if self.sortolderthandays:
                try:
                    age_days = (time.time() - os.stat(file).st_mtime) / 86400.0
                except OSError:
                    age_days = 0
                if age_days < self.sortolderthandays:
                    self.out("std", "SKIP: %s is newer than %s days old.\n" % (file, self.sortolderthandays))
                    continue
            # treat symlinks separately
            if os.path.islink(file):
                if self.removesymlinks == "TRUE":
                    self.out("std", "DELETE: Removing symlink: %s\n" % file)
                    if not self.dryrun:
                        try:
                            os.unlink(file)
                        except OSError as e:
                            self.out("warn", "WARN: Could not delete symlink %s: %s\n" % (file, e))
                # otherwise file is a symlink, ignore
            elif os.path.isdir(file) and self.treatdir == "IGNORE":
                self.out("verbose", "INFO: Ignoring Dir: %s\n" % file)
            else:
                # here we attempt to sort each type of media
                # movie should come last since it will attempt to find a matching movie name online
                try:
                    if not (self.is_music(file, fname)
                            or self.is_season_directory(file, fname)
                            or self.is_tv_episode(file, fname)
                            or self.is_movie(file, fname)):
                        # if it does not match the requirements for any sort method,
                        # either recursively sort each directory, or the file is an "other"
                        if os.path.isdir(file) and self.treatdir == "RECURSIVELY_SORT_CONTENTS":
                            self.out("verbose", "INFO: Entering into directory or compressed file %s\n" % file)
                            self.sort_directory(file + "/")
                            # removes any empty directories from the to-sort directory and sub-directories
                            if not self.dryrun:
                                self.remove_empty_dirs(sortd)
                        elif self.miscdir and self.tvdir != "KEEP_IN_SAME_DIRECTORIES":
                            # move anything else
                            self.sort_other("OTHER", self.miscdir, file)
                except Exception as e:  # keep going with the next file, as the original did
                    self.out("warn", "WARN: Error sorting %s: %s\n" % (file, e))

    @staticmethod
    def remove_empty_dirs(top):
        if not top:
            return
        for root, dirs, files in os.walk(top, topdown=False):
            if os.path.normpath(root) == os.path.normpath(top):
                continue
            try:
                os.rmdir(root)
            except OSError:
                pass

    def is_other(self, file):
        return matches_type(file, self.nonmediaext)

    def is_video_to_be_sorted(self, file, fname):
        isfile, isdir = os.path.isfile(file), os.path.isdir(file)
        return (self.treatdir == "AS_FILES_TO_SORT" and isdir) \
            or (self.useextensions == "FALSE" and isfile and not self.is_other(file)) \
            or (isfile and not self.is_other(file) and matches_type(fname, VIDEO_EXT + IMAGE_EXT + SUBTITLE_EXT))

    def is_music_to_be_sorted(self, file, fname):
        return os.path.isfile(file) and not self.is_other(file) and matches_type(fname, self.musicext)

    def is_movie(self, file, fname):
        """Checks whether this is a movie to be sorted; if it is, this kicks off the sorting process."""
        if self.moviedir and (self.is_video_to_be_sorted(file, fname)
                              or (os.path.isdir(file) and self.sort_movie_dir == "TRUE")):
            patterns = [
                URLATSTART_RE + r"?(.*?)" + DASHSPACE_RE + r"*\(?\[?((?:20|19)\d{2})\)?\]?(?:" + MOVIE_TAGS_RE
                + r")*.*?(\.\w*$)",
                r"(.*?)\.?(?:[\[\]{}()]|" + MOVIE_TAGS_RE + r")+.*?()(\.\w*$)",
                r"(.*?)()(\.\w*$)",
                r"(.*)()()",
            ]
            for pattern in patterns:
                m = re.search(pattern, fname, re.I)
                if m:
                    title, year, ext = m.group(1), m.group(2), m.group(3)
                    title = re.sub(r"(?:" + MOVIE_TAGS_RE + r"|[\[\]{}()])", "", title, flags=re.I)
                    # at this point if it is not a known movie it is an "other"
                    if self.tmdb and self.match_and_sort_movie(title, year, ext, file):
                        return True
                    break
        return False

    def _season_title_re(self):
        """$seasontitle as interpolated (unquoted) into a regex in the original."""
        try:
            re.compile(self.seasontitle)
            return self.seasontitle
        except re.error:
            return re.escape(self.seasontitle)

    @staticmethod
    def _extract_year(pureshowname):
        m = re.search(r"(.*)(?:\.|\s|-|\(|\[)*\(?((?:20|19)\d{2})(?:\)|\])?", pureshowname)
        return m.group(2) if m else ""

    def _format_series(self, series):
        if self.seasondoubledigit == "TRUE" and re.search(r"\d+", str(series)):
            return "%02d" % int(series)
        return str(series)

    def is_tv_episode(self, file, fname):
        """Checks whether this is a TV episode to be sorted; if it is, this kicks off the sorting process."""
        if not (self.tvdir and self.is_video_to_be_sorted(file, fname)):
            return False
        dirsandfile = file.replace(self.sortdir, "", 1) if self.sortdir else file
        st = re.escape(self.seasontitle)
        ds, url, sp = DASHSPACE_RE, URLATSTART_RE, SPACESLASHDASH_OR_FIRSTCAPTURED_RE

        m = re.search(url + r"?(.*?)(?:\.|\s|-|_|\[)+[Ss]0*(\d+)" + ds + r"*[Ee]0*(\d+).*", fname)
        # "Show/Season 1/S1E1.avi" or "Show/Season 1/1.avi" or "Show Season 1/101.avi" or "Show/Season 1/1x1.avi"
        # or "Show Series 1 Episode 1.avi" etc
        if not m:
            m = re.search(url + r"?(.*?)" + sp + r"*(?:Season|Series|" + st + r")\D?0*(\d+)" + sp + r"+[Ss]0*\2"
                          + ds + r"*[Ee]0*(\d+).*", dirsandfile, re.I)
        # Show.S11E11.something/show.1111.blah.ext
        if not m:
            m = re.search(url + r"?(.*?)" + ds + r"*[Ss]0*(\d+)" + ds + r"*[Ee]0*(\d+).*" + sp + r"+\1\2.*",
                          dirsandfile, re.I)
        if not m:
            m = re.search(url + r"?(.*?)" + sp + r"*(?:Season|Series|" + st + r")\D?0*(\d+)" + sp
                          + r"+\[?0*\2?\s*[xX-]?\s*0*(\d{1,2}).*", dirsandfile, re.I)
        if not m:
            m = re.search(url + r"?(.*?)" + sp + r"*(?:Season|Series|" + st + r")\D?0*(\d+)" + sp
                          + r"+\d??(?:[ .-]*Episode[ .-]*)?0*(\d{1,2}).*", dirsandfile, re.I)
        # not a date, but is 1x1 or 1-1
        if not m and not re.search(r"(\d{4}[-.]\d{1,2}[-.]\d{1,2})", fname):
            m = re.search(url + r"?(.*)" + ds + r"+\[?0*(\d+)\s*[xX-]\s*0*(\d+).*", fname)
        if not m:
            m = re.search(url + r"?(.*)" + ds + r"+0*(\d)(\d{2})(?:\.|\s).*", fname)
        if not m and self.matchtype == "LIBERAL":
            m = re.search(r"(.*)" + ds + r"0*(\d+)\D*0*(\d+).*", filename(file))

        if m:
            self.pureshowname = self.fixpurename(m.group(1))
            self.showname = self.fixtitle(self.pureshowname)
            self.series = self._format_series(m.group(2)) if self.seasondoubledigit == "TRUE" else m.group(2)
            self.episode = m.group(3)
            # extract year if present, for example "Show (2011)"
            self.year = self._extract_year(self.pureshowname)
            if self.pureshowname != "":
                if not self.tvdir.startswith("KEEP_IN_SAME_DIRECTORIES"):
                    return self.move_episode(self.pureshowname, self.showname, self.series, self.episode,
                                             self.year, file)
                self.rename_episode(self.pureshowname, self.series, self.episode, file)
                return True
            return False

        # match "Show - Episode title.avi" or "Show - [AirDate].avi"
        if self.lookupseasonep == "TRUE" and self.tvdb and \
                ((os.path.isdir(file) and self.treatdir == "AS_FILES_TO_SORT")
                 or (os.path.isfile(file) and matches_type(fname, VIDEO_EXT + IMAGE_EXT + SUBTITLE_EXT))):
            m = re.search(r"(.*)(?:\.|\s)(\d{4}[-.]\d{1,2}[-.]\d{1,2}).*", filename(file)) \
                or re.search(r"(.*)-(.*)(?:\..*)", filename(file))
            if m:
                self.pureshowname = m.group(1)
                self.showname = self.fixtitle(self.pureshowname)
                self.year = self._extract_year(self.pureshowname)
                episodetitle = self.fixdate(m.group(2))
                self.series = self.episode = ""
                # tries to find season and episode numbers: returns (season, episode)
                found = self.fetchseasonep(self.resolve_show_name(self.pureshowname), episodetitle)
                if found:
                    self.series, self.episode = str(found[0]), str(found[1])
                if self.series != "" and self.episode != "":
                    self.series = self._format_series(self.series)
                    if not self.tvdir.startswith("KEEP_IN_SAME_DIRECTORIES"):
                        return self.move_episode(self.pureshowname, self.showname, self.series, self.episode,
                                                 self.year, file)
                    self.rename_episode(self.pureshowname, self.series, self.episode, file)
                    return True
        return False

    def is_season_directory(self, file, fname):
        """Checks whether this is a tv season directory to be sorted as is."""
        if self.tvdir and self.treatdir == "AS_FILES_TO_SORT" and os.path.isdir(file):
            m = re.search(r".*/(.*)(?:Season|Series|" + self._season_title_re() + r")\D?0*(\d+).*", file, re.I)
            if m and m.group(1):
                self.out("verbose", "INFO: Treating %s as directory to sort\n" % file)
                self.pureshowname = m.group(1)
                self.series = self._format_series(m.group(2)) if self.seasondoubledigit == "TRUE" else m.group(2)
                self.showname = self.fixtitle(self.pureshowname)
                self.year = self._extract_year(self.pureshowname)
                if self.move_series(self.pureshowname, self.showname, self.series, self.year, file):
                    return True
        return False

    def is_music(self, file, fname):
        """Checks whether this is music to be sorted; if it is, sorts it."""
        if self.musicdir and self.is_music_to_be_sorted(file, fname):
            self.sort_other("MUSIC", self.musicdir, file)
            return True
        return False

    def sort_other(self, msg, destdir, file):
        """Used to sort files into another directory."""
        newname = file.replace(self.sortdir, "", 1) if self.sortdir else file
        newname = self.escape_myfilename(newname)
        if self.flattennonepisodefiles == "FALSE":
            dirs = path_of(newname)
            fname = filename(newname)
            if not os.path.isdir(file) and not os.path.exists(destdir + dirs):
                os.makedirs(destdir + dirs, exist_ok=True)  # recursively creates the dir structure
            newname = dirs + fname
        else:  # flatten
            newname = re.sub(r"[\\/]", "-", newname)
        self.sort_file(file, destdir + newname, msg)

    # -----------------------------------------------------------------------
    # Name handling
    # -----------------------------------------------------------------------

    def fixtitle(self, title):
        """Normalises a title for comparisons: lowercase, drops 'the', 'and', commas, path and punctuation."""
        original = title
        title = title.lower()
        title = re.sub(r",|\.the\.|\bthe\b", " ", title, flags=re.I)
        title = re.sub(r"\.and\.|\band\b", " ", title, flags=re.I)
        title = title.rsplit("/", 1)[-1]
        title = remdot(title)
        # make sure that didn't remove everything
        return title if title else original

    def fixpurename(self, title):
        """Cleans up the show title extracted by the episode regexes."""
        m = re.search(r"/(.+)", title)
        if m:
            title = m.group(1)
        title = re.sub(r"(?:Season.([0-9]{1,3}).|Series.([0-9]{1,3}).|" + re.escape(self.seasontitle) + r".*)",
                       "", title, flags=re.I)
        title = remdot(title)
        title = re.sub(r"\s\s", " ", title)
        return title

    def fixdate(self, title):
        """Formats a date to YYYY-MM-DD for air date lookups; anything else goes to fixtitle."""
        m = re.search(r"(\d{4})[-.](\d{1,2})[-.](\d{1,2})", title)
        if m:
            return "%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3)))
        return self.fixtitle(title)

    def substitute_name(self, source):
        fixed = self.fixtitle(source).lower()
        for substitute, replacement in self.showrenames.items():
            if fixed == substitute.lower():
                return replacement
        return source

    def resolve_show_name(self, title):
        """Applies name substitutions, or else looks up the proper title on thetvdb.

        A name set with show-name-substitute is used exactly as written (thetvdb's title does not replace it),
        so you can choose your own folder name, e.g. "WWE Raw-->WWE.Monday.Night.Raw".
        """
        cleaned = remdot(title)
        substituted = self.substitute_name(cleaned)
        if substituted is not cleaned:
            return substituted
        return self.tvdb_title(substituted)

    def tvdb_ref(self, name):
        """What to look a show up by on thetvdb: its tvdb-id-substitute ID if one is configured, else the name."""
        return self.substitute_tvdb_id(name)

    def substitute_tvdb_id(self, source):
        fixed = self.fixtitle(source).lower()
        for substitute, tvdbid in self.showtvdbids.items():
            if fixed == substitute.lower():
                return tvdbid
        return source

    def tvdb_title(self, filetitle):
        """Looks up the show title (via a configured tvdb id, or by name); returns the original if not found."""
        if not filetitle:
            filetitle = self.pureshowname
        if self.tvdbrename == "TRUE" and self.tvdb:
            try:
                id_sub = self.substitute_tvdb_id(filetitle)
                if re.match(r"^[+-]?\d+$", str(id_sub)):
                    newname = self.tvdb.series_name_by_id(int(id_sub))
                    if newname:
                        return newname
                newname = self.tvdb.series_name(filetitle)
                if newname:
                    return newname
            except HTTPError as e:
                self.out("verbose", "INFO: thetvdb lookup failed for %s: %s\n" % (filetitle, e))
        return filetitle

    def escape_myfilename(self, name):
        """Converts to filesystem friendly names."""
        if IS_WINDOWS or self.windowsnames == "TRUE":
            return re.sub(r'[:*?"<>|]', "-", name)
        return re.sub(r'["<>|]', "-", name)

    @staticmethod
    def extract_quality(file):
        fname = filename(file)
        for qual in ("Bluray", "BlurayRip", "HD", "720p", "1080p", "High definition"):
            if re.search(r"\b" + qual + r"\b", fname, re.I):
                return " HD"
        for qual in ("DVD", "SD", "DVDRip"):
            if re.search(r"\b" + qual + r"\b", fname, re.I):
                return " SD"
        return ""

    # -----------------------------------------------------------------------
    # Filters
    # -----------------------------------------------------------------------

    def check_lists(self, filepath):
        """Checks the white, delete and ignore lists. Returns 'OK' or 'NEXT'."""
        fname = filename(filepath)
        if os.path.isdir(filepath):
            fname += "/"
        if self.whitelist and not any(re.search(w, fname) for w in self.whitelist):
            self.out("std", "SKIP: Doesn't match whitelist: %s\n" % fname)
            return "NEXT"
        for todelete in self.deletelist:
            if re.search(todelete, fname):
                self.out("std", "DELETE: Matches delete list: %s\n" % filepath)
                if not self.dryrun:
                    try:
                        if os.path.isdir(filepath) and not os.path.islink(filepath):
                            os.rmdir(filepath)
                        else:
                            os.unlink(filepath)
                    except OSError as e:
                        self.out("warn", "WARN: File could not be deleted: %s\n" % e)
                return "NEXT"
        for black in self.blacklist:
            if re.search(black, fname):
                self.out("std", "SKIP: Matches ignore list: %s\n" % fname)
                return "NEXT"
        return "OK"

    def check_filesize(self, file):
        if not os.path.isfile(file) or not self.sizerange:
            return "OK"
        filesize = os.path.getsize(file) / 1024.0 / 1024.0
        for minsize, maxsize in self.sizerange:
            if minsize <= filesize <= maxsize:
                return "OK"
        self.out("std", "SKIP: Doesn't fit the filesize requirements: %s\n" % filename(file))
        return "NEXT"

    # -----------------------------------------------------------------------
    # Archives
    # -----------------------------------------------------------------------

    def _run_extractor(self, commands, arfile, dest, label_fail):
        failure_codes = (1, 3, 127)  # the original treated these exit codes as failure
        for label, cmd in commands:
            try:
                code = subprocess.call(cmd, stdout=subprocess.DEVNULL if not self.verbose else None)
            except OSError:
                continue
            if code not in failure_codes:
                self.out("std", "%s: extracting %s into %s\n" % (label, arfile, dest))
                return
        self.out("std", "WARN: the %s program could not be found (or an error occurred), not decompressing %s\n"
                 % (label_fail, arfile))

    def extract_archives(self, sortd):
        """Extracts .rar, .zip, .7z etc. using rar, unrar, unzip or 7zip if available."""
        try:
            names = sorted(n for n in os.listdir(sortd) if not n.startswith("."))
        except OSError:
            return
        archives = []
        for ext in ("rar", "zip", "7z", "gz", "bz2"):
            archives += [sortd + n for n in names if n.endswith("." + ext)]
        sevenzips = [("7ZIP", "7z"), ("7ZIP", "7za"), ("7ZIP", r"C:\Program Files\7-Zip\7z.exe")]
        for arfile in archives:
            dest = arfile + " (extracted by SortTV)"
            if os.path.exists(dest):
                self.out("std", "SKIP: already extracted: %s\n" % dest)
                continue
            prefix = filename_without_ext(arfile)
            if any(n.startswith(prefix) and ".part" in n[len(prefix):] for n in names):
                self.out("std", "SKIP: parts are still downloading: %s\n" % arfile)
                continue
            if re.search(r"\b.*\.part\d+\.rar$", filename(arfile), re.I) and \
                    not re.search(r"\b.*\.part0*1\.rar$", filename(arfile), re.I):
                self.out("std", "SKIP: part file: %s\n" % arfile)
                continue
            if self.dryrun:
                self.out("std", "DRYRUN: not extracting %s\n" % arfile)
                continue
            try:
                os.mkdir(dest)
            except OSError as e:
                self.out("warn", "WARN: could not create directory: %s (%s), extracting to %s\n" % (dest, e, sortd))
                dest = sortd
            dest_slash = dest if dest.endswith("/") else dest + "/"
            seven = [(label, [exe, "e", "-y", arfile, "-o" + dest]) for label, exe in sevenzips]
            if arfile.endswith(".rar"):
                over = "+" if self.ifexists == "OVERWRITE" else "-"
                self._run_extractor([("RAR", ["rar", "e", "-o" + over, arfile, dest_slash]),
                                     ("UNRAR", ["unrar", "e", "-o" + over, arfile, dest_slash])] + seven,
                                    arfile, dest, "rar / 7zip")
            elif arfile.endswith(".zip"):
                over = "-o" if self.ifexists == "OVERWRITE" else "-n"
                self._run_extractor([("UNZIP", ["unzip", over, arfile, "-d", dest])] + seven,
                                    arfile, dest, "unzip / 7zip")
            else:
                self._run_extractor(seven, arfile, dest, "7zip")

    # -----------------------------------------------------------------------
    # TV episodes
    # -----------------------------------------------------------------------

    def display_time(self):
        self.out("std", time.strftime("%H:%M:%S, %d-%m-%Y") + "\n")

    def _mkdir(self, path):
        try:
            os.mkdir(path, 0o777)
        except OSError as e:
            return e
        if self.dir_perms is not None:
            try:
                os.chmod(path, int(str(self.dir_perms), 8))
            except (OSError, ValueError) as e:
                self.out("warn", "WARN: could not set permissions on %s: %s\n" % (path, e))
        return None

    def rename_episode(self, pureshowname, series, episode, file):
        self.out("verbose", "INFO: trying to rename %s season %s episode %s\n" % (pureshowname, series, episode))
        self.move_an_ep(file, path_of(file), path_of(file), series, episode)
        return True

    def dir_matching_show_name(self, tvdir, pureshowname, showname, year):
        self.out("verbose", "INFO: trying to move %s season %s episode %s\n" % (pureshowname, self.series,
                                                                                self.episode))
        subshowname = self.fixtitle(self.escape_myfilename(self.resolve_show_name(pureshowname))).lower()
        for show in list_dir(tvdir):
            # test if it matches a simple version, or a substituted version of the file to move
            if self.fixtitle(filename(show)).lower() == showname.lower() or \
                    self.fixtitle(self.escape_myfilename(filename(show))).lower() == subshowname:
                # and if a year is included try finding one where year matches the dir
                if year:
                    m = re.search(r".*(?:\.|\s|-|\(|\[)*\(?((?:20|19)\d{2})(?:\)|\])?$", show)
                    if m and abs(int(m.group(1)) - int(year)) <= self.yeartoleranceforerror:
                        return show
                else:
                    return show

        # if we are here then we couldn't find a matching show
        if year:
            self.out("std", "INFO: Could not find a show directory for %s matching the year %s, trying ignoring "
                            "the year...\n" % (pureshowname, year))
            return self.dir_matching_show_name(tvdir, pureshowname, showname, "")
        if self.needshowexist != "TRUE":
            # we couldn't find a matching show, make DIR
            newshow = self.escape_myfilename(self.resolve_show_name(pureshowname))
            if self.usedots == "TRUE":
                newshow = re.sub(r"\s", ".", newshow)
            newshowdir = tvdir + newshow
            self.out("std", "INFO: making show directory: %s\n" % newshowdir)
            err = self._mkdir(newshowdir)
            if err is None:
                if self.fetchimages != "FALSE":
                    self.fetchshowimages(self.resolve_show_name(pureshowname), newshowdir)
                return newshowdir
            self.out("warn", "WARN: Could not create show dir: %s:%s\n" % (newshowdir, err))
        return None

    def dir_matching_season(self, show, series, pureshowname, make_or_check):
        season_re = r"(?:Season|Series|" + self._season_title_re() + r")?\s?0*(\d+)$"
        for season in list_dir(show + "/"):
            season = season.replace(show + "/", show + "/", 1)
            if os.path.isdir(season + "/"):
                m = re.search(season_re, season, re.I)
                if m and int(m.group(1)) == int(series):
                    return season
        # didn't find a matching season, make DIR
        if make_or_check == "check":
            return None
        self.out("std", "INFO: making season directory: %s/%s%s\n" % (show, self.seasontitle, series))
        newdir = "%s%s" % (self.seasontitle, series)
        if self.usedots == "TRUE":
            newdir = re.sub(r"\s", ".", newdir)
        newpath = "%s/%s" % (show, newdir)
        err = self._mkdir(newpath)
        if err is None:
            if self.fetchimages != "FALSE":
                self.fetchseasonimages(self.resolve_show_name(pureshowname), show, series, newpath)
            return newpath
        self.out("warn", "WARN: Could not create season dir: %s\n" % err)
        return None

    def move_episode(self, pureshowname, showname, series, episode, year, file):
        """Finds (and possibly creates) the show/season dirs for an episode, and sorts it into them."""
        show = self.dir_matching_show_name(self.tvdir, pureshowname, showname, year)
        if show:
            self.out("verbose", "INFO: found a matching show:\n\t%s\n" % show)
            if self.useseasondirs == "TRUE":
                season = self.dir_matching_season(show, series, pureshowname, "make")
            else:
                self.out("verbose", "INFO: not using a season directory.\n")
                season = show
            if season:
                self.out("verbose", "INFO: found a matching season directory:\n\t%s\n" % season)
                self.move_an_ep(file, season, show, series, episode)
                return True
        else:
            self.out("verbose", "SKIP: Show directory does not exist: %s%s\n"
                     % (self.tvdir, self.escape_myfilename(self.resolve_show_name(pureshowname))))
        return False

    # -- images ---------------------------------------------------------------

    def _duplicate_image(self, source, dest, link_target):
        """Symlinks (or copies) an image, as configured by duplicate-images."""
        if self.duplicateimages == "SYMLINK":
            try:
                os.symlink(link_target, dest)
                return
            except (OSError, NotImplementedError, AttributeError):
                pass
        try:
            shutil.copyfile(source, dest)
        except OSError:
            pass

    def fetchshowimages(self, fetchname, newshowdir):
        if not self.tvdb:
            return
        self.out("std", "DOWNLOAD: downloading images for %s\n" % fetchname)
        if self.dryrun:
            self.out("std", "DRYRUN: not copying images.\n")
            return
        try:
            poster, fanart, banner = self.tvdb.series_images(self.tvdb_ref(fetchname))
        except HTTPError as e:
            self.out("verbose", "INFO: Failed to download TV images: %s.\n" % e)
            return
        got_fanart = fanart and download_file(fanart, newshowdir + "/fanart.jpg")
        got_banner = banner and download_file(banner, newshowdir + "/banner.jpg")
        got_poster = poster and download_file(poster, newshowdir + "/poster.jpg")
        if not (got_fanart or got_banner or got_poster):
            self.out("verbose", "INFO: No TV images downloaded for %s.\n" % fetchname)
        if got_poster and self.imagesformat == "POSTER":
            self._duplicate_image(newshowdir + "/poster.jpg", newshowdir + "/folder.jpg", "poster.jpg")
        elif got_banner and self.imagesformat == "BANNER":
            self._duplicate_image(newshowdir + "/banner.jpg", newshowdir + "/folder.jpg", "banner.jpg")

    def fetchseasonimages(self, fetchname, newshowdir, season, seasondir):
        if not self.tvdb:
            return
        self.out("std", "DOWNLOAD: downloading season image for %s\n" % fetchname)
        if self.dryrun:
            self.out("std", "DRYRUN: not copying images.\n")
            return
        try:
            poster, bannerwide = self.tvdb.season_images(self.tvdb_ref(fetchname), season)
        except HTTPError as e:
            self.out("verbose", "INFO: Failed to download TV images: %s.\n" % e)
            return
        snum = "%02d" % int(season)
        target = "%s/season%s.jpg" % (newshowdir, snum)
        url = poster if self.imagesformat == "POSTER" else bannerwide if self.imagesformat == "BANNER" else None
        if url and download_file(url, target):
            self._duplicate_image(target, seasondir + "/folder.jpg", "../season%s.jpg" % snum)

    def fetchepisodeimage(self, fetchname, newshowdir, season, seasondir, episode, newfilename):
        if not self.tvdb:
            return
        if self.dryrun:
            self.out("std", "DRYRUN: not copying images.\n")
            return
        try:
            epimage = self.tvdb.episode_image(self.tvdb_ref(fetchname), season, episode)
        except HTTPError as e:
            self.out("verbose", "INFO: Failed to download TV episode image: %s.\n" % e)
            return
        if epimage:
            newimagepath = re.sub(r"(.*)(\..*)", r"\1.tbn", seasondir.rstrip("/") + "/" + newfilename)
            download_file(epimage, newimagepath)

    # -- lookups --------------------------------------------------------------

    def fetchseasonep(self, show, eptitle):
        """Looks up the season and episode number from the show name and episode title or air date."""
        if not self.tvdb:
            return None
        ref = self.tvdb_ref(show)
        try:
            if self.tvdb.series_id(ref) is None:
                self.out("std", "WARN: Failed to get %s series information on thetvdb.com.\n" % show)
                return None
            if re.search(r"\d{4}-\d{2}-\d{2}", eptitle):
                self.out("verbose", "INFO: Looking for episode of %s aired on %s.\n" % (show, eptitle))
                ep = self.tvdb.episode_by_airdate(ref, eptitle)
            else:
                self.out("verbose", "INFO: Looking for episode of %s named %s.\n" % (show, eptitle))
                ep = self.tvdb.episode_by_title(ref, eptitle)
        except HTTPError as e:
            self.out("warn", "WARN: Failed to get %s series information on thetvdb.com: %s\n" % (show, e))
            return None
        if ep:
            return ep["seasonNumber"], ep["number"]
        return None

    # -- moving an episode ----------------------------------------------------

    def move_an_ep(self, file, season, show, series, episode):
        newfilename = filename(file)
        sendxbmcnotifications = self.xbmcoldwebserver or self.xbmcaddress
        ep1 = "S%02dE%02d" % (int(series), int(episode))
        if self.rename == "TRUE":
            ext = eptitle = ""
            if not os.path.isdir(file) and "." in filename(file):
                ext = "." + filename(file).rsplit(".", 1)[1]
            m = re.search(r"\[EP_NAME(\d)\]", self.renameformat, re.I)
            if m:
                fmt = m.group(1)
                sname = self.resolve_show_name(self.pureshowname)
                self.out("verbose", "INFO: Fetching episode title for %s Season %s Episode %s.\n"
                         % (sname, series, episode))
                name = ""
                if self.tvdb:
                    showtitle = self.substitute_tvdb_id(sname)
                    try:
                        name = self.tvdb.episode_name(showtitle, series, episode) or ""
                    except HTTPError as e:
                        self.out("verbose", "INFO: thetvdb lookup failed: %s\n" % e)
                if not name and self.tvdbrequired == "TRUE":
                    # the episode name is required and not available: skip this file
                    self.out("warn", "SKIP: Failed to retrieve episode name from thetvdb\n")
                    return
                if name:
                    name = name.rstrip()
                    if fmt == "1":
                        eptitle = " - " + name
                    elif fmt == "2":
                        eptitle = "." + name
                else:
                    self.out("warn", "WARN: Could not get episode title for %s Season %s Episode %s.\n"
                             % (sname, series, episode))
            sname = self.resolve_show_name(self.pureshowname)
            values = [
                (r"\[SHOW_NAME\]", sname),
                (r"\[EP1\]", ep1),
                (r"\[EP2\]", "%dx%d" % (int(series), int(episode))),
                (r"\[EP3\]", "%dx%02d" % (int(series), int(episode))),
                (r"\[EP4\]", "%02d" % int(episode)),
                (r"\[EP_NAME\d\]", eptitle),
            ]
            # create the new file name
            newfilename = self.renameformat
            for pattern, value in values:
                newfilename = re.sub(pattern, lambda _m, v=value: v, newfilename, flags=re.I)
            if re.search(r"\[QUALITY\]", newfilename, re.I):
                quality = self.extract_quality(file)
                newfilename = re.sub(r"\[QUALITY\]", lambda _m: quality, newfilename, flags=re.I)
            # keep any "part 1" etc on the end of the new filename
            pm = re.search(r"(\b(?:part|cd|disk)\s?\.?\d+)\b", filename(file), re.I)
            if pm:
                newfilename += " " + pm.group(1)
            newfilename += ext
            # make sure it is filesystem friendly and contains no slashes
            newfilename = cleanup_filename(self.escape_myfilename(newfilename))
        if self.usedots == "TRUE":
            newfilename = re.sub(r"\s", ".", newfilename)
        newpath = season if season.endswith("/") else season + "/"
        newpath += newfilename
        if not (self.verbose or (self.sortby != "COPY" and self.sortby != "PLACE-SYMLINK")):
            sendxbmcnotifications = ""
        if self.sort_file(file, newpath, "EPISODE"):
            # if the episode was moved...
            if self.fetchimages != "FALSE":
                self.fetchepisodeimage(self.resolve_show_name(self.pureshowname), show, series, season, episode,
                                       newfilename)
            if sendxbmcnotifications:
                self.new = "%s %s" % (self.resolve_show_name(self.pureshowname), ep1)
                self.newshows += self.new + "\n"
                if self.xbmcoldwebserver:
                    if self.xbmc_old_get("ExecBuiltIn(Notification(NEW EPISODE, %s, 7000))" % self.new) is None:
                        self.out("warn", "WARN: Could not connect to xbmc webserver.\nRECOMMENDATION: If you do "
                                         "not use this feature you should disable it in the configuration file.\n")
                        self.xbmcoldwebserver = ""

    # -----------------------------------------------------------------------
    # File operations
    # -----------------------------------------------------------------------

    @staticmethod
    def _move_file(src, dst):
        try:
            os.replace(src, dst)
        except OSError as e:
            if e.errno != errno.EXDEV:
                raise
            shutil.copy2(src, dst)
            os.remove(src)

    @staticmethod
    def _dirmove(src, dst):
        parent = os.path.dirname(dst.rstrip("/"))
        if parent:
            os.makedirs(parent, exist_ok=True)
        if not os.path.exists(dst):
            try:
                os.rename(src, dst)
                return
            except OSError:
                pass
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)
        shutil.rmtree(src)

    @staticmethod
    def _dircopy(src, dst):
        shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)

    def _do(self, action, errfmt, *args):
        if self.dryrun:
            return
        try:
            action(*args)
        except (OSError, shutil.Error) as e:
            self.out("warn", errfmt + " : %s\n" % e)

    def sort_file(self, file, newpath, msg):
        """Moves, copies or links the file to the destination; returns whether it was sorted."""
        retval = False
        verbose_or_moving = self.verbose or (self.sortby != "COPY" and self.sortby != "PLACE-SYMLINK")
        if os.path.exists(newpath):
            if re.search(r"repack|proper", filename(file), re.I):
                # still overwrites if copying, but doesn't output a message unless verbose
                if verbose_or_moving:
                    self.out("warn", "OVERWRITE: Repack/proper version.\n")
                    self.out("std", "%s %s: sorting %s --to--> %s\n" % (self.sortby, msg, file, newpath))
                retval = True
            elif self.ifexists == "OVERWRITE":
                self.out("warn", "OVERWRITE: Existing file.\n")
                self.out("std", "%s %s: sorting %s --to--> %s\n" % (self.sortby, msg, file, newpath))
                retval = True
            else:
                if verbose_or_moving:
                    self.out("warn", "SKIP: File %s already exists, skipping.\n" % newpath)
                return retval
        else:
            self.out("std", "%s%s %s: sorting %s --to--> %s\n" % (self.dryrun, self.sortby, msg, file, newpath))
            retval = True

        isdir = os.path.isdir(file)
        if self.sortby in ("MOVE", "MOVE-AND-LEAVE-SYMLINK-BEHIND"):
            self._do(self._dirmove if isdir else self._move_file,
                     "File %s cannot be moved to %s." % (file, newpath), file, newpath)
        elif self.sortby == "COPY":
            self._do(self._dircopy if isdir else shutil.copy,
                     "File %s cannot be copied to %s." % (file, newpath), file, newpath)
        elif self.sortby == "PLACE-SYMLINK":
            self._do(os.symlink, "File %s cannot be symlinked to %s." % (file, newpath), file, newpath)
        elif self.sortby == "PLACE-HARDLINK":
            self._do(os.link, "File %s cannot be hardlinked to %s." % (file, newpath), file, newpath)
        # have moved, now link
        if self.sortby == "MOVE-AND-LEAVE-SYMLINK-BEHIND":
            self._do(os.symlink, "File %s cannot be symlinked to %s." % (newpath, file), newpath, file)
        return retval

    def move_a_season(self, file, show, series):
        newpath = show + "/" + self.escape_myfilename("%s%s" % (self.seasontitle, series))
        if os.path.exists(newpath):
            if self.sortby not in ("COPY", "PLACE-SYMLINK"):
                self.out("warn", "SKIP: File %s already exists, skipping.\n" % newpath)
            return
        self.out("std", "%s%s SEASON: %s sorting %s --to--> %s\n" % (self.dryrun, self.sortby, file, file, newpath))
        self.out("verbose", "%s: sorting directory to: %s\n" % (self.sortby, newpath))
        errfmt = "%s cannot be sorted to %s" % (file, newpath)
        if self.sortby in ("MOVE", "MOVE-AND-LEAVE-SYMLINK-BEHIND"):
            self._do(self._dirmove, errfmt, file, newpath)
        elif self.sortby == "COPY":
            self._do(self._dircopy, errfmt, file, newpath)
        elif self.sortby == "PLACE-SYMLINK":
            self._do(os.symlink, errfmt, file, newpath)
        elif self.sortby == "PLACE-HARDLINK":
            self._do(os.link, errfmt, file, newpath)
        if self.sortby == "MOVE-AND-LEAVE-SYMLINK-BEHIND":
            self._do(os.symlink, "File %s cannot be symlinked to %s." % (newpath, file), newpath, file)

    def move_series(self, pureshowname, showname, series, year, file):
        """Moves a whole 'Season x' directory."""
        show = self.dir_matching_show_name(self.tvdir, pureshowname, showname, year)
        if show:
            self.out("verbose", "INFO: found a matching show:\t%s\n" % show)
            season = self.dir_matching_season(show, series, pureshowname, "check")
            if season:
                self.out("warn", "SKIP: Cannot move season directory: found a matching season already existing:"
                                 "\n\t%s\n" % season)
                return False
            # found a show without a matching season, move DIR
            self.move_a_season(file, show, series)
            if self.xbmcoldwebserver or self.xbmcaddress:
                self.new = "%s Season %s directory" % (showname, series)
                self.newshows += self.new + "\n"
                if self.xbmcoldwebserver:
                    self.xbmc_old_get("ExecBuiltIn(Notification(NEW EPISODE, %s, 7000))" % self.new)
            return True
        return False

    # -----------------------------------------------------------------------
    # Movies
    # -----------------------------------------------------------------------

    def match_and_sort_movie(self, title, year, ext, file):
        """Matches the title and year to known movies; if a match is found the file is sorted."""
        self.out("verbose", "INFO: Looking for movie matching %s using the movie db\n" % title)
        query = self.fixpurename(title)
        try:
            result = self.tmdb.search_movie(query)
        except (HTTPError, ValueError) as e:
            self.out("warn", "WARN: Could not search the movie db: %s\n" % e)
            return False
        total_pages = result.get("total_pages") or 0
        total_results = result.get("total_results") or 0
        if not total_results > 0:
            self.out("verbose", "INFO: No movies matching %s found\n" % title)
            return False
        self.out("verbose", "INFO: %s movies are similar to %s, checking if they are close enough matches...\n"
                 % (total_results, title))
        fixed_title = self.fixtitle(title)
        # (the original walked every page of results; capped here as TMDb can return hundreds of pages)
        for page_index in range(1, min(total_pages, 10) + 1):
            self.out("verbose", "INFO: Fetching page %s of results\n" % page_index)
            if page_index > 1:
                try:
                    result = self.tmdb.search_movie(query, page_index)
                except (HTTPError, ValueError) as e:
                    self.out("warn", "WARN: Could not search the movie db: %s\n" % e)
                    break
            for result_index, movie in enumerate(result.get("results") or [], 1):
                self.out("verbose", "Processing results page %s #%s: ...\n" % (page_index, result_index))
                moviename = movie.get("title") or ""
                orgname = movie.get("original_title") or ""
                released = movie.get("release_date") or ""
                poster = TMDB_IMAGE_URL + movie["poster_path"] if movie.get("poster_path") else None
                backdrop = TMDB_IMAGE_URL + movie["backdrop_path"] if movie.get("backdrop_path") else None
                self.out("verbose", "INFO: Comparing %s (%s) to %s (%s),%s\n"
                         % (title, fixed_title, moviename, self.fixtitle(moviename) if moviename else "", orgname))
                if (moviename and self.fixtitle(moviename) == fixed_title) or \
                        (orgname and self.fixtitle(orgname) == fixed_title):
                    self.out("verbose", "INFO: Title matches\n")
                    movietitle = cleanup_filename(moviename or orgname)
                    released_year = None
                    ym = re.search(r"(\d{4})-\d{2}-\d{2}", released)
                    if ym:
                        released_year = ym.group(1)
                    else:
                        self.out("warn", "WARN: could not extract year from online movie information (%s)\n"
                                 % movietitle)
                    if year and released_year:
                        if abs(int(released_year) - int(year)) <= self.yeartoleranceforerror:
                            self.out("verbose", "INFO: Year also matches\n")
                            rating = self.get_rating(movie.get("id"))
                            self.sort_movie(file, movietitle, released_year, ext, poster, backdrop, rating)
                            return True
                        self.out("warn", "WARN: Found matching movie '%s', but does not match year in filename "
                                         "(named %s not %s), skipping\n" % (movietitle, year, released_year))
                        continue
                    rating = self.get_rating(movie.get("id"))
                    yeartouse = year or released_year or ""
                    self.sort_movie(file, movietitle, yeartouse, ext, poster, backdrop, rating)
                    return True
        # at this point, we didn't find a match
        return False

    def sort_movie(self, file, title, year, ext, posterimg, backimg, mpaa_rating):
        sendxbmcnotifications = self.xbmcoldwebserver or self.xbmcaddress
        if self.rename == "TRUE":
            location = self.movierenameformat
            # if we are sorting a directory, ignore directories in the rename format
            if os.path.isdir(file):
                location = re.sub(r"/[^/]*$", "", location)
            location = re.sub(r"\[MOVIE_TITLE\]", lambda _m: title, location, flags=re.I)
            location = re.sub(r"\[FIRST_LETTER\]", lambda _m: first_letter(title), location, flags=re.I)
            location = re.sub(r"\[RATING\]", lambda _m: mpaa_rating or "", location, flags=re.I)
            if year:
                location = re.sub(r"\[YEAR1\]", lambda _m: "(%s)" % year, location, flags=re.I)
                location = re.sub(r"\[YEAR2\]", lambda _m: str(year), location, flags=re.I)
            else:
                location = re.sub(r"[. -]*\[YEAR1\]", "", location, flags=re.I)
                location = re.sub(r"[. -]*\[YEAR2\]", "", location, flags=re.I)
            if re.search(r"\[QUALITY\]", location, re.I):
                quality = self.extract_quality(file)
                location = re.sub(r"\[QUALITY\]", lambda _m: quality, location, flags=re.I)
            # keep any "part 1" etc on the end of the new filename
            pm = re.search(r"(\b(?:part|cd|disk)\s?\.?\d+)\b", filename(file), re.I)
            if pm:
                location += " " + pm.group(1)
            location += ext
            dest = self.escape_myfilename(location)
        else:
            dest = filename(file)
        if self.usedots == "TRUE":
            dest = re.sub(r"\s", ".", dest)
        # set the destination, and create the directory if we need to
        if os.path.isdir(file):
            mdir = self.moviedir + dest + "/"
        else:
            mdir = path_of(self.moviedir + dest)
            if not os.path.exists(mdir):
                self.out("std", "INFO: Making directory: %s\n" % mdir)
            if not self.dryrun:
                os.makedirs(mdir, exist_ok=True)
        if self.sort_file(file, self.moviedir + dest, "MOVIE"):
            # if the movie was sorted... download images
            if self.dryrun:
                self.out("std", "DRYRUN: not downloading movie images.\n")
            elif self.fetchmovieimages != "FALSE":
                posterfilename = mdir + "folder.jpg"
                posterfilename_copy = mdir + "movie.tbn"
                fanartfilename = mdir + "fanart.jpg"
                if not (self.rename == "TRUE" and self.movie_has_own_directory()):
                    posterfilename = mdir + filename_without_ext(dest) + ".jpg"
                    posterfilename_copy = mdir + filename_without_ext(dest) + ".tbn"
                    fanartfilename = mdir + filename_without_ext(dest) + "-fanart.jpg"
                self.out("std", "INFO: Fetching movie images\n")
                if posterimg:
                    self.out("std", "INFO: Downloading poster for %s (from %s to %s)\n"
                             % (title, posterimg, posterfilename))
                    if not download_file(posterimg, posterfilename):
                        self.out("warn", "Failed to download image\n")
                if backimg:
                    self.out("std", "INFO: Downloading backdrop for %s (from %s to %s)\n"
                             % (title, backimg, fanartfilename))
                    if not download_file(backimg, fanartfilename):
                        self.out("warn", "Failed to download image\n")
                if os.path.exists(posterfilename):
                    self._duplicate_image(posterfilename, posterfilename_copy, filename(posterfilename))
            if sendxbmcnotifications:
                self.new = "%s %s" % (title, year)
                self.newshows += self.new + "\n"
                if self.xbmcoldwebserver:
                    if self.xbmc_old_get("ExecBuiltIn(Notification(NEW MOVIE, %s, 7000))" % self.new) is None:
                        self.out("warn", "WARN: Could not connect to xbmc webserver.\nRECOMMENDATION: If you do "
                                         "not use this feature you should disable it in the configuration file.\n")
                        self.xbmcoldwebserver = ""

    def movie_has_own_directory(self):
        """Whether the movie rename format puts each movie in its own directory (not just e.g. a letter one)."""
        dirs = self.movierenameformat.rsplit("/", 1)
        return len(dirs) == 2 and re.search(r"\[MOVIE_TITLE\]", dirs[0].rsplit("/", 1)[-1], re.I) is not None

    def get_rating(self, movie_id):
        """US MPAA rating (without hyphens, e.g. PG13), 'NR' if there is none. Only fetched when needed."""
        if not (self.rename == "TRUE" and re.search(r"\[RATING\]", self.movierenameformat, re.I)):
            return ""
        self.out("verbose", "Checking for US MPAA Rating...\n")
        try:
            mpaa = self.tmdb.us_certification(movie_id)
        except (HTTPError, ValueError) as e:
            self.out("warn", "WARN: Could not get the movie rating: %s\n" % e)
            return "NR"
        if not mpaa:
            return "NR"
        self.out("verbose", "MPAA rating found! Rated: %s\n" % mpaa)
        return mpaa.replace("-", "")

    # -----------------------------------------------------------------------
    # Output
    # -----------------------------------------------------------------------

    def out(self, kind, *msg):
        text = "".join(str(m) for m in msg)
        if kind == "verbose" and not self.verbose:
            return
        stream = sys.stderr if kind == "warn" else sys.stdout
        try:
            stream.write(text)
        except UnicodeEncodeError:
            stream.write(text.encode(stream.encoding or "ascii", "replace").decode(stream.encoding or "ascii"))
        stream.flush()
        if self.log:
            self.log.write(text)
            self.log.flush()

    def showhelp(self):
        self.out("std", HELP_TEXT)
        sys.exit(0)


HELP_TEXT = """Usage: sorttv.py [OPTIONS] [directory-to-sort directory-to-sort-into]

By default SortTV tries to read the configuration from sorttv.conf (next to sorttv.py)
You can overwrite any config options with commandline arguments, which match the format of the config file
(except that each argument starts with "--")

OPTIONS:
--directory-to-sort=dir
	A directory containing files to sort
	For example, set this to where completed downloads are stored

--file-to-sort=file
	A file to be sorted
	This argument can be repeated to add multiple individual files to sort

--tv-directory=dir
	Where to sort episodes into (dir that will contain dirs for each show)
	This directory will contain the structure (Show)/(Seasons)/(episodes)
	Alternatively set this to "KEEP_IN_SAME_DIRECTORIES" for a recursive renaming of files in directory-to-sort

--movie-directory=dir
	Where to sort movies into
	If not specified, movies are not moved
	Requires a tmdb-api-key, since movies are identified using themoviedb.org

--music-directory=dir
	Where to sort music into
	If not specified, music is not moved

--misc-directory=dir
	Where to put things that are not episodes etc
	If this is supplied then files and directories that SortTV does not believe are episodes will be moved here
	If not specified, non-episodes are not moved

--tvdb-api-key=key
--tvdb-pin=pin
	Your thetvdb.com v4 API key (and subscriber PIN, if your key needs one)
	Needed for show titles, episode names, episode lookups by title/air date, and images
	Can also be set with the TVDB_API_KEY / TVDB_PIN environment variables
	Get one at https://thetvdb.com/api-information

--tmdb-api-key=key
	Your themoviedb.org API key (v3 key or v4 read access token), needed to sort movies
	Can also be set with the TMDB_API_KEY environment variable
	Get one at https://www.themoviedb.org/settings/api

--dry-run
	Dry run mode. No file operations will occur on the to-sort directory.
	Some directories may be created at the destination.

--whitelist=pattern
	Only copy if the file matches one of these patterns
	Uses shell-like simple pattern matches (eg *.avi)
	This argument can be repeated to add more rules

--ignore=pattern
	Don't copy if the file matches one of these blacklist patterns
	Uses shell-like simple pattern matches (eg *.avi)
	This argument can be repeated to add more rules

--delete=pattern
	Delete the source file, if the file matches one of these patterns
	Uses shell-like simple pattern matches (eg *.avi)
	This argument can be repeated to add more rules

--consider-media-file-extensions=[TRUE|FALSE]
	Consider the file extension before treating certain files as movies or TV episodes
	Recommended: SortTV is aware of a large number of extensions, and this can avoid many false matches
	if not specified, TRUE

--non-media-extension=pattern
	These extensions are NEVER movies or TV shows or music, treat them as "others" automatically
	Note: Will not run these file types through tvdb, tmdb, etc.
	Not typically required if consider-media-file-extensions=TRUE
	This argument can be repeated to add multiple extensions

--filesize-range=pattern
	Only copy files which fall within these filesize ranges.
	Examples for the pattern include 345MB-355MB or 1.05GB-1.15GB

--sort-only-older-than-days=number
	Sort only files or directories that are older than this number of days.
	If not specified or zero, sort everything.

--xbmc-old-web-server=host:port
	host:port for the old xbmc webserver, to automatically update library when new episodes arrive
	If not specified, xbmc is not updated

--xbmc-remote-control=host
	host for Kodi/XBMC JSON-RPC (TCP), to automatically update library when new episodes arrive
	You probably want to set this to "localhost"

--xbmc-remote-control-port=port
	port number for Kodi/XBMC JSON-RPC (TCP)
	If not specified, 9090

--log-file=filepath
	Log to this file
	If not specified, output goes to sorttv.log in the script directory

--verbose
	Output verbosity. Shows messages describing the decision making process.

--poll-time={X}
	Tell the script to check for new files to sort every X seconds, minutes, hours, or days
	Valid values include "2secs", "2days", "1min", "3hrs", "30s" etc.
	If not specified, polling is disabled and the script will only sort the directory once.

--read-config-file=filepath
	Secondary config file, overwrites settings loaded so far
	If not specified, only the default config file is loaded (sorttv.conf)

--fetch-show-title=[TRUE|FALSE]
	Fetch show titles from thetvdb.com (for proper formatting)
	If not specified, TRUE

--rename-media=[TRUE|FALSE]
	Rename episodes and movies to a new format when moving
	If not specified, FALSE

--rename-tv-format={formatstring}
	the format to use if renaming to a new format (as specified above)
	The formatstring can be made up of:
	[SHOW_NAME]: "My Show"
	[EP1]: "S01E01"
	[EP2]: "1x1"
	[EP3]: "1x01"
	[EP4]: "01" (Episode number only)
	[EP_NAME1]: " - Episode Title"
	[EP_NAME2]: ".Episode Title"
	[QUALITY]: " HD" (or " SD") - extracted from original file name
	If not specified the format is "[SHOW_NAME] - [EP1][EP_NAME1]"

--rename-movie-format={formatstring}
	The format to use if renaming movies
	The format can be made up of:
		[MOVIE_TITLE]: "My Movie"
		[YEAR1]: "(2011)"
		[YEAR2]: "2011"
		[QUALITY]: " HD" (or " SD") - extracted from original file name
		[RATING]: "PG" - MPAA rating (US)
		[FIRST_LETTER]: "M" - first letter of the title ("#" if it is not a letter)
		/: A sub-directory (folder) - movies can be in their own directories
		eg "[FIRST_LETTER]/[MOVIE_TITLE] [YEAR2]/[MOVIE_TITLE] [YEAR1]" -> "M/My Movie 2011/My Movie (2011)"
	If not specified the format is, "[MOVIE_TITLE] [YEAR2]/[MOVIE_TITLE] [YEAR1]"

--use-dots-instead-of-spaces=[TRUE|FALSE]
	Renames episodes to replace spaces with dots
	If not specified, FALSE

--use-season-directories=[TRUE|FALSE]
	Whether to use directories for seasons
	If not specified, TRUE

--season-title=string
	Season title (eg "Season " -> "Season 1",  "Series "->"Series 1", "Season."->"Season.1")
	If not specified, "Season "

--season-double-digits=[TRUE|FALSE]
	Season format padded to double digits (eg "Season 01" rather than "Season 1")
	If not specified, FALSE

--year-tolerance-for-error=number
	The tolerated variance for year matches.
	If not specified, 1

--match-type=[NORMAL|LIBERAL]
	LIBERAL assumes all files are episodes and tries to extract season and episode number any way possible.
	If not specified, NORMAL

--match-files-based-on-tvdb-lookups=[TRUE|FALSE]
	Attempt to sort files that are named after the episode title or air date.
	For example, "My show - My episode title.avi" or "My show - 2010-12-12.avi"
	 could become "My Show - S01E01 - My episode title.avi"
	If not specified, TRUE

--sort-by=[MOVE|COPY|MOVE-AND-LEAVE-SYMLINK-BEHIND|PLACE-SYMLINK|PLACE-HARDLINK]
	Sort by moving or copying the file.
	If not specified, MOVE

--treat-directories=[AS_FILES_TO_SORT|RECURSIVELY_SORT_CONTENTS|IGNORE]
	AS_FILES_TO_SORT - sorts directories, moving entire directories that represents an episode, also detects
	                   and moves directories of entire seasons
	RECURSIVELY_SORT_CONTENTS - doesn't move directories, just their contents, including subdirectories
	IGNORE - ignores directories
	If not specified, RECURSIVELY_SORT_CONTENTS

--require-show-directories-already-exist=[TRUE|FALSE]
	Only sort into show directories that already exist
	If not specified, FALSE

--remove-symlinks=[TRUE|FALSE]
	Deletes symlinks from the directory to sort while sorting.
	If not specified, FALSE

--show-name-substitute=NAME1-->NAME2
	Substitutes names equal to NAME1 for NAME2
	NAME2 is used exactly as written for the show folder (thetvdb's title does not replace it)
	Combine with --tvdb-id-substitute=NAME2-->ID so episode lookups still find the right show
	This argument can be repeated to add multiple rules for substitution

--tvdb-id-substitute=NAME1-->TVDB ID
	Substitutes names equal to NAME1 for TVDB ID for lookups
	This argument can be repeated to add multiple rules for substitution

--music-extension=extension
	Define additional extensions for music files (SortTV knows a lot already)

--sort-movie-directories=[TRUE|FALSE]
	Attempt to sort entire directories that represent a movie (the directory is sorted as is)
	If not specified, FALSE

--force-windows-compatible-filenames=[TRUE|FALSE]
	Forces MSWindows compatible file names, even when run on other platforms such as Linux
	If not specified, TRUE

--tv-lookup-language=[en|...]
--movie-lookup-language=[en|...]
	Set language for thetvdb / tmdb lookups, this affects episode and movie titles etc
	If not specified, en (English)

--flatten-non-eps=[TRUE|FALSE]
	Should non-episode files lose their directory structure?
	If not specified, FALSE

--fetch-images=[NEW_SHOWS|FALSE]
	Download images for shows, seasons, and episodes from thetvdb
	If not specified, NEW_SHOWS

--images-format=[POSTER|BANNER]
	If not specified, POSTER

--fetch-movie-images=[TRUE|FALSE]
	If not specified, TRUE

--duplicate-images=[SYMLINK|COPY]
	If not specified, SYMLINK.

--if-file-exists=[SKIP|OVERWRITE]
	If not specified, SKIP

--tvdb-episode-name-required=[TRUE|FALSE]
	Only sort tv episodes if the episode name was available from thetvdb
	If not specified, FALSE

--extract-compressed-before-sorting=[TRUE|FALSE]
	Extracts the contents of archives (.zip, .rar) into the directory-to-sort while sorting
	If "rar", "unrar", "unzip" or "7z" programs are available they are used.
	If not specified, TRUE

--dir-permissions=[octal]
	Set permissions on new created directories (octal format : 0775)

--display-license=[TRUE|FALSE]
	If not specified, TRUE

--no-network
	Disables all the network enabled features

EXAMPLES:
Does a sort, as configured in sorttv.conf:
	python3 sorttv.py

To sort a Downloads directory contents into a TV directory
	python3 sorttv.py /home/me/Downloads /home/me/Videos/TV

To move non-episode files in a separate directory:
	python3 sorttv.py --directory-to-sort=/home/me/Downloads --tv-directory=/home/me/Videos/TV --misc-dir=/home/me/Videos/Other

"""


if __name__ == "__main__":
    try:
        SortTV().main(sys.argv[1:])
    except KeyboardInterrupt:
        sys.exit(130)
