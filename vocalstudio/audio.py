from __future__ import annotations

from collections import deque
from pathlib import Path
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioEngine:
    def __init__(self):
        self.sample_rate = 44100
        self.position = 0
        self.playing = False
        self.guide_volume = .25
        self.backing_volume = .8
        self.output = None
        self.input = None
        self.lock = threading.Lock()
        self.frames = deque(maxlen=16)
        self.backing = np.zeros((0, 2), dtype='float32')
        self.vocal = self.backing
        self.input_rate = 44100
        self.latency = 0.
        self.device_error = ''
        self.level = 0.

    def load(self, folder: Path):
        self.pause()
        backing, sr = sf.read(folder / 'instrumental.wav', dtype='float32', always_2d=True)
        vocal, vsr = sf.read(folder / 'vocals.wav', dtype='float32', always_2d=True)
        if sr != vsr or backing.shape[1] != 2 or vocal.shape[1] != 2:
            raise ValueError('Дорожки должны быть стерео и иметь одинаковую частоту дискретизации.')
        if abs(len(backing) - len(vocal)) > sr * .1:
            raise ValueError('Длительности вокала и минуса отличаются больше чем на 0,1 секунды.')
        length = min(len(vocal), len(backing))
        self.backing, self.vocal = backing[:length], vocal[:length]
        self.sample_rate, self.position = sr, 0

    @property
    def seconds(self):
        return max(0., self.position / self.sample_rate - (self.latency if self.playing else 0))

    @property
    def duration(self):
        return len(self.backing) / self.sample_rate

    def callback(self, outdata, frames, time_info, status):
        outdata.fill(0)
        with self.lock:
            if not self.playing:
                return
            remaining = min(frames, len(self.backing) - self.position)
            if remaining > 0:
                end = self.position + remaining
                outdata[:remaining] = np.clip(self.backing[self.position:end] * self.backing_volume +
                                              self.vocal[self.position:end] * self.guide_volume, -1, 1)
                self.position = end
            if self.position >= len(self.backing):
                self.playing = False

    def play(self):
        if not len(self.backing):
            return
        if self.output is None:
            self.output = sd.OutputStream(samplerate=self.sample_rate, channels=2, dtype='float32',
                                          callback=self.callback, blocksize=512)
            self.output.start()
            self.latency = float(self.output.latency)
        if self.position >= len(self.backing):
            self.position = 0
        self.playing = True

    def pause(self):
        self.playing = False
        if self.output is not None:
            self.output.stop()
            self.output.close()
            self.output = None

    def seek(self, seconds):
        with self.lock:
            self.position = int(np.clip(seconds * self.sample_rate, 0, len(self.backing)))
        self.frames.clear()

    def start_microphone(self, device=None):
        self.stop_microphone()
        info = sd.query_devices(device, 'input')
        self.input_rate = int(info['default_samplerate'])
        def capture(indata, frames, time_info, status):
            self.frames.append(indata[:, 0].copy())
            self.level = float(np.sqrt(np.mean(indata[:, 0] ** 2)))
        self.input = sd.InputStream(device=device, samplerate=self.input_rate, channels=1,
                                    dtype='float32', blocksize=512, callback=capture)
        self.input.start()

    def stop_microphone(self):
        if self.input is not None:
            self.input.stop()
            self.input.close()
            self.input = None
        self.frames.clear()
        self.level = 0.

    def microphone_samples(self):
        # Snapshot the deque: PortAudio writes on a different thread.
        chunks = list(self.frames)
        if not chunks:
            return None
        samples = np.concatenate(chunks)
        needed = int(self.input_rate * .07)
        return samples[-needed:] if len(samples) >= needed else None

    def close(self):
        self.pause()
        self.stop_microphone()
