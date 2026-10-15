"""Validate an agent-reviewed TTS delivery text before any paid synthesis.

Narration and captions remain plain source text. Only native pause tags and
whitespace may differ in the request text; historical episodes stay compatible.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

PAUSE = re.compile(r'<#(\d+(?:\.\d{1,2})?)#>')


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flat(text):
    return re.sub(r'\s+', '', text)


def validate_request_text(source, request):
    plain = PAUSE.sub('', request)
    if '<#' in plain or '#>' in plain:
        raise ValueError('Malformed native pause tag')
    if flat(plain) != flat(source):
        raise ValueError('Directed TTS text changed locked narration; only pauses and whitespace may differ')
    spans = list(PAUSE.finditer(request))
    previous = 0
    for tag in spans:
        if not .01 <= float(tag[1]) <= 99.99:
            raise ValueError('Native pause outside supported range')
        if not re.search(r'\w', request[previous:tag.start()]):
            raise ValueError('Pause must follow spoken text; no leading or consecutive pauses')
        previous = tag.end()
    if spans and not re.search(r'\w', request[previous:]):
        raise ValueError('Pause must precede spoken text; no trailing pause')
    return len(spans)


def load_direction(config, episode_dir):
    episode_dir = Path(episode_dir).resolve()
    plain_config = '\n'.join(s['text'] for s in config['sentences'])
    settings = config.get('audio_direction')
    frozen = episode_dir / 'generation/production-defaults.json'
    required = str(config.get('workflow_version','')).startswith('2.')
    if frozen.is_file():
        stored = json.loads(frozen.read_text())
        defaults = stored.get('episode_defaults',stored)
        required = required or defaults.get('audio_direction', {}).get('required', False)
    if not settings:
        if required:
            raise ValueError('This session requires audio-agent direction before synthesis')
        return plain_config, None

    def local_file(relative):
        path = (episode_dir / relative).resolve()
        if not path.is_relative_to(episode_dir) or not path.is_file():
            raise ValueError('Missing or out-of-episode audio direction file: ' + str(relative))
        return path

    source = local_file('narration.txt')
    lock = json.loads(local_file('source/locked-inputs.json').read_text())
    if lock['files'].get('narration.txt') != sha256(source):
        raise ValueError('Narration changed since input lock')
    if flat(plain_config) != flat(source.read_text()):
        raise ValueError('Episode sentences differ from locked narration')
    request_path = local_file(settings['request_text_file'])
    review_path = local_file(settings['review_file'])
    request = request_path.read_text()
    count = validate_request_text(source.read_text(), request)
    review = json.loads(review_path.read_text())
    if review.get('status') != 'ready_for_synthesis':
        raise ValueError('Audio direction review is not ready')
    reviewer = review.get('reviewer', {})
    if reviewer.get('mode') == 'subagent':
        if not reviewer.get('task_id') or not reviewer.get('response_file'):
            raise ValueError('Record the real audio-agent task and its response')
        response=local_file(reviewer['response_file'])
        if reviewer.get('response_sha256')!=sha256(response): raise ValueError('Audio agent response missing or changed')
    elif reviewer.get('mode') == 'main_agent_separate_pass':
        if not reviewer.get('unavailable_reason'):
            raise ValueError('Separate-pass fallback needs a real subagent unavailability reason')
    else:
        raise ValueError('Missing actual audio reviewer')
    if not review.get('reasoning_summary') or not review.get('model_requirements', {}).get('source_url'):
        raise ValueError('Missing rhythm decisions or model requirements source')
    for key, path in [('narration_sha256', source), ('request_text_sha256', request_path)]:
        if review.get(key) != sha256(path):
            raise ValueError('Audio review stale: ' + key)
    for key in ['provider', 'model', 'voice', 'speed']:
        if review.get('speech', {}).get(key) != config['speech'].get(key):
            raise ValueError('Audio review uses different speech setting: ' + key)
    # A stable content key prevents a revised rhythm from overwriting its earlier run.
    if settings.get('request_text_sha256') != sha256(request_path):
        raise ValueError('Set audio_direction.request_text_sha256 to the reviewed request hash')
    if settings.get('review_sha256') != sha256(review_path):
        raise ValueError('Set audio_direction.review_sha256 to the actual review hash')
    return request, {'review': review, 'review_sha256': sha256(review_path),
                     'request_text_sha256': sha256(request_path), 'pause_count': count}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', required=True, type=Path)
    args = parser.parse_args()
    try:
        config = json.loads(args.episode.read_text())
        request, evidence = load_direction(config, args.episode.parent)
        print('AUDIO DIRECTION PASS:', evidence['pause_count'] if evidence else 0, 'native pauses; no API call')
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.exit(1, f'AUDIO DIRECTION FAIL: {error}\n')
