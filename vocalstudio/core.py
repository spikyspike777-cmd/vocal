from __future__ import annotations

import bisect
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


def create_project(root: Path, source: Path, lyrics: str, title: str = '') -> Path:
    folder = root / uuid.uuid4().hex
    folder.mkdir(parents=True)
    atomic_json(folder / 'project.json', {
        'version': 2, 'title': title.strip() or source.stem, 'source': str(source.resolve()),
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
            label = re.sub(r'\[\d+:\d{2}(?:\.\d+)?\]|<\d+:\d{2}(?:\.\d+)?>', '', raw).strip()
            for match in matches:
                result.append({'text': label, 'time': int(match[1]) * 60 + float(match[2])})
        elif not re.match(r'^\[(?:ar|ti|al|au|by|re|ve|la|length|offset|id)\s*:', raw, re.I):
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


def _clean_track(pitch: np.ndarray) -> np.ndarray:
    """Remove isolated blips and octave slips from a frame-wise pitch track (NaN = unvoiced)."""
    track = pitch.copy()
    voiced = np.isfinite(track)
    # Octave slips: a short run that sits ~12 semitones away from both neighbours.
    for i in range(1, len(track) - 1):
        if voiced[i] and voiced[i - 1]:
            jump = track[i] - track[i - 1]
            if abs(abs(jump) - 12) < 1.2:
                track[i] -= 12 * np.sign(jump)
    # Median over 5 frames, computed on voiced neighbours only.
    smooth = track.copy()
    for i in np.flatnonzero(voiced):
        window = track[max(0, i - 2):i + 3]
        window = window[np.isfinite(window)]
        if len(window) >= 3:
            smooth[i] = np.median(window)
    # Drop voiced islands shorter than 5 frames.
    i = 0
    while i < len(smooth):
        if np.isfinite(smooth[i]):
            j = i
            while j < len(smooth) and np.isfinite(smooth[j]):
                j += 1
            if j - i < 5:
                smooth[i:j] = np.nan
            i = j
        else:
            i += 1
    return smooth


def tuning_offset(pitch: np.ndarray) -> float:
    """Circular mean deviation from equal temperament, in semitones (-0.5..0.5)."""
    values = pitch[np.isfinite(pitch)]
    if not len(values):
        return 0.
    angle = 2 * np.pi * (values - np.round(values))
    return float(np.arctan2(np.mean(np.sin(angle)), np.mean(np.cos(angle))) / (2 * np.pi))


def segment_notes(times, pitch, step: float, minimum: float = .09) -> list[dict]:
    """Group a cleaned pitch track into notes snapped to the song's own semitone grid."""
    pitch = np.asarray([np.nan if p is None else p for p in pitch], dtype=np.float64)
    offset = tuning_offset(pitch)
    raw, current = [], []
    def close():
        if current:
            raw.append((times[current[0]], times[current[-1]] + step, float(np.median(pitch[current]))))
            current.clear()
    for i, value in enumerate(pitch):
        if not np.isfinite(value):
            if current and times[i] - times[current[-1]] > 2.5 * step:
                close()
            continue
        if current and abs(value - np.median(pitch[current[-12:]])) > .7:
            close()
        current.append(i)
    close()
    notes = []
    for start, end, value in raw:
        midi = round(value - offset) + offset
        if notes and abs(notes[-1]['midi'] - midi) < 1e-6 and start - notes[-1]['end'] < .07:
            notes[-1]['end'] = round(end, 3)
        else:
            notes.append({'start': round(start, 3), 'end': round(end, 3), 'midi': round(midi, 3)})
    return [note for note in notes if note['end'] - note['start'] >= minimum]


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
    track = _clean_track(np.asarray([np.nan if p is None else p for p in notes], dtype=np.float64))
    midi = [float(round(p, 3)) if np.isfinite(p) else None for p in track]
    return {'times': times, 'midi': midi, 'confidence': confidence,
            'notes': segment_notes(times, midi, hop / 16000)}


def note_at(notes: list[dict], starts: list[float], position: float) -> int | None:
    index = bisect.bisect_right(starts, position) - 1
    return index if index >= 0 and position < notes[index]['end'] else None


_VOWELS = set('аеёиоуыэюяaeiouyієїў')


def syllables(text: str) -> int:
    return max(1, sum(1 for char in text.lower() if char in _VOWELS))


def auto_align(lines: list[dict], notes: list[dict], duration: float) -> list[dict]:
    """Estimate start times for untimed lyric lines from the vocal melody.

    Sung syllables roughly follow note onsets, so every line starts at the note
    whose index matches the share of syllables before it, snapped to the nearest
    phrase start (a note after a pause). Lines that already have a time are kept.
    The result is an approximation meant to be corrected by tapping.
    """
    result = [dict(line) for line in lines]
    pending = [i for i, line in enumerate(result) if line.get('time') is None]
    if not pending:
        return result
    if not notes:
        for order, i in enumerate(pending):
            result[i].update(time=round(duration * (order + .5) / (len(pending) + 1), 2), auto=True)
        return result
    weights = [syllables(result[i]['text']) for i in pending]
    total = sum(weights)
    phrase_starts = [k for k in range(len(notes)) if k == 0 or notes[k]['start'] - notes[k - 1]['end'] >= .3]
    before, previous = 0, -1
    for order, i in enumerate(pending):
        share = len(notes) * weights[order] / total
        guess = len(notes) * before / total
        reach = max(2., share * .6)
        options = [k for k in phrase_starts if abs(k - guess) <= reach and k > previous]
        index = min(options, key=lambda k: abs(k - guess)) if options else int(round(guess))
        index = min(max(index, previous + 1), len(notes) - 1)
        stamp = notes[index]['start']
        if order and stamp <= result[pending[order - 1]]['time']:
            stamp = result[pending[order - 1]]['time'] + .05
        result[i].update(time=round(max(0., stamp - .15), 2), auto=True)
        previous = index
        before += weights[order]
    return result


def realign_following(lines: list[dict], index: int, notes: list[dict], duration: float) -> None:
    """After line ``index`` was timed by hand, re-estimate the automatic lines after it in place.

    Only lines up to the next hand-timed line are touched, and only notes between
    the two anchors are used, so every tap makes the remaining guesses better.
    """
    stop, end = len(lines), duration
    for j in range(index + 1, len(lines)):
        if lines[j].get('time') is not None and not lines[j].get('auto'):
            stop, end = j, lines[j]['time']
            break
    if stop == index + 1:
        return
    start = lines[index]['time']
    window = [note for note in notes if start - .2 <= note['start'] < end]
    count = stop - index
    if window:
        block = auto_align([{'text': line['text'], 'time': None} for line in lines[index:stop]], window, end)
        guesses = [item['time'] for item in block[1:]]
    else:
        guesses = [start + (end - start) * k / count for k in range(1, count)]
    previous = start
    for line, guess in zip(lines[index + 1:stop], guesses):
        previous = round(max(guess, previous + .05), 2)
        line.update(time=previous, auto=True)
