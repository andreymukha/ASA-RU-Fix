import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.iostore_companions import write_companions


class IoStoreCompanionTests(unittest.TestCase):
    def test_emits_verified_sidecars_next_to_custom_pak_without_changing_pak(self):
        with tempfile.TemporaryDirectory() as folder:
            pak = Path(folder) / 'custom_P.pak'
            original = b'locres patch'
            pak.write_bytes(original)
            expected = {
                'custom_P.utoc': {'size': 202, 'sha256': '4cf47c360360ed970df26b1db1c83072f3035a33f4b98e6cbb6d3d09d195c353'},
                'custom_P.ucas': {'size': 64, 'sha256': '81cf60aca4403cb235e1f34e43c2cb7b4a0d8f3540d2c27b43d30f7286c43425'},
            }
            self.assertEqual(write_companions(pak), expected)
            for name, record in expected.items():
                raw = pak.with_name(name).read_bytes()
                self.assertEqual(len(raw), record['size'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'])
            self.assertEqual(pak.read_bytes(), original)
            self.assertEqual(write_companions(pak), expected)

    def test_invalid_payload_is_rejected_before_writing_either_sidecar(self):
        with tempfile.TemporaryDirectory() as folder:
            pak = Path(folder) / 'ASA_RU_Fix_P.pak'
            pak.write_bytes(b'locres patch')
            with patch('tools.iostore_companions.UCAS', b'\0' * 64):
                with self.assertRaisesRegex(RuntimeError, 'UCAS'):
                    write_companions(pak)
            self.assertEqual(list(pak.parent.iterdir()), [pak])

    def test_rejects_output_suffix_that_would_alias_a_companion(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'ASA_RU_Fix_P.utoc'
            output.write_bytes(b'keep me')
            with self.assertRaisesRegex(ValueError, 'PAK'):
                write_companions(output)
            self.assertEqual(output.read_bytes(), b'keep me')


if __name__ == '__main__':
    unittest.main()
