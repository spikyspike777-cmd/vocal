"""Separate process: heavyweight preparation never blocks Qt's event loop."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from .core import atomic_json, extract_reference
from .separation import separate


def progress(message):
    print(message, flush=True)


def convert(source: Path, destination: Path):
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', str(source),
                    '-ar', '44100', '-ac', '2', '-c:a', 'pcm_f32le', str(destination)], check=True)


def demo(folder: Path):
    sr = 44100
    t = np.arange(sr * 24) / sr
    vocal = np.zeros_like(t)
    notes = [60, 62, 64, 67, 65, 64, 62, 60]
    for i, midi in enumerate(notes):
        start = 2 + i * 2.5
        local = t - start
        mask = (local >= 0) & (local < 1.8)
        envelope = np.clip(local * 12, 0, 1) * np.clip((1.8 - local) * 8, 0, 1)
        hz = 440 * 2 ** ((midi - 69) / 12)
        vocal += mask * envelope * (.2 * np.sin(2 * np.pi * hz * local) + .04 * np.sin(4 * np.pi * hz * local))
    backing = .045 * np.sin(2 * np.pi * 130.8128 * t) + .025 * np.sin(2 * np.pi * 195.9977 * t)
    backing *= np.minimum(t, 1) * np.minimum(24 - t, 1)
    sf.write(folder / 'vocals.wav', np.column_stack((vocal, vocal)), sr)
    sf.write(folder / 'instrumental.wav', np.column_stack((backing, backing)), sr)
    project = json.loads((folder / 'project.json').read_text())
    project.update(title='Первая распевка', lyrics='\n'.join(['Ла-а-а'] * 8),
                   lines=[{'text': f'Ла-а-а · {i + 1}', 'time': 2 + i * 2.5} for i in range(8)])
    atomic_json(folder / 'project.json', project)


def prepare(folder: Path, mode: str, vocal: str | None = None, backing: str | None = None):
    if mode == 'demo':
        progress('Создаём учебную распевку…')
        demo(folder)
    elif mode == 'import':
        progress('Импортируем готовые дорожки…')
        convert(Path(vocal), folder / 'vocals.wav')
        convert(Path(backing), folder / 'instrumental.wav')
    else:
        if not shutil.which('ffmpeg'):
            raise RuntimeError('Нужен FFmpeg в PATH. Инструкция есть в README.md.')
        project = json.loads((folder / 'project.json').read_text())
        progress('Декодируем песню…')
        source_path = folder / 'source.wav'
        convert(Path(project['source']), source_path)
        try:
            info = sf.info(source_path)
            if info.duration > 600:
                raise ValueError('Пока поддерживаются песни длительностью до 10 минут.')
            mixture, rate = sf.read(source_path, dtype='float32', always_2d=True)
            vocals, instrumental = separate(mixture, rate, progress)
            sf.write(folder / 'vocals.wav', vocals, rate, subtype='FLOAT')
            sf.write(folder / 'instrumental.wav', instrumental, rate, subtype='FLOAT')
        finally:
            source_path.unlink(missing_ok=True)
        project['separator'] = 'repetition-centre-v1'
        atomic_json(folder / 'project.json', project)
    vocal_info = sf.info(folder / 'vocals.wav')
    backing_info = sf.info(folder / 'instrumental.wav')
    if abs(vocal_info.duration - backing_info.duration) > .1:
        raise ValueError('Вокал и минус должны иметь одинаковую длительность и начало.')
    progress('Определяем высоту вокала…')
    audio, sr = sf.read(folder / 'vocals.wav', dtype='float32')
    atomic_json(folder / 'reference.json', extract_reference(audio, sr))
    project = json.loads((folder / 'project.json').read_text())
    project.update(state='ready', duration=len(audio) / sr)
    atomic_json(folder / 'project.json', project)
    progress('Готово')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--mode', choices=['separate', 'import', 'demo'], default='separate')
    parser.add_argument('--vocal')
    parser.add_argument('--backing')
    args = parser.parse_args()
    try:
        prepare(args.folder, args.mode, args.vocal, args.backing)
    except Exception as error:
        progress(f'ОШИБКА: {error}')
        sys.exit(1)


if __name__ == '__main__':
    main()
