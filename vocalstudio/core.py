from __future__ import annotations

import json
import math
import re
import uuid
from pathlib import Path

import numpy as np
from scipy.signal import resample_poly


def atomic_json(path: Path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def create_project(root: Path, source: Path, lyrics: str) -> Path:
    folder = root / uuid.uuid4().hex
    folder.mkdir(parents=True)
    atomic_json(folder / 'project.json', {
        'version': 1, 'title': source.stem, 'source': str(source.resolve()),
        'lyrics': lyrics, 'lines': parse_lyrics(lyrics), 'state': 'new',
    })
    return folder


def parse_lyrics(text: str) -> list[dict]:
    result = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        matches = list(re.finditer(r'\[(\d+):(\d{2}(?:\.\d+)?)\]', raw))
        if matches:
            label = re.sub(r'\[\d+:\d{2}(?:\.\d+)?\]', '', raw).strip()
            for match in matches:
                result.append({'text': label, 'time': int(match[1]) * 60 + float(match[2])})
        elif not re.match(r'^\[(?:ar|ti|al|by|offset):', raw, re.I):
            result.append({'text': raw, 'time': None})
    return result


def active_line(lines: list[dict], position: float) -> int | None:
    candidates = [(float(line['time']), i) for i, line in enumerate(lines)
                  if line.get('time') is not None and float(line['time']) <= position]
    return max(candidates)[1] if candidates else None


def note_name(midi: float | None) -> str:
    if midi is None or not math.isfinite(midi):
        return '—'
    value = round(midi)
    return ('C', 'C♯', 'D', 'D♯', 'E', 'F', 'F♯', 'G', 'G♯', 'A', 'A♯', 'B')[value % 12] + str(value // 12 - 1)


def cents_error(actual: float, target: float, octave_flexible: bool = False) -> float:
    delta = actual - target
    if octave_flexible:
        delta = (delta + 6) % 12 - 6
    return delta * 100


def detect_pitch(samples: np.ndarray, sample_rate: int, floor=65., ceiling=1000.) -> tuple[float | None, float]:
    """YIN difference function using FFT, returning fractional MIDI and confidence."""
    x = np.asarray(samples, dtype=np.float64)
    if len(x) < sample_rate / floor * 2 or np.sqrt(np.mean(x * x)) < .008:
        return None, 0.
    x = x - np.mean(x)
    n = len(x)
    low = max(2, int(sample_rate / ceiling))
    high = min(n // 2, int(sample_rate / floor))
    fft = np.fft.rfft(x, n=2 ** int(np.ceil(np.log2(2 * n))))
    correlation = np.fft.irfft(fft * np.conj(fft))[:high + 1]
    energy = np.concatenate(([0.], np.cumsum(x * x)))
    shifts = np.arange(high + 1)
    difference = np.maximum(0., energy[n - shifts] + energy[n] - energy[shifts] - 2 * correlation)
    normalized = np.ones(high + 1)
    normalized[1:] = difference[1:] * np.arange(1, high + 1) / np.maximum(np.cumsum(difference[1:]), 1e-12)
    candidates = np.flatnonzero(normalized[low:high] < .15)
    if not len(candidates):
        return None, 0.
    lag = low + int(candidates[0])
    while lag + 1 < high and normalized[lag + 1] < normalized[lag]:
        lag += 1
    confidence = float(1 - normalized[lag])
    offset = 0.
    if 0 < lag < high:
        a, b, c = normalized[lag - 1:lag + 2]
        denominator = a - 2 * b + c
        if abs(denominator) > 1e-12:
            offset = float(np.clip(.5 * (a - c) / denominator, -.5, .5))
    frequency = sample_rate / (lag + offset)
    return float(69 + 12 * np.log2(frequency / 440)), confidence


def extract_reference(audio: np.ndarray, sample_rate: int) -> dict:
    if audio.ndim == 2:
        audio = np.mean(audio, axis=1)
    divisor = math.gcd(sample_rate, 16000)
    mono = resample_poly(audio, 16000 // divisor, sample_rate // divisor)
    window, hop = 1024, 320
    times, notes, confidence = [], [], []
    padded = np.pad(mono, (window // 2, window // 2))
    for start in range(0, len(mono), hop):
        midi, certainty = detect_pitch(padded[start:start + window], 16000)
        times.append(round(start / 16000, 4))
        notes.append(midi)
        confidence.append(certainty)
    return {'times': times, 'midi': notes, 'confidence': confidence}
