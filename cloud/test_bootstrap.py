import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bootstrap import download_archive, install_archive


class BundleChecks(unittest.TestCase):
    def test_https_download_preserves_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary, patch('bootstrap.urlopen',return_value=io.BytesIO(b'verified bytes')) as network:
            target=Path(temporary)/'package.zip'
            download_archive('https://assets.example/package.zip',target,{'bytes':14})
            self.assertEqual(target.read_bytes(),b'verified bytes')
            self.assertEqual(network.call_args.args[0].full_url,'https://assets.example/package.zip')

    def test_insecure_and_credential_urls_never_download(self):
        with patch('bootstrap.urlopen') as network:
            for url in ('http://assets.example/package.zip','https://user:password@assets.example/package.zip'):
                with self.assertRaises(ValueError):download_archive(url,Path('/unused'),{'bytes':1})
            network.assert_not_called()

    def test_incomplete_and_oversized_downloads_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            for payload in (b'ab',b'abcdef'):
                with self.subTest(payload=payload),patch('bootstrap.urlopen',return_value=io.BytesIO(payload)):
                    with self.assertRaises(ValueError):download_archive('https://assets.example/package.zip',Path(temporary)/'package.zip',{'bytes':3})

    def test_wrong_hash_is_rejected_before_extraction(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);archive=root/'package.zip';archive.write_bytes(b'abc')
            with self.assertRaisesRegex(ValueError,'SHA-256'):
                install_archive(archive,root/'installed',{'bytes':3,'sha256':'0'*64})
            self.assertFalse((root/'installed').exists())


if __name__=='__main__':unittest.main(verbosity=2)
