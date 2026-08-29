"""The media-storage seam: `save()` writes to disk and both methods hand back
a `/media/...` URL. The nginx `location /media/` block (not exercised here)
serves those files directly."""

from __future__ import annotations

import io

import pytest

from app.storage import LocalMediaStorage


def test_save_writes_the_bytes_and_returns_the_media_url(tmp_path):
    store = LocalMediaStorage(tmp_path)

    url = store.save("topics/integers/number-line.png", io.BytesIO(b"PNGDATA"))

    assert url == "/media/topics/integers/number-line.png"
    assert (tmp_path / "topics" / "integers" / "number-line.png").read_bytes() == b"PNGDATA"


def test_get_url_maps_a_key_onto_the_media_prefix(tmp_path):
    store = LocalMediaStorage(tmp_path)
    assert store.get_url("a/b.png") == "/media/a/b.png"
    assert store.get_url("/a/b.png") == "/media/a/b.png"  # leading slash tolerated


@pytest.mark.parametrize("bad_key", ["../secrets.txt", "a/../../b.png", "..", "/"])
def test_traversal_keys_are_rejected(tmp_path, bad_key):
    store = LocalMediaStorage(tmp_path)
    with pytest.raises(ValueError):
        store.save(bad_key, io.BytesIO(b"x"))
