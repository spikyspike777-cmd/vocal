import io
import json

import numpy as np
import pytest

from vocalstudio import lyrics_online, neural


def test_spectral_front_end_round_trip():
    t = np.arange(neural.CHUNK) / neural.MODEL_RATE
    chunk = np.stack([.3 * np.sin(2 * np.pi * 440 * t), .2 * np.sin(2 * np.pi * 3000 * t)]).astype(np.float32)
    planes = neural._stft(chunk)
    assert planes.shape == (1, 4, neural.DIM_F, neural.DIM_T)
    restored = neural._istft(planes)
    assert restored.shape == chunk.shape
    inner = slice(neural.TRIM, -neural.TRIM)
    assert np.max(np.abs(restored[:, inner] - chunk[:, inner])) < 1e-4


def test_separation_stitches_chunks_with_a_stub_model(monkeypatch):
    class Identity:
        def get_inputs(self):
            return [type('Input', (), {'name': 'input'})()]

        def run(self, names, feed):
            return [feed['input'] * .5]

    monkeypatch.setattr(neural, '_session', lambda path: Identity())
    rate = neural.MODEL_RATE
    t = np.arange(int(rate * 7.3)) / rate  # spans two model chunks
    mix = np.column_stack([.3 * np.sin(2 * np.pi * 330 * t), .3 * np.sin(2 * np.pi * 550 * t)]).astype(np.float32)
    messages = []
    vocals, backing = neural.separate(mix, rate, 'unused.onnx', messages.append)
    assert vocals.shape == backing.shape == mix.shape
    inner = slice(rate // 2, -rate // 2)
    np.testing.assert_allclose(vocals[inner], mix[inner] * .5 * neural.COMPENSATE, atol=2e-3)
    np.testing.assert_allclose(vocals + backing, mix, atol=1e-6)
    assert messages[-1].endswith('100%')
    with pytest.raises(ValueError):
        neural.separate(mix[:, 0], rate, 'unused.onnx')


def test_corrupt_model_download_is_rejected(tmp_path, monkeypatch):
    class Response(io.BytesIO):
        headers = {'Content-Length': '4'}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(neural.urllib.request, 'urlopen', lambda request, timeout: Response(b'oops'))
    with pytest.raises(RuntimeError, match='повреждён'):
        neural.ensure_model(tmp_path)
    assert not list(tmp_path.iterdir())


def test_online_lyrics_prefers_synced_results(monkeypatch):
    payload = [
        {'trackName': 'A', 'artistName': 'X', 'duration': 100, 'plainLyrics': 'plain', 'syncedLyrics': None},
        {'trackName': 'B', 'artistName': 'Y', 'duration': 120, 'plainLyrics': 'p', 'syncedLyrics': '[00:01.00]s'},
        {'trackName': 'C', 'artistName': 'Z', 'duration': 90, 'plainLyrics': None, 'syncedLyrics': None},
    ]

    class Response(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    seen = {}

    def fake(request, timeout):
        seen['url'] = request.full_url
        return Response(json.dumps(payload).encode())

    monkeypatch.setattr(lyrics_online.urllib.request, 'urlopen', fake)
    results = lyrics_online.search('  X A ')
    assert seen['url'].endswith('q=X+A')
    assert [item['title'] for item in results] == ['B', 'A']
    assert results[0]['synced'] and results[0]['lyrics'] == '[00:01.00]s'
    assert lyrics_online.search('  ') == []
