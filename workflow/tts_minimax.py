"""Domestic MiniMax narration with durable paid-request records and native timings.

No dependency installation. Never auto-resubmit an ambiguous paid request.
"""
import os
import hashlib
import fcntl
import json
from pathlib import Path
import re
import urllib.request
import wave

from portable import project_root, resolve_font
ROOT = project_root()
ENDPOINT = 'https://api.minimax.cn/v1/t2a_v2'
SUPPORTED_MODELS = {'speech-2.8-hd', 'speech-2.8-turbo'}


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(path)


def secret():
    env = {}
    path = ROOT / '.env.local'
    if path.is_file():
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                k,v=line.split('=',1);env[k.strip()]=v.strip().strip('\"\'')
    env.update({k:os.environ[k] for k in ['MINIMAX_API_KEY','MINIMAX_REGION'] if k in os.environ})
    if env.get('MINIMAX_REGION') != 'cn': raise ValueError('Set MINIMAX_REGION=cn explicitly for this domestic adapter')
    if not env.get('MINIMAX_API_KEY'): raise ValueError('MINIMAX_API_KEY is not configured')
    return env['MINIMAX_API_KEY']


def synthesize(text, speech, cache_root):
    # Serialize cache lookup and submission so concurrent callers cannot double-bill.
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    with (cache_root / '.submit.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _synthesize(text, speech, cache_root)


def _synthesize(text, speech, cache_root):
    if speech['model'] not in SUPPORTED_MODELS:
        raise ValueError('Unsupported MiniMax model; verify pricing and schema before adding')
    payload = {
        'model': speech['model'], 'text': text, 'stream': False,
        'voice_setting': {'voice_id': speech['voice'], 'speed': speech['speed'], 'vol': 1, 'pitch': 0},
        'audio_setting': {'sample_rate': 24000, 'format': 'wav', 'channel': 1},
        'language_boost': 'Chinese', 'subtitle_enable': True,
        'subtitle_type': 'word', 'output_format': 'hex',
    }
    fingerprint = hashlib.sha256(json.dumps({'endpoint':ENDPOINT,'payload':payload}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    folder = Path(cache_root) / fingerprint[:16]
    folder.mkdir(parents=True, exist_ok=True)
    record_path = folder / 'record.json'
    record = json.loads(record_path.read_text()) if record_path.exists() else None
    if record and record.get('fingerprint') != fingerprint:
        raise ValueError('Cache fingerprint mismatch')
    if record and record['state'] not in {'response_received', 'complete'}:
        raise RuntimeError('Previous paid request unresolved; inspect ' + str(record_path))
    if record is None:
        key = secret()
        record = {'state': 'submitting', 'endpoint': ENDPOINT, 'request': payload, 'fingerprint': fingerprint}
        save(record_path, record)
        request = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(),
                                        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                data = json.load(response)
        except Exception as error:
            record.update(state='submission_unknown', error_type=type(error).__name__)
            save(record_path, record)
            raise RuntimeError('MiniMax submission outcome unknown; no automatic retry') from None
        if data.get('base_resp', {}).get('status_code') != 0:
            record.update(state='failed', status_code=data.get('base_resp', {}).get('status_code'))
            save(record_path, record)
            raise RuntimeError('MiniMax rejected request, code ' + str(record['status_code']))
        audio = bytes.fromhex(data['data'].pop('audio'))
        temporary = folder / 'audio.partial.wav'
        temporary.write_bytes(audio)
        temporary.replace(folder / 'audio.wav')
        record.update(state='response_received', response=data,
                      usage_characters=data.get('extra_info', {}).get('usage_characters'),
                      audio_sha256=hashlib.sha256(audio).hexdigest())
        save(record_path, record)
    if hashlib.sha256((folder / 'audio.wav').read_bytes()).hexdigest() != record['audio_sha256']:
        raise ValueError('Cached audio hash mismatch; refusing regeneration')
    subtitles_path = folder / 'subtitles.json'
    if not subtitles_path.exists():
        url = record['response']['data'].get('subtitle_file')
        if not url or not url.startswith('https://'):
            raise ValueError('Missing native subtitle URL; audio kept, no paid retry')
        with urllib.request.urlopen(url, timeout=60) as response:
            subtitles = json.load(response)
        save(subtitles_path, subtitles)
    with wave.open(str(folder / 'audio.wav')) as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (24000, 1, 2):
            raise ValueError('Unexpected MiniMax PCM format')
        record['duration'] = audio.getnframes() / audio.getframerate()
    record['state'] = 'complete'
    record['cost_estimate'] = None  # Verify current service pricing separately; no stale price claims.
    record['billing_verified'] = False
    save(record_path, record)
    return folder, record


def normalized(text):
    return ''.join(re.findall(r'[\w]', text, flags=re.UNICODE))


def align(sentences, subtitles, duration, intro=0, outro=0):
    """Map editorial captions to native words; reject omissions, overlaps and drift.

    If a caption boundary divides a multi-character word, distribute only that word's
    duration across its characters. Entire narration is never timed by character count.
    """
    rows = subtitles if isinstance(subtitles, list) else subtitles.get('subtitles', [])
    words = [w for row in rows for w in (row.get('timestamped_words') or [])]
    if not words:
        raise ValueError('Native word timestamps missing; cannot assert aligned captions')
    characters = []
    previous_end = 0
    for word in words:
        text = normalized(word['word'])
        if not text:
            continue
        start, end = word['time_begin'] / 1000, word['time_end'] / 1000
        if start < previous_end - .02 or end <= start or end > duration + .08:
            raise ValueError('Invalid native word timestamps')
        start = max(previous_end, start)
        for i, char in enumerate(text):
            characters.append((char, start + (end-start)*i/len(text), start + (end-start)*(i+1)/len(text)))
        previous_end = end
    expected = normalized(''.join(s['text'] for s in sentences))
    if ''.join(c[0] for c in characters) != expected:
        raise ValueError('Native subtitle text does not exactly match approved narration')
    captions, scenes = [], []
    cursor = 0
    for i, sentence in enumerate(sentences, 1):
        first = len(captions)
        for caption in sentence['captions']:
            size = len(normalized(caption))
            if not size:
                raise ValueError('Empty normalized caption')
            captions.append({'start': characters[cursor][1] + intro,
                             'end': characters[cursor+size-1][2] + intro,
                             'text': caption, 'sentence': i})
            cursor += size
        scenes.append({'index': i, 'asset': sentence['asset'], 'start': captions[first]['start'],
                       'end': captions[-1]['end'], 'text': sentence['text'],
                       'kind': sentence.get('kind', 'knowledge')})
    scenes[0]['start'] = 0
    for previous, following in zip(scenes, scenes[1:]):
        previous['end'] = following['start']
    scenes[-1]['end'] = intro + duration + outro
    shots = []
    for sentence, scene in zip(sentences, scenes):
        sentence_captions = [c for c in captions if c['sentence'] == scene['index']]
        cuts = [{'caption': 0, 'asset': scene['asset']}] + sentence.get('visual_cuts', [])
        for index, cut in enumerate(cuts):
            shot = dict(scene)
            shot['sentence'] = scene['index']
            shot['index'] = len(shots) + 1
            shot['asset'] = cut['asset']
            shot['start'] = scene['start'] if index == 0 else sentence_captions[cut['caption']]['start']
            shot['end'] = (sentence_captions[cuts[index+1]['caption']]['start']
                           if index+1 < len(cuts) else scene['end'])
            shots.append(shot)
    return {'duration': intro + duration + outro, 'scenes': shots, 'captions': captions,
            'timing_method': 'MiniMax native word timestamps; interpolation only within words crossing editorial boundaries'}
