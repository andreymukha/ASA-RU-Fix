import hashlib
import errno
import urllib.error
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.bootstrap import (
    DEPOTDOWNLOADER_SHA256,
    DEPOTDOWNLOADER_VERSION,
    ensure_download,
    is_transient_network_error,
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


class NetworkClassificationTests(unittest.TestCase):
    def test_only_specific_network_errors_are_transient(self):
        for error in (TimeoutError('timed out'), ConnectionResetError('reset'),
                      urllib.error.URLError(TimeoutError('timed out')),
                      OSError(errno.ECONNREFUSED, 'connection refused'),
                      RuntimeError('BOOTSTRAP ERROR: [WinError 10060]'),
                      RuntimeError('DepotDownloader failed: System.Net.Sockets.SocketException (10060)')):
            with self.subTest(error=error):
                self.assertTrue(is_transient_network_error(error))
        for code in (429, 500, 502, 503, 504):
            self.assertTrue(is_transient_network_error(urllib.error.HTTPError('url', code, 'error', {}, None)))
        for error in (RuntimeError('BOOTSTRAP ERROR: unknown'), RuntimeError('compiler timeout'),
                      FileNotFoundError('cl.exe'), PermissionError('access denied'),
                      urllib.error.URLError('certificate verify failed')):
            with self.subTest(error=error):
                self.assertFalse(is_transient_network_error(error))
        for code in (400, 401, 403, 404, 501):
            self.assertFalse(is_transient_network_error(urllib.error.HTTPError('url', code, 'error', {}, None)))

    def test_final_error_takes_precedence_over_old_network_diagnostics(self):
        self.assertFalse(is_transient_network_error(RuntimeError(
            'retry [WinError 10060] recovered\nBOOTSTRAP ERROR: ooz compiler failed')))

    def test_integrity_failure_is_never_a_network_retry(self):
        self.assertFalse(is_transient_network_error(RuntimeError(
            'SHA-256 mismatch: old diagnostic [WinError 10060]')))
