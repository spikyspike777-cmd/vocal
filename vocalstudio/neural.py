"""Neural vocal separation with an MDX-Net model executed by ONNX Runtime.

The model file (about 64 MB) is downloaded once and cached; after that the
separation runs fully offline. PyTorch is not required. The spectral front-end
(STFT/ISTFT) is implemented here with NumPy so that the only runtime
dependency is ``onnxruntime``.
"""
from __future__ import annotations

import hashlib
import os
import urllib.request
from collections.abc import Callable
from pathlib import Path

import numpy as np

MODEL_NAME = 'Kim_Vocal_2.onnx'
MODEL_URL = 'https://github.com/TRvlvr/model_repo/releases/download/all_public_uvr_models/Kim_Vocal_2.onnx'
MODEL_SHA256 = 'ce74ef3b6a6024ce44211a07be9cf8bc6d87728cc852a68ab34eb8e58cde9c8b'
MODEL_RATE = 44100
N_FFT = 7680
HOP = 1024
DIM_F = 3072
DIM_T = 256
# Published gain correction for this checkpoint.
COMPENSATE = 1.009

CHUNK = HOP * (DIM_T - 1)
TRIM = N_FFT // 2
STEP = CHUNK - 2 * TRIM


def available() -> bool:
    try:
        import onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


def model_file(models: Path) -> Path:
    return Path(models) / MODEL_NAME


def _digest(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            sha.update(block)
    return sha.hexdigest()


def ensure_model(models: Path, progress: Callable[[str], None] = lambda message: None) -> Path:
    """Return the cached model path, downloading and verifying it when missing."""
    target = model_file(models)
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix('.part')
    progress('Скачиваем модель разделения (один раз, 64 МБ)… 0%')
    try:
        request = urllib.request.Request(MODEL_URL, headers={'User-Agent': 'VocalStudio'})
        with urllib.request.urlopen(request, timeout=60) as response, open(partial, 'wb') as output:
            total = int(response.headers.get('Content-Length') or 0)
            done, shown = 0, -1
            while block := response.read(1 << 18):
                output.write(block)
                done += len(block)
                percent = int(done * 100 / total) if total else 0
                if percent != shown:
                    progress(f'Скачиваем модель разделения (один раз, 64 МБ)… {percent}%')
                    shown = percent
        if _digest(partial) != MODEL_SHA256:
            raise RuntimeError('Файл модели повреждён при загрузке.')
        os.replace(partial, target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return target


def _session(path: Path):
    import onnxruntime as ort
    preferred = ['CUDAExecutionProvider', 'DmlExecutionProvider', 'CoreMLExecutionProvider', 'CPUExecutionProvider']
    providers = [name for name in preferred if name in ort.get_available_providers()]
    options = ort.SessionOptions()
    options.log_severity_level = 3
    try:
        return ort.InferenceSession(str(path), sess_options=options, providers=providers)
    except Exception:
        return ort.InferenceSession(str(path), sess_options=options, providers=['CPUExecutionProvider'])


_WINDOW = None
_NORMALISER = None


def _window():
    global _WINDOW, _NORMALISER
    if _WINDOW is None:
        _WINDOW = (.5 - .5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)
        total = np.zeros(CHUNK + N_FFT, dtype=np.float32)
        for frame in range(DIM_T):
            total[frame * HOP:frame * HOP + N_FFT] += _WINDOW ** 2
        _NORMALISER = np.maximum(total[TRIM:TRIM + CHUNK], 1e-8)
    return _WINDOW, _NORMALISER


def _stft(chunk: np.ndarray) -> np.ndarray:
    """(2, CHUNK) waveform -> (1, 4, DIM_F, DIM_T) real/imaginary planes."""
    window, _ = _window()
    padded = np.pad(chunk, ((0, 0), (TRIM, TRIM)), mode='reflect')
    index = np.arange(N_FFT)[None, :] + HOP * np.arange(DIM_T)[:, None]
    spectrum = np.fft.rfft(padded[:, index] * window, axis=-1)[:, :, :DIM_F]  # (2, T, F)
    planes = np.stack((spectrum.real, spectrum.imag), axis=1)  # (2, 2, T, F)
    return planes.reshape(1, 4, DIM_T, DIM_F).transpose(0, 1, 3, 2).astype(np.float32)


def _istft(planes: np.ndarray) -> np.ndarray:
    """(1, 4, DIM_F, DIM_T) planes -> (2, CHUNK) waveform."""
    window, normaliser = _window()
    data = planes.transpose(0, 1, 3, 2).reshape(2, 2, DIM_T, DIM_F)
    spectrum = np.zeros((2, DIM_T, N_FFT // 2 + 1), dtype=np.complex64)
    spectrum[:, :, :DIM_F] = data[:, 0] + 1j * data[:, 1]
    frames = np.fft.irfft(spectrum, n=N_FFT, axis=-1).astype(np.float32) * window
    output = np.zeros((2, CHUNK + N_FFT), dtype=np.float32)
    for frame in range(DIM_T):
        output[:, frame * HOP:frame * HOP + N_FFT] += frames[:, frame]
    return output[:, TRIM:TRIM + CHUNK] / normaliser


def separate(audio: np.ndarray, sample_rate: int, model: Path,
             progress: Callable[[str], None] = lambda message: None) -> tuple[np.ndarray, np.ndarray]:
    """Return (vocals, accompaniment) for stereo 44.1 kHz float audio shaped (n, 2)."""
    source = np.asarray(audio, dtype=np.float32)
    if source.ndim != 2 or source.shape[1] != 2 or sample_rate != MODEL_RATE:
        raise ValueError('Нейросеть ожидает стерео 44,1 кГц.')
    if not len(source) or not np.all(np.isfinite(source)):
        raise ValueError('Некорректные аудиоданные.')
    session = _session(Path(model))
    name = session.get_inputs()[0].name
    length = len(source)
    count = -(-length // STEP)
    mixture = np.zeros((2, TRIM + count * STEP + TRIM), dtype=np.float32)
    mixture[:, TRIM:TRIM + length] = source.T
    vocals = np.zeros((2, count * STEP), dtype=np.float32)
    progress('Нейросеть отделяет вокал… 0%')
    for index in range(count):
        chunk = mixture[:, index * STEP:index * STEP + CHUNK]
        if np.max(np.abs(chunk)) > 1e-5:
            result = session.run(None, {name: _stft(chunk)})[0]
            vocals[:, index * STEP:(index + 1) * STEP] = _istft(result)[:, TRIM:TRIM + STEP]
        progress(f'Нейросеть отделяет вокал… {int((index + 1) * 100 / count)}%')
    voice = (vocals[:, :length] * COMPENSATE).T
    return np.ascontiguousarray(voice), source - voice
