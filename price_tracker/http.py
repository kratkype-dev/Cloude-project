"""Tiny polite JSON HTTP client (stdlib only)."""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "cs-CZ,cs;q=0.9",
}


class Http:
    def __init__(self, base_url, delay=0.7, retries=4, timeout=30):
        self.base_url = base_url
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self._last = 0.0

    def url(self, path, params=None):
        url = urllib.parse.urljoin(self.base_url, path)
        if params:
            sep = "&" if "?" in url else "?"
            url += sep + urllib.parse.urlencode(params, doseq=True)
        return url

    def get_json(self, path, params=None):
        url = self.url(path, params)
        for attempt in range(self.retries + 1):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                req = urllib.request.Request(url, headers=HEADERS)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                if e.code < 500 and e.code != 429:
                    raise
                err = e
            except (urllib.error.URLError, TimeoutError) as e:
                err = e
            if attempt < self.retries:
                backoff = 2 ** (attempt + 1)
                log.warning("GET %s failed (%s), retry in %ss", url, err, backoff)
                time.sleep(backoff)
        raise err
