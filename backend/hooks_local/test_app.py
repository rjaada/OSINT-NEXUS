import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from fastapi import HTTPException

class MediaBoundaryTests(unittest.TestCase):
    def test_local_media_with_url_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'video.mp4';path.write_bytes(b'test')
            with patch.object(app,'MEDIA_ROOT',Path(tmp)), patch.object(app,'_deepfake_baseline',return_value={'label':'unverified'}):
                asyncio.run(app.deepfake_hook(app.HookRequest(media_path=str(path),media_url='https://example.test/video')))
            self.assertTrue(path.exists())

    def test_local_path_outside_media_root_rejected(self):
        with self.assertRaises(HTTPException) as error:
            asyncio.run(app._resolve_media(app.HookRequest(media_path='/etc/passwd')))
        self.assertEqual(error.exception.status_code,400)

    def test_dns_resolving_to_private_address_rejected(self):
        with patch.object(app.socket,'getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',80))]):
            with self.assertRaises(HTTPException):app._validate_url('https://example.test/video')

    def test_temporary_ownership_requires_directory_and_prefix(self):
        self.assertFalse(app._is_temporary_download(Path('/data/media/video.mp4')))
        self.assertTrue(app._is_temporary_download(Path(tempfile.gettempdir())/'nexus-hook-test.mp4'))

    def test_oversized_download_is_rejected_and_temporary_file_removed(self):
        import httpx
        client=httpx.AsyncClient(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=b'12345')))
        with tempfile.TemporaryDirectory() as tmp, patch.object(app.tempfile,'tempdir',tmp), patch.object(app,'_validate_url'), patch.object(app.httpx,'AsyncClient',return_value=client), patch.object(app,'MAX_DOWNLOAD_BYTES',4):
            with self.assertRaises(HTTPException) as error:
                asyncio.run(app._resolve_media(app.HookRequest(media_url='https://example.test/video.mp4')))
            self.assertEqual(error.exception.status_code,413)
            self.assertEqual(list(Path(tmp).iterdir()),[])
