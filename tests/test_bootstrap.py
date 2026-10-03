import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.bootstrap import (
    DEPOTDOWNLOADER_SHA256,
    DEPOTDOWNLOADER_VERSION,
    ensure_download,
)


class CacheTests(unittest.TestCase):
    def test_verified_cache_never_downloads(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cached'
            path.write_bytes(b'verified')
            with patch('urllib.request.urlopen', side_effect=AssertionError('network used')):
                ensure_download('https://example.invalid', path, hashlib.sha256(b'verified').hexdigest())

    def test_corrupt_download_does_not_replace_target(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'cached'
            path.write_bytes(b'old')
            from io import BytesIO
            with patch('urllib.request.urlopen', return_value=BytesIO(b'wrong')):
                with self.assertRaises(RuntimeError):
                    ensure_download('https://example.invalid', path, hashlib.sha256(b'verified').hexdigest())
            self.assertEqual(path.read_bytes(), b'old')
            self.assertFalse(path.with_suffix('.partial').exists())

    def test_depotdownloader_release_is_version_and_hash_pinned(self):
        self.assertEqual(DEPOTDOWNLOADER_VERSION, '3.4.0')
        self.assertEqual(DEPOTDOWNLOADER_SHA256,
                         '41c9e9f0df54b3ad02e67a11726756e5c73283bd7c2e1b04acfa5ae4c2ed3767')
