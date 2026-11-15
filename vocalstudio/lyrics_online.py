"""Optional lookup of time-synced lyrics in the public LRCLIB database.

Only the search text typed by the user is sent; audio never leaves the computer.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

API = 'https://lrclib.net/api/search'


def search(query: str, timeout: float = 15.) -> list[dict]:
    """Return matches as dicts with title, artist, duration, synced flag and lyrics text."""
    query = query.strip()
    if not query:
        return []
    request = urllib.request.Request(API + '?' + urllib.parse.urlencode({'q': query}),
                                     headers={'User-Agent': 'VocalStudio'})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        rows = json.loads(response.read().decode('utf-8'))
    results = []
    for row in rows if isinstance(rows, list) else []:
        synced, plain = row.get('syncedLyrics'), row.get('plainLyrics')
        if not (synced or plain):
            continue
        results.append({
            'title': row.get('trackName') or '', 'artist': row.get('artistName') or '',
            'duration': float(row.get('duration') or 0), 'synced': bool(synced), 'lyrics': synced or plain,
        })
    results.sort(key=lambda item: not item['synced'])
    return results
