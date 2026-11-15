#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo 'Сначала установите приложение по README.md.'
  exit 1
fi
# A local PortAudio copy is used only in the isolated development environment.
if [[ -d .native/usr/lib/x86_64-linux-gnu ]]; then
  export LD_LIBRARY_PATH="$PWD/.native/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi
exec .venv/bin/python -m vocalstudio
