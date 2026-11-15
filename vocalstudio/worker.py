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

from . import neural
from .core import atomic_json, auto_align, extract_reference
from .separation import separate


_STATUS_FILE: Path | None = None


def progress(message):
    """Report a stage to the GUI: over stdout and, for windowed builds without stdout, a status file."""
    try:
        print(message, flush=True)
    except (OSError, ValueError, AttributeError):
        pass
    if _STATUS_FILE is not None:
        try:
            _STATUS_FILE.write_text(message, encoding='utf-8')
        except OSError:
            pass


def ffmpeg_path() -> str | None:
    """System FFmpeg, or the copy bundled with the imageio-ffmpeg package."""
    found = shutil.which('ffmpeg')
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def convert(source: Path, destination: Path):
    tool = ffmpeg_path()
    if not tool:
        raise RuntimeError('Не найден FFmpeg. Переустанови зависимости по README.md.')
    flags = {'creationflags': 0x08000000} if sys.platform == 'win32' else {}
    subprocess.run([tool, '-nostdin', '-v', 'error', '-y', '-i', str(source),
                    '-ar', '44100', '-ac', '2', '-c:a', 'pcm_f32le', str(destination)], check=True, **flags)


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
    project = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
    project.update(title='Первая распевка', lyrics='\n'.join(['Ла-а-а'] * 8),
                   lines=[{'text': f'Ла-а-а · {i + 1}', 'time': 2 + i * 2.5} for i in range(8)])
    atomic_json(folder / 'project.json', project)


def prepare(folder: Path, mode: str, vocal: str | None = None, backing: str | None = None,
            engine: str = 'dsp', models: Path | None = None):
    if mode == 'demo':
        progress('Создаём учебную распевку…')
        demo(folder)
    elif mode == 'import':
        progress('Импортируем готовые дорожки…')
        convert(Path(vocal), folder / 'vocals.wav')
        convert(Path(backing), folder / 'instrumental.wav')
    else:
        project = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
        progress('Декодируем песню…')
        source_path = folder / 'source.wav'
        convert(Path(project['source']), source_path)
        try:
            info = sf.info(source_path)
            if info.duration > 600:
                raise ValueError('Пока поддерживаются песни длительностью до 10 минут.')
            mixture, rate = sf.read(source_path, dtype='float32', always_2d=True)
            separator = 'repetition-centre-v1'
            vocals = None
            if engine == 'neural' and models is not None and neural.available():
                try:
                    model = neural.ensure_model(models, progress)
                except Exception as error:
                    progress(f'Модель не скачалась ({error}). Используем быстрый режим…')
                else:
                    vocals, instrumental = neural.separate(mixture, rate, model, progress)
                    separator = 'mdx-net-kim-vocal-2'
            if vocals is None:
                vocals, instrumental = separate(mixture, rate, progress)
            sf.write(folder / 'vocals.wav', vocals, rate, subtype='FLOAT')
            sf.write(folder / 'instrumental.wav', instrumental, rate, subtype='FLOAT')
        finally:
            source_path.unlink(missing_ok=True)
        project['separator'] = separator
        atomic_json(folder / 'project.json', project)
    vocal_info = sf.info(folder / 'vocals.wav')
    backing_info = sf.info(folder / 'instrumental.wav')
    if abs(vocal_info.duration - backing_info.duration) > .1:
        raise ValueError('Вокал и минус должны иметь одинаковую длительность и начало.')
    progress('Определяем высоту вокала…')
    audio, sr = sf.read(folder / 'vocals.wav', dtype='float32')
    reference = extract_reference(audio, sr)
    atomic_json(folder / 'reference.json', reference)
    project = json.loads((folder / 'project.json').read_text(encoding='utf-8'))
    duration = len(audio) / sr
    project.update(state='ready', duration=duration,
                   lines=auto_align(project.get('lines', []), reference['notes'], duration))
    atomic_json(folder / 'project.json', project)
    progress('Готово')


def main(argv=None):
    global _STATUS_FILE
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    parser.add_argument('--mode', choices=['separate', 'import', 'demo'], default='separate')
    parser.add_argument('--vocal')
    parser.add_argument('--backing')
    parser.add_argument('--engine', choices=['neural', 'dsp'], default='dsp')
    parser.add_argument('--models', type=Path)
    args = parser.parse_args(argv)
    _STATUS_FILE = args.folder / 'progress.txt'
    try:
        prepare(args.folder, args.mode, args.vocal, args.backing, args.engine, args.models)
    except Exception as error:
        progress(f'ОШИБКА: {error}')
        sys.exit(1)
    _STATUS_FILE.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
