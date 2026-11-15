import numpy as np
import pytest

from vocalstudio.separation import separate


def known_mix(rate=22050, duration=12):
    t = np.arange(int(rate * duration), dtype=np.float32) / rate
    bass = .12 * np.sin(2 * np.pi * 110 * t)
    chord = sum(.035 * np.sin(2 * np.pi * frequency * t) for frequency in [130.81, 164.81, 196])
    left = .06 * np.sin(2 * np.pi * 440 * t)
    right = .06 * np.sin(2 * np.pi * 523.25 * t)
    backing = np.column_stack([bass + chord + left, bass + chord + right])
    vocal = np.zeros_like(t)
    for start, frequency in [(2, 240), (5, 290), (8, 350)]:
        local = t - start
        envelope = np.clip(local * 10, 0, 1) * np.clip((1.4 - local) * 10, 0, 1)
        phase = 2 * np.pi * (frequency * local + 15 * local ** 2)
        vocal += envelope * (.18 * np.sin(phase) + .07 * np.sin(2 * phase) + .03 * np.sin(3 * phase))
    return np.column_stack([vocal, vocal]), backing


def test_separation_reduces_known_backing_and_preserves_sum():
    voice, backing = known_mix()
    mixture = voice + backing
    vocals, instrumental = separate(mixture, 22050)
    assert vocals.shape == instrumental.shape == mixture.shape
    assert np.all(np.isfinite(vocals))
    np.testing.assert_allclose(vocals + instrumental, mixture, atol=1e-7)
    before = np.mean((mixture - voice) ** 2)
    after = np.mean((vocals - voice) ** 2)
    improvement = 10 * np.log10(before / after)
    assert improvement > 6, f'Expected useful isolation on controlled mixture, got {improvement:.2f} dB'
    # Prevent an all-zero "vocal" output from passing the reconstruction check.
    retained = np.sum(vocals * voice) / np.sum(voice ** 2)
    assert retained > .65


@pytest.mark.parametrize('channels', [1, 2])
@pytest.mark.parametrize('rate', [16000, 44100, 48000])
def test_short_silence_lengths_and_rates(channels, rate):
    source = np.zeros((round(rate * .031), channels), dtype=np.float32)
    if channels == 1:
        source = source[:, 0]
    voice, backing = separate(source, rate)
    assert voice.shape == source.shape == backing.shape
    assert np.max(np.abs(voice)) == 0
    assert np.max(np.abs(backing)) == 0


def test_hard_panned_signal_is_kept_in_backing():
    rate = 22050
    t = np.arange(rate * 3) / rate
    left = .3 * np.sin(2 * np.pi * (220 * t + 20 * t ** 2))
    source = np.column_stack([left, np.zeros_like(left)])
    voice, backing = separate(source, rate)
    assert np.sqrt(np.mean(voice ** 2)) < 1e-6
    np.testing.assert_allclose(backing, source, atol=1e-7)


def test_nonfinite_and_empty_input_rejected():
    with pytest.raises(ValueError):
        separate(np.array([np.nan]), 44100)
    with pytest.raises(ValueError):
        separate(np.array([]), 44100)
