"""Local, model-free separation by repetition and stereo centre extraction.

This is a classical DSP baseline, inspired by the REPET principle: similar
musical frames share accompaniment, while non-repeating foreground is retained.
No pretrained weights, external separator, or network calls are used.
"""
from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import istft, resample_poly, stft

MAX_SECONDS = 600
ANALYSIS_RATE = 22050
FFT_SIZE = 2048
HOP = 512


def _resample(audio: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return audio
    divisor = math.gcd(source_rate, target_rate)
    return resample_poly(audio, target_rate // divisor, source_rate // divisor, axis=0).astype(np.float32)


def _features(magnitude: np.ndarray, frequencies: np.ndarray) -> np.ndarray:
    # Coarse log bands make neighbour selection less sensitive to single peaks.
    edges = np.geomspace(60, ANALYSIS_RATE / 2, 65)
    features = np.zeros((64, magnitude.shape[1]), dtype=np.float32)
    for index, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        band = (frequencies >= lo) & (frequencies < hi)
        if np.any(band):
            features[index] = np.sqrt(np.mean(magnitude[band], axis=0))
    features /= np.maximum(np.linalg.norm(features, axis=0, keepdims=True), 1e-10)
    return features.T


def _foreground_mask(magnitude: np.ndarray, frequencies: np.ndarray,
                     progress: Callable[[str], None]) -> np.ndarray:
    count = magnitude.shape[1]
    features = _features(magnitude, frequencies)
    # Bound pairwise search and the median workspace for long songs.
    candidates = np.unique(np.linspace(0, count - 1, min(count, 1500), dtype=int))
    candidate_features = features[candidates]
    exclusion = min(2.0, count * HOP / ANALYSIS_RATE / 8) * ANALYSIS_RATE / HOP
    mask = np.zeros_like(magnitude, dtype=np.float32)
    neighbours = 20
    last_percent = -1
    for start in range(0, count, 32):
        stop = min(start + 32, count)
        similarity = features[start:stop] @ candidate_features.T
        nearby = np.abs(np.arange(start, stop)[:, None] - candidates[None, :]) <= exclusion
        similarity[nearby] = -np.inf
        for local, frame in enumerate(range(start, stop)):
            valid = np.flatnonzero(np.isfinite(similarity[local]))
            if len(valid):
                k = min(neighbours, len(valid))
                selected = valid[np.argpartition(similarity[local, valid], -k)[-k:]]
                background = np.median(magnitude[:, candidates[selected]], axis=1)
            else:
                background = np.median(magnitude, axis=1)
            background = np.minimum(background, magnitude[:, frame])
            foreground = np.maximum(magnitude[:, frame] - background, 0)
            # Soft Wiener-style mask: avoid hard spectral holes and musical noise.
            numerator = foreground * foreground
            mask[:, frame] = numerator / (numerator + background * background + 1e-12)
        percent = int(stop / count * 100)
        if percent // 10 != last_percent // 10:
            progress(f'Ищем повторяющийся аккомпанемент… {percent}%')
            last_percent = percent
    return median_filter(mask, size=(3, 3), mode='nearest')


def separate(audio: np.ndarray, sample_rate: int,
             progress: Callable[[str], None] = lambda message: None) -> tuple[np.ndarray, np.ndarray]:
    """Return (vocals, accompaniment) at original rate, length and channel count.

    Vocals are assumed to be near the stereo centre and less repetitive than
    accompaniment. Mono input uses repetition alone. Output stems sum to input
    within floating-point error; neither stem is independently normalized.
    """
    source = np.asarray(audio, dtype=np.float32)
    mono = source.ndim == 1
    if mono:
        source = source[:, None]
    if source.ndim != 2 or source.shape[1] not in (1, 2):
        raise ValueError('Поддерживаются моно и стерео записи.')
    if sample_rate < 8000 or not len(source) or not np.all(np.isfinite(source)):
        raise ValueError('Некорректные аудиоданные или частота дискретизации.')
    if len(source) / sample_rate > MAX_SECONDS:
        raise ValueError('Пока поддерживаются песни длительностью до 10 минут.')
    progress('Анализируем спектр и стереопанораму…')
    analysis = _resample(source, sample_rate, ANALYSIS_RATE)
    original_length = len(analysis)
    if len(analysis) < FFT_SIZE:
        analysis = np.pad(analysis, ((0, FFT_SIZE - len(analysis)), (0, 0)))
    middle = np.mean(analysis, axis=1)
    frequencies, _, spectrum = stft(middle, fs=ANALYSIS_RATE, nperseg=FFT_SIZE,
                                    noverlap=FFT_SIZE - HOP, boundary='zeros', padded=True)
    magnitude = np.abs(spectrum)
    mask = _foreground_mask(magnitude, frequencies, progress)
    if source.shape[1] == 2:
        side = (analysis[:, 0] - analysis[:, 1]) * .5
        _, _, side_spectrum = stft(side, fs=ANALYSIS_RATE, nperseg=FFT_SIZE,
                                  noverlap=FFT_SIZE - HOP, boundary='zeros', padded=True)
        # Hard-panned instruments have equal mid and side power; centred voice
        # has little side power. A soft gate also permits moderate vocal reverb.
        centre = np.clip(1 - (np.abs(side_spectrum) / np.maximum(magnitude, 1e-8)) ** 2, 0, 1)
        mask *= centre
    # Protect sub-bass and the very top end from being assigned to the voice.
    band = np.clip((frequencies - 45) / 40, 0, 1) * np.clip((11025 - frequencies) / 1800, 0, 1)
    mask *= band[:, None]
    progress('Собираем вокал и минус…')
    _, foreground = istft(spectrum * mask, fs=ANALYSIS_RATE, nperseg=FFT_SIZE,
                          noverlap=FFT_SIZE - HOP, boundary=True)
    foreground = _resample(foreground[:original_length], ANALYSIS_RATE, sample_rate)
    foreground = np.pad(foreground, (0, max(0, len(source) - len(foreground))))[:len(source)]
    vocals = np.repeat(foreground[:, None], source.shape[1], axis=1)
    accompaniment = source - vocals
    return (vocals[:, 0], accompaniment[:, 0]) if mono else (vocals, accompaniment)
