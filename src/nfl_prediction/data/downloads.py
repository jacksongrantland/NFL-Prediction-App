"""Immutable raw blobs, verified cache hits, conditional requests, and bounded retries."""

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import uuid4

from nfl_prediction.data.audit import USER_AGENT, utc_now
from nfl_prediction.storage.database import Database

MAX_BYTES = 256 * 1024 * 1024


class IncompleteDownload(ValueError):
    """A truncated transfer can be retried without accepting partial bytes."""


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


@dataclass(frozen=True)
class Download:
    url: str
    path: str
    sha256: str
    size: int
    retrieved_at: str
    etag: str | None = None
    last_modified: str | None = None


class Downloader:
    _last_host_request: dict[str, float] = {}

    def __init__(self, root: Path, db: Database, *, request_interval: float = 0.5):
        self.root, self.db = root, db
        if not 0 <= request_interval <= 60:
            raise ValueError("Request interval must be between zero and 60 seconds")
        self.request_interval = request_interval
        self.memo: dict[str, Download] = {}
        self.downloaded_bytes = 0
        self.cache_hits = 0
        self.revalidated = 0

    def fetch(self, url: str, *, refresh: bool, force: bool = False) -> Download:
        if url in self.memo:
            return self.memo[url]
        cached = self.db.one(
            "SELECT metadata_json FROM download_cache WHERE url=:url", {"url": url}
        )
        previous = Download(**json.loads(cached["metadata_json"])) if cached else None
        if previous and (
            not Path(previous.path).is_file() or file_hash(Path(previous.path)) != previous.sha256
        ):
            raise ValueError(
                f"Raw cache integrity failure: {previous.path}; investigate before retry"
            )
        if previous and not refresh and not force:
            self.cache_hits += 1
            self.memo[url] = previous
            return previous
        headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
        if previous and not force:
            if previous.etag:
                headers["If-None-Match"] = previous.etag
            if previous.last_modified:
                headers["If-Modified-Since"] = previous.last_modified
        temporary = self.root / "raw" / f"{uuid4().hex}.part"
        temporary.parent.mkdir(parents=True, exist_ok=True)
        result = None
        for attempt in range(3):
            try:
                host = urlsplit(url).netloc
                delay = self.request_interval - (
                    time.monotonic() - self._last_host_request.get(host, 0)
                )
                if delay > 0:
                    time.sleep(delay)
                self._last_host_request[host] = time.monotonic()
                with urlopen(Request(url, headers=headers), timeout=45) as response:
                    digest, size = hashlib.sha256(), 0
                    with temporary.open("wb") as stream:
                        while chunk := response.read(1024 * 1024):
                            size += len(chunk)
                            if size > MAX_BYTES:
                                raise ValueError(f"Source exceeds {MAX_BYTES} byte limit: {url}")
                            digest.update(chunk)
                            stream.write(chunk)
                    expected = response.headers.get("Content-Length")
                    if not size or (expected and size != int(expected)):
                        raise IncompleteDownload(f"Incomplete download: {url}")
                    sha = digest.hexdigest()
                    suffix = ".csv" if url.endswith(".csv") else ".parquet"
                    path = self.root / "raw" / "blobs" / f"{sha}{suffix}"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.exists():
                        if file_hash(path) != sha:
                            raise ValueError(f"Existing immutable blob is corrupt: {path}")
                        temporary.unlink()
                    else:
                        os.replace(temporary, path)
                    result = Download(
                        url,
                        str(path.resolve()),
                        sha,
                        size,
                        utc_now(),
                        response.headers.get("ETag"),
                        response.headers.get("Last-Modified"),
                    )
                    self.downloaded_bytes += size
                break
            except HTTPError as error:
                if error.code == 304 and previous:
                    self.revalidated += 1
                    result = previous
                    break
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise
                time.sleep(2**attempt)
            except (URLError, TimeoutError, ConnectionError, IncompleteRead, IncompleteDownload):
                if attempt == 2:
                    raise
                time.sleep(2**attempt)
            finally:
                temporary.unlink(missing_ok=True)
        if result is None:
            raise RuntimeError(f"Download failed: {url}")
        self.db.execute(
            "INSERT INTO download_cache(url, metadata_json) VALUES (:url, :metadata) "
            "ON CONFLICT(url) DO UPDATE SET metadata_json=excluded.metadata_json",
            {"url": url, "metadata": json.dumps(asdict(result))},
        )
        self.memo[url] = result
        return result
