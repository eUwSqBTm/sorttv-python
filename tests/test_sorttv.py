#!/usr/bin/env python3
"""Tests for sorttv.py.

Mirrors the scenarios in the original SortTV test script (other_scripts/sorttv-tests.pl). The online lookups
run against a small local mock of the TheTVDB v4 and TMDb v3 APIs, so no API keys or network access are needed.

Run with:  python3 -m unittest discover -s tests -v
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
SORTTV = os.path.join(os.path.dirname(HERE), "sorttv.py")

# ---------------------------------------------------------------------------
# Mock API data
# ---------------------------------------------------------------------------

SERIES = {
    83949: {"name": "The Guild", "episodes": [(1, 1, "Wake-Up Call", "2007-07-27")]},
    154521: {"name": "Pioneer One", "episodes": [(1, 1, "Earthfall", "2010-06-16"),
                                                 (1, 2, "The Man From Mars", "2010-12-12"),
                                                 (1, 3, "Triangular Diplomacy", "2011-01-18")]},
}
MOVIES = [
    {"id": 1, "title": "RiP!: A Remix Manifesto", "original_title": "RiP!: A Remix Manifesto",
     "release_date": "2009-03-10", "poster_path": "/rip_poster.jpg", "backdrop_path": "/rip_back.jpg", "cert": ""},
    {"id": 2, "title": "Night of the Living Dead", "original_title": "Night of the Living Dead",
     "release_date": "1968-10-04", "poster_path": "/notld.jpg", "backdrop_path": None, "cert": "R"},
    {"id": 3, "title": "Night of the Living Dead", "original_title": "Night of the Living Dead",
     "release_date": "1990-10-19", "poster_path": None, "backdrop_path": None, "cert": "R"},
]


class MockAPI(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/tvdb/login" and body.get("apikey") == "tvdbkey":
            return self._json({"status": "success", "data": {"token": "tok"}})
        return self._json({"status": "failure"}, 401)

    def do_GET(self):
        url = urlparse(self.path)
        q = parse_qs(url.query)
        path = url.path
        if path.startswith("/img/"):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"\xff\xd8image")
            return
        if path.startswith("/tvdb/"):
            if self.headers.get("Authorization") != "Bearer tok":
                return self._json({"status": "failure"}, 401)
            return self.tvdb(path[len("/tvdb"):], q)
        if path.startswith("/tmdb/"):
            if q.get("api_key") != ["tmdbkey"]:
                return self._json({"status_code": 7}, 401)
            return self.tmdb(path[len("/tmdb"):], q)
        self._json({}, 404)

    def tvdb(self, path, q):
        img = "http://127.0.0.1:%d/img" % self.server.server_port
        if path == "/search":
            query = q["query"][0].lower()
            data = [{"tvdb_id": str(sid), "name": s["name"], "translations": {"eng": s["name"]}}
                    for sid, s in SERIES.items() if query in s["name"].lower()]
            return self._json({"status": "success", "data": data})
        if path == "/artwork/types":
            return self._json({"data": [{"id": 1, "name": "Banner", "recordType": "series"},
                                        {"id": 2, "name": "Poster", "recordType": "series"},
                                        {"id": 3, "name": "Background", "recordType": "series"},
                                        {"id": 6, "name": "Banner", "recordType": "season"},
                                        {"id": 7, "name": "Poster", "recordType": "season"}]})
        m = re.match(r"^/series/(\d+)(/.*)?$", path)
        if m and int(m.group(1)) in SERIES:
            sid, rest, s = int(m.group(1)), m.group(2) or "", SERIES[int(m.group(1))]
            if rest == "":
                return self._json({"data": {"id": sid, "name": s["name"]}})
            if rest == "/translations/eng":
                return self._json({"data": {"name": s["name"], "language": "eng"}})
            if rest.startswith("/episodes/default"):
                page = int(q.get("page", ["0"])[0])
                eps = [{"id": sid * 100 + i, "seasonNumber": se, "number": ep, "name": name, "aired": aired,
                        "image": img + "/episodes/%d-%d.jpg" % (se, ep)}
                       for i, (se, ep, name, aired) in enumerate(s["episodes"])] if page == 0 else []
                return self._json({"data": {"series": {"id": sid}, "episodes": eps}, "links": {"next": None}})
            if rest == "/extended":
                return self._json({"data": {"id": sid, "name": s["name"], "image": img + "/poster_base.jpg",
                                            "artworks": [{"type": 2, "image": img + "/poster.jpg", "score": 5},
                                                         {"type": 3, "image": img + "/fanart.jpg", "score": 5},
                                                         {"type": 1, "image": img + "/banner.jpg", "score": 5}],
                                            "seasons": [{"id": sid * 10 + 1, "number": 1,
                                                         "type": {"type": "official"}}]}})
        m = re.match(r"^/seasons/(\d+)/extended$", path)
        if m:
            return self._json({"data": {"id": int(m.group(1)),
                                        "artwork": [{"type": 7, "image": img + "/season_poster.jpg"},
                                                    {"type": 6, "image": img + "/season_banner.jpg"}]}})
        return self._json({"status": "failure"}, 404)

    def tmdb(self, path, q):
        if path == "/search/movie":
            words = re.sub(r"[^a-z ]", "", q["query"][0].lower()).split()
            results = [dict((k, v) for k, v in mv.items() if k != "cert") for mv in MOVIES
                       if all(w in mv["title"].lower() for w in words)]
            return self._json({"page": 1, "total_pages": 1 if results else 0, "total_results": len(results),
                               "results": results})
        m = re.match(r"^/movie/(\d+)/release_dates$", path)
        if m:
            mv = [x for x in MOVIES if x["id"] == int(m.group(1))][0]
            return self._json({"id": mv["id"], "results": [
                {"iso_3166_1": "GB", "release_dates": [{"certification": "18"}]},
                {"iso_3166_1": "US", "release_dates": [{"certification": mv["cert"]}]}]})
        return self._json({}, 404)


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

class SortTVTest(unittest.TestCase):
    STD_RENAME = ["--rename-tv-format=[SHOW_NAME] - [EP1]", "--rename-media=TRUE"]
    TVDB_RENAME = ["--rename-tv-format=[SHOW_NAME] - [EP1][EP_NAME1]", "--rename-media=TRUE"]
    MOVIE_RENAME = ["--rename-movie-format=[MOVIE_TITLE] [YEAR2]/[MOVIE_TITLE] [YEAR1]"]

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MockAPI)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        port = cls.server.server_port
        cls.env = dict(os.environ,
                       SORTTV_TVDB_URL="http://127.0.0.1:%d/tvdb" % port,
                       SORTTV_TMDB_URL="http://127.0.0.1:%d/tmdb" % port,
                       SORTTV_TMDB_IMG_URL="http://127.0.0.1:%d/img" % port,
                       TVDB_API_KEY="tvdbkey", TMDB_API_KEY="tmdbkey")
        for var in ("SORTTV_CONFIG", "SORTTV_DATA_DIR"):
            cls.env.pop(var, None)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="sorttv_test_")
        # run a private copy of the script so the user's sorttv.conf and .cache are not used
        self.scriptdir = os.path.join(self.root, "script")
        os.makedirs(self.scriptdir)
        shutil.copy(SORTTV, self.scriptdir)
        for d in ("sort", "TV", "Movies", "Music", "Misc"):
            os.makedirs(os.path.join(self.root, d))

    def tearDown(self):
        shutil.rmtree(self.root)

    def p(self, rel):
        return os.path.join(self.root, rel)

    def sort(self, files, *options, network=True):
        for f in files:
            full = self.p("sort/" + f)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").close()
        cmd = [sys.executable, os.path.join(self.scriptdir, "sorttv.py"),
               "--directory-to-sort=" + self.p("sort"), "--tv-directory=" + self.p("TV"),
               "--movie-directory=" + self.p("Movies"), "--music-directory=" + self.p("Music"),
               "--misc-dir=" + self.p("Misc"), "--sort-by=MOVE", "--treat-directories=RECURSIVELY_SORT_CONTENTS",
               "--log-file=" + self.p("script/test.log"), "--force-windows-compatible-filenames=TRUE",
               "--display-license=FALSE"] + list(options)
        env = self.env if network else dict(self.env, TVDB_API_KEY="", TMDB_API_KEY="")
        result = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertNotIn("Traceback", result.stderr, result.stderr)
        return result

    def assertExists(self, rel):
        self.assertTrue(os.path.lexists(self.p(rel)), "expected %s; tree:\n%s" % (rel, self.tree()))

    def assertNotExists(self, rel):
        self.assertFalse(os.path.lexists(self.p(rel)), "did not expect %s; tree:\n%s" % (rel, self.tree()))

    def tree(self):
        out = []
        for dp, dn, fn in os.walk(self.root):
            for n in fn:
                out.append(os.path.relpath(os.path.join(dp, n), self.root))
        return "\n".join(sorted(out))

    # -- TV, no network ---------------------------------------------------------

    def test_tv_regex_no_network(self):
        cases = {
            "test/Pioneer One Season 1 Episode 1.avi": "Pioneer One - S01E01.avi",
            "Pioneer One 1x2.avi": "Pioneer One - S01E02.avi",
            "Pioneer One/Season 1/2.avi": "Pioneer One - S01E02.avi",
            "Pioneer One/Season 1/s1e2.avi": "Pioneer One - S01E02.avi",
            "Pioneer One 102.avi": "Pioneer One - S01E02.avi",
            "Pioneer One - 102.avi": "Pioneer One - S01E02.avi",
            "Pioneer One 1-2.avi": "Pioneer One - S01E02.avi",
            "Pioneer One/Season 1/102.avi": "Pioneer One - S01E02.avi",
            "Pioneer One S1E2.avi": "Pioneer One - S01E02.avi",
        }
        for src, dest in cases.items():
            with self.subTest(src=src):
                shutil.rmtree(self.p("TV"))
                os.makedirs(self.p("TV"))
                self.sort([src], "--no-network", *self.STD_RENAME)
                self.assertExists("TV/Pioneer One/Season 1/" + dest)

    def test_delete_and_ignore(self):
        self.sort(["Show 1x1.avi"], "--delete=*.avi", "--no-network", *self.STD_RENAME)
        self.assertNotExists("TV/Show/Season 1/Show - S01E01.avi")
        self.assertNotExists("sort/Show 1x1.avi")
        self.sort(["Show 1x2.avi"], "--ignore=*.avi", "--no-network", *self.STD_RENAME)
        self.assertNotExists("TV/Show/Season 1/Show - S01E02.avi")
        self.assertExists("sort/Show 1x2.avi")

    def test_file_extensions(self):
        self.sort(["Show 1x1.avi", "Show 1x2.ava", "Show 1x3.mpg"], "--consider-media-file-extensions=TRUE",
                  "--non-media-extension=mpg", "--no-network", *self.STD_RENAME)
        self.assertExists("TV/Show/Season 1/Show - S01E01.avi")
        self.assertExists("Misc/Show 1x2.ava")
        self.assertExists("Misc/Show 1x3.mpg")

    def test_filesize_and_age(self):
        self.sort(["Show 1x1.avi"], "--filesize-range=170MB-400MB", "--no-network", *self.STD_RENAME)
        self.assertExists("sort/Show 1x1.avi")
        self.sort([], "--filesize-range=0MB-400MB", "--sort-only-older-than-days=1", "--no-network",
                  *self.STD_RENAME)
        self.assertExists("sort/Show 1x1.avi")
        self.sort([], "--filesize-range=0MB-400MB", "--no-network", *self.STD_RENAME)
        self.assertExists("TV/Show/Season 1/Show - S01E01.avi")

    def test_rename_formats(self):
        self.sort(["Show 1x1.avi", "Show 1x2 1080p.avi", "Show 1x3 DVDRip.avi"], "--rename-media=TRUE",
                  "--rename-tv-format=[EP4][QUALITY]", "--no-network")
        self.assertExists("TV/Show/Season 1/01.avi")
        self.assertExists("TV/Show/Season 1/02 HD.avi")
        self.assertExists("TV/Show/Season 1/03 SD.avi")
        self.sort(["Other 1x1.avi"], "--rename-media=TRUE", "--rename-tv-format=[SHOW_NAME] ~ [EP3]",
                  "--no-network")
        self.assertExists("TV/Other/Season 1/Other ~ 1x01.avi")

    def test_dots_seasons_and_names(self):
        self.sort(["test/Pioneer One Season 1 Episode 1.avi"], "--use-dots-instead-of-spaces=TRUE",
                  "--no-network", *self.STD_RENAME)
        self.assertExists("TV/Pioneer.One/Season.1/Pioneer.One.-.S01E01.avi")
        self.sort(["Show s2e1.avi"], "--season-title=Series.", "--season-double-digits=TRUE", "--no-network",
                  *self.STD_RENAME)
        self.assertExists("TV/Show/Series.02/Show - S02E01.avi")
        # the original test expected "A-@", but since SortTV 1.37's unicode clean-up (kept here) symbols are stripped
        self.sort(["A*@ s1e1.avi"], "--no-network", *self.STD_RENAME)
        self.assertExists("TV/A/Season 1/A - S01E01.avi")

    def test_sort_by_modes(self):
        self.sort(["a/Show s1e1.avi"], "--sort-by=COPY", "--no-network", *self.STD_RENAME)
        self.assertExists("TV/Show/Season 1/Show - S01E01.avi")
        self.assertExists("sort/a/Show s1e1.avi")
        shutil.rmtree(self.p("TV/Show"))
        self.sort([], "--sort-by=MOVE-AND-LEAVE-SYMLINK-BEHIND", "--no-network", *self.STD_RENAME)
        self.assertTrue(os.path.islink(self.p("sort/a/Show s1e1.avi")))
        self.assertExists("TV/Show/Season 1/Show - S01E01.avi")

    def test_season_directory_as_file_to_sort(self):
        self.sort(["Pioneer One Season 1/test.avi"], "--treat-directories=AS_FILES_TO_SORT", "--no-network",
                  *self.STD_RENAME)
        self.assertExists("TV/Pioneer One/Season 1/test.avi")

    def test_flatten_and_music(self):
        self.sort(["test/test/thisisatest.txt", "My Music - test.mp3"], "--flatten-non-eps=TRUE", "--no-network")
        self.assertExists("Misc/test-test-thisisatest.txt")
        self.assertExists("Music/My Music - test.mp3")

    def test_config_file(self):
        with open(os.path.join(self.scriptdir, "sorttv.conf"), "w") as fh:
            fh.write("# test config\nrename-media:TRUE\nrename-tv-format=[SHOW_NAME] [EP2]\n"
                     "show-name-substitute=Its Always Sunny-->It's Always Sunny in Philadelphia\nno-network\n")
        self.sort(["Its.Always.Sunny.S01E01.avi"])
        self.assertExists("TV/It's Always Sunny in Philadelphia/Season 1/It's Always Sunny in Philadelphia 1x1.avi")

    def test_keep_in_same_directories(self):
        self.sort(["sub/show.s01e02.avi"], "--tv-directory=KEEP_IN_SAME_DIRECTORIES", "--no-network",
                  *self.STD_RENAME)
        self.assertExists("sort/sub/show - S01E02.avi")

    # -- TheTVDB lookups (mock API) ----------------------------------------------

    def test_tvdb_naming_and_images(self):
        self.sort(["Pioneer One Season 1 Episode 1.avi"], "--fetch-tv-images=NEW_SHOWS", *self.TVDB_RENAME)
        self.assertExists("TV/Pioneer One/Season 1/Pioneer One - S01E01 - Earthfall.avi")
        self.assertExists("TV/Pioneer One/Season 1/Pioneer One - S01E01 - Earthfall.tbn")
        for img in ("folder.jpg", "poster.jpg", "fanart.jpg", "banner.jpg", "season01.jpg", "Season 1/folder.jpg"):
            self.assertExists("TV/Pioneer One/" + img)
        self.assertTrue(os.path.isfile(self.p("TV/Pioneer One/Season 1/folder.jpg")))  # symlink resolves

    def test_show_title_formatting(self):
        self.sort(["pioneer.one.s01e02.avi"], "--fetch-tv-images=FALSE", *self.TVDB_RENAME)
        self.assertExists("TV/Pioneer One/Season 1/Pioneer One - S01E02 - The Man From Mars.avi")

    def test_substitution_with_tvdb(self):
        self.sort(["lalala 1x1.avi"], "--show-name-substitute=lalala-->Pioneer One", "--fetch-tv-images=FALSE",
                  *self.TVDB_RENAME)
        self.assertExists("TV/Pioneer One/Season 1/Pioneer One - S01E01 - Earthfall.avi")

    def test_custom_folder_name_with_tvdb_id(self):
        # a show-name-substitute is used as written; the tvdb-id-substitute keeps lookups (incl. air dates) working
        opts = ["--show-name-substitute=Pioneer One-->Pioneer.One.Custom",
                "--tvdb-id-substitute=Pioneer One Custom-->154521", "--fetch-tv-images=FALSE"] + self.TVDB_RENAME
        self.sort(["Pioneer.One.S01E01.avi", "Pioneer.One.2010.12.12.avi"], *opts)
        self.assertExists("TV/Pioneer.One.Custom/Season 1/Pioneer.One.Custom - S01E01 - Earthfall.avi")
        self.assertExists("TV/Pioneer.One.Custom/Season 1/Pioneer.One.Custom - S01E02 - The Man From Mars.avi")

    def test_tvdb_title_and_airdate_matches(self):
        for src in ("test/Pioneer One - Earthfall.avi", "test/Pioneer One 2010-06-16.avi",
                    "test/Pioneer One - 2010-06-16.avi"):
            with self.subTest(src=src):
                shutil.rmtree(self.p("TV"))
                os.makedirs(self.p("TV"))
                self.sort([src], "--match-files-based-on-tvdb-lookups=TRUE", "--fetch-tv-images=FALSE",
                          *self.TVDB_RENAME)
                self.assertExists("TV/Pioneer One/Season 1/Pioneer One - S01E01 - Earthfall.avi")

    def test_tvdb_id_substitute(self):
        self.sort(["test s1e1.avi"], "--tvdb-id-substitute:test-->83949", "--fetch-tv-images=FALSE",
                  *self.STD_RENAME)
        self.assertExists("TV/The Guild/Season 1/The Guild - S01E01.avi")

    def test_episode_name_required(self):
        self.sort(["Pioneer One Season 1 Episode 10.avi"], "--tvdb-episode-name-required=TRUE",
                  "--fetch-tv-images=FALSE", *self.TVDB_RENAME)
        self.assertNotExists("TV/Pioneer One/Season 1/Pioneer One - S01E10.avi")
        self.assertExists("sort/Pioneer One Season 1 Episode 10.avi")

    def test_no_api_key_falls_back(self):
        result = self.sort(["Pioneer One Season 1 Episode 1.avi", "RIP: A Remix Manifesto.avi"], *self.TVDB_RENAME,
                           network=False)
        self.assertIn("no tvdb-api-key", result.stderr)
        self.assertExists("TV/Pioneer One/Season 1/Pioneer One - S01E01.avi")
        self.assertExists("Misc/RIP- A Remix Manifesto.avi")

    # -- TMDb lookups (mock API) --------------------------------------------------

    def test_movie_into_subdirectory(self):
        self.sort(["RIP: A Remix Manifesto.avi"], "--rename-media=TRUE", "--fetch-movie-images=FALSE",
                  *self.MOVIE_RENAME)
        self.assertExists("Movies/RiP!- A Remix Manifesto 2009/RiP!- A Remix Manifesto (2009).avi")
        self.assertNotExists("Movies/RiP!- A Remix Manifesto 2009/folder.jpg")

    def test_movie_rename_format_quality_rating(self):
        self.sort(["RIP: A Remix Manifesto DVD.avi"], "--rename-movie-format=[MOVIE_TITLE] [YEAR2][QUALITY]",
                  "--rename-media=TRUE", "--fetch-movie-images=FALSE")
        self.assertExists("Movies/RiP!- A Remix Manifesto 2009 SD.avi")
        self.sort(["RIP: A Remix Manifesto.avi", "Night of the Living Dead 1968.avi"],
                  "--rename-movie-format=[MOVIE_TITLE] [YEAR2] [RATING]", "--rename-media=TRUE",
                  "--fetch-movie-images=FALSE")
        self.assertExists("Movies/RiP!- A Remix Manifesto 2009 NR.avi")
        self.assertExists("Movies/Night of the Living Dead 1968 R.avi")

    def test_movie_year_tolerance(self):
        expectations = {2011: False, 2010: True, 2009: True, 2008: True, 2007: False}
        for year, expected in expectations.items():
            with self.subTest(year=year):
                shutil.rmtree(self.p("Movies"))
                os.makedirs(self.p("Movies"))
                self.sort(["RIP: A Remix Manifesto %d.avi" % year], "--year-tolerance-for-error=1",
                          "--rename-media=TRUE", "--fetch-movie-images=FALSE", *self.MOVIE_RENAME)
                target = "Movies/RiP!- A Remix Manifesto 2009/RiP!- A Remix Manifesto (2009).avi"
                (self.assertExists if expected else self.assertNotExists)(target)

    def test_movie_without_renaming(self):
        self.sort(["RIP: A Remix Manifesto DVD.avi"], "--rename-media=FALSE", "--fetch-movie-images=FALSE")
        self.assertExists("Movies/RIP: A Remix Manifesto DVD.avi")

    def test_movie_images(self):
        self.sort(["RIP: A Remix Manifesto.avi"], "--rename-media=TRUE", "--fetch-movie-images=TRUE",
                  *self.MOVIE_RENAME)
        for img in ("fanart.jpg", "folder.jpg", "movie.tbn"):
            self.assertExists("Movies/RiP!- A Remix Manifesto 2009/" + img)
        self.sort(["RIP: A Remix Manifesto.mkv"], "--rename-movie-format=[MOVIE_TITLE] [YEAR2]",
                  "--rename-media=TRUE", "--fetch-movie-images=TRUE")
        for img in ("RiP!- A Remix Manifesto 2009.tbn", "RiP!- A Remix Manifesto 2009.jpg",
                    "RiP!- A Remix Manifesto 2009-fanart.jpg"):
            self.assertExists("Movies/" + img)

    def test_movie_directory(self):
        self.sort(["RIP: A Remix Manifesto/test.avi"], "--treat-directories=AS_FILES_TO_SORT", "--rename-media=TRUE",
                  "--fetch-movie-images=FALSE", *self.MOVIE_RENAME)
        self.assertExists("Movies/RiP!- A Remix Manifesto 2009/test.avi")


if __name__ == "__main__":
    unittest.main()
