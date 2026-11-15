import numpy as np
import pytest
from vocalstudio.core import (
    active_line, auto_align, cents_error, detect_pitch, extract_reference, note_at, parse_lyrics,
    realign_following, segment_notes,
)


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


def test_notes_are_segmented_and_snapped_to_the_songs_tuning():
    step = .02
    times = [round(i * step, 4) for i in range(200)]
    # Two held notes 30 cents sharp of equal temperament, a gap, then a blip that is too short.
    pitch = [None] * 200
    for i in range(10, 60):
        pitch[i] = 60.3 + .05 * np.sin(i)
    for i in range(60, 110):
        pitch[i] = 64.3
    for i in range(150, 153):
        pitch[i] = 70.3
    notes = segment_notes(times, pitch, step)
    assert [(note['start'], note['end']) for note in notes] == [(.2, 1.2), (1.2, 2.2)]
    assert notes[0]['midi'] == pytest.approx(60.3, abs=.05)
    assert notes[1]['midi'] == pytest.approx(64.3, abs=.05)
    starts = [note['start'] for note in notes]
    assert note_at(notes, starts, .1) is None
    assert note_at(notes, starts, 1.5) == 1
    assert note_at(notes, starts, 2.5) is None


def test_reference_contains_notes():
    rate = 16000
    t = np.arange(rate * 3) / rate
    voice = np.where(t < 1.5, np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t)) * .3
    notes = extract_reference(voice, rate)['notes']
    assert [round(note['midi']) for note in notes] == [57, 64]
    assert abs(notes[1]['start'] - 1.5) < .08


def _phrases():
    notes = []
    for phrase in range(3):
        for k in range(4):
            start = phrase * 5 + 1 + k * .5
            notes.append({'start': start, 'end': start + .4, 'midi': 60})
    return notes


def test_plain_lyrics_are_aligned_to_phrase_starts():
    lines = parse_lyrics('ла ла ла ла\nла ла ла ла\nла ла ла ла')
    aligned = auto_align(lines, _phrases(), 16)
    assert [line['time'] for line in aligned] == [.85, 5.85, 10.85]
    assert all(line['auto'] for line in aligned)
    # Hand-made or LRC timing is never overwritten.
    lines[1]['time'] = 7.
    aligned = auto_align(lines, _phrases(), 16)
    assert aligned[1] == {'text': 'ла ла ла ла', 'time': 7.}
    # Without a melody the lines are simply spread over the song.
    spread = auto_align(parse_lyrics('a\nb'), [], 9)
    assert [line['time'] for line in spread] == [1.5, 4.5]


def test_tapping_a_line_improves_the_following_guesses():
    lines = auto_align(parse_lyrics('ла ла ла ла\nла ла ла ла\nла ла ла ла'), _phrases(), 16)
    lines[2] = {'text': lines[2]['text'], 'time': 15.}      # timed by hand earlier
    lines[0] = {'text': lines[0]['text'], 'time': 5.9}      # the singer actually starts at phrase two
    realign_following(lines, 0, _phrases(), 16)
    assert lines[1]['auto'] and 5.9 < lines[1]['time'] < 15
    assert lines[2] == {'text': 'ла ла ла ла', 'time': 15.}
