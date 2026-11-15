import numpy as np
import pytest
from vocalstudio.core import active_line, cents_error, detect_pitch, extract_reference, parse_lyrics


@pytest.mark.parametrize('frequency', [82.4069, 130.8128, 220, 440, 880])
def test_pitch_on_harmonic_voice(frequency):
    rate = 44100
    t = np.arange(4096) / rate
    signal = .2 * np.sin(2 * np.pi * frequency * t) + .08 * np.sin(4 * np.pi * frequency * t)
    midi, confidence = detect_pitch(signal, rate)
    expected = 69 + 12 * np.log2(frequency / 440)
    assert abs(midi - expected) < .1
    assert confidence > .85


def test_silence_and_unpitched_noise_are_not_notes():
    assert detect_pitch(np.zeros(4096), 44100)[0] is None
    noise = np.random.default_rng(1).normal(0, .08, 4096)
    assert detect_pitch(noise, 44100)[0] is None


def test_reference_time_and_resampling():
    rate = 48000
    t = np.arange(rate * 2) / rate
    voice = np.where(t >= .5, .25 * np.sin(2 * np.pi * 440 * t), 0)
    reference = extract_reference(np.column_stack([voice, voice]), rate)
    assert all(note is None for time, note in zip(reference['times'], reference['midi']) if time < .45)
    assert abs(reference['midi'][50] - 69) < .1
    assert reference['times'][50] == 1.
    assert reference['times'][-1] < 2.


def test_plain_and_timestamped_lyrics():
    assert parse_lyrics('Привет\n\nМир') == [{'text': 'Привет', 'time': None}, {'text': 'Мир', 'time': None}]
    lines = parse_lyrics('[ar:Artist]\n[00:02.50][01:02.50]Припев\n[00:08.00]Куплет')
    assert len(lines) == 3
    assert active_line(lines, 1) is None
    assert active_line(lines, 9) == 2
    assert active_line(lines, 63) == 1


def test_octave_mode_and_direction():
    assert cents_error(72, 60) == 1200
    assert cents_error(72, 60, True) == 0
    assert cents_error(60.6, 60) == pytest.approx(60)
