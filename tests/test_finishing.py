"""Offline synthetic fixtures: routing and rendered bytes, never production acceptance."""
import contextlib
import io
import json
import math
import struct
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'workflow'))
from finishing import (audio_mode, audio_signature, movie_names, opening_graph,
                       finish_film, mux_narration_only, release_gate, sha,
                       run_command, caption_signature)
from initialize import create, write
from portable import resolve_font


class FinishingChecks(unittest.TestCase):
    def test_audio_route_preserves_legacy_and_skips_catalog(self):
        self.assertEqual(audio_mode({'workflow_version': '2.1.0'}), 'licensed_bgm')
        p = {'workflow_version': '2.2.0', 'bgm': {'catalog_file': 'missing'}}
        with patch('finishing.load_music', side_effect=AssertionError('Music node must be skipped')):
            self.assertEqual(audio_signature(Path('/missing-project'), p), {'mode': 'narration_only'})
        self.assertEqual(movie_names(p), ['film.mp4'])
        with self.assertRaises(ValueError):
            audio_mode({'audio_output': {'mode': 'unknown'}})

    def test_licensed_music_keeps_zero_to_two_alternatives(self):
        for count in range(3):
            p = {'workflow_version': '2.2.0', 'audio_output': {'mode': 'licensed_bgm'},
                 'bgm': {'alternatives': ['fixture'] * count}}
            self.assertEqual(movie_names(p), ['film.mp4'] + [f'film-bgm-alt-{i:02d}.mp4' for i in range(1, count + 1)])
        self.assertEqual(movie_names({'workflow_version': '2.1.0', 'bgm': {'enabled': False}}), ['film.mp4'])

    def test_init_freezes_new_defaults_without_rewriting_existing_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = create(root, 'first', 'Fixture', 'One.')
            p = json.loads((first / 'episode.json').read_text())
            self.assertEqual(p['workflow_version'], '2.2.0')
            self.assertEqual(p['audio_output']['mode'], 'narration_only')
            self.assertEqual(p['opening']['style'], 'visible_smooth_lift')
            self.assertEqual(json.loads((first / 'visual-plan.json').read_text())['workflow_version'], '2.2.0')
            defaults = root / 'brand/production-defaults.json'
            old = json.loads(defaults.read_text())
            old.pop('audio_output')
            old.pop('opening')
            old['bgm'] = {'enabled': True, 'catalog_file': 'music.json'}
            write(defaults, old)
            before = defaults.read_bytes()
            second = create(root, 'second', 'Fixture', 'Two.')
            p2 = json.loads((second / 'episode.json').read_text())
            self.assertEqual(p2['audio_output']['mode'], 'licensed_bgm')
            self.assertNotIn('opening', p2)
            self.assertEqual(before, defaults.read_bytes())

    def test_opening_requires_visible_finite_settings_and_preserves_legacy_fade(self):
        self.assertEqual(opening_graph({}, 'a', 'b'), '[a]fade=t=in:st=0:d=0.3[b]')
        for key, value in [('initial_brightness', 0), ('initial_brightness', 1.1),
                           ('initial_brightness', True), ('seconds', 0),
                           ('seconds', float('nan')), ('seconds', True)]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                opening_graph({'opening': {'style': 'visible_smooth_lift', key: value}}, 'a', 'b')

    def fixture(self, root):
        from PIL import Image
        ep = root / 'episode'
        run = root / 'run'
        ep.mkdir()
        (run / 'render').mkdir(parents=True)
        image = root / 'source.png'
        Image.new('RGB', (270, 480), '#847452').save(image)
        narration = run / 'narration.wav'
        with wave.open(str(narration), 'wb') as w:
            w.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
            w.writeframes(b''.join(struct.pack('<h', int(3500 * math.sin(2 * math.pi * 220 * i / 24000))) for i in range(48000)))
        base = run / 'base.mp4'
        run_command(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-i', image, '-t', '2', '-r', '25',
                     '-c:v', 'libx264', '-pix_fmt', 'yuv420p', base])
        layout = {'box': [.08, .1, .84, .15], 'theme': 'light_text', 'align': 'center', 'max_lines': 2,
                  'layout_group': 'fixture', 'reason': 'Synthetic test empty region', 'protected_regions': []}
        write(ep / 'plan.json', {'shots': [{'caption_layout': layout}]})
        write(run / 'timeline.json', {'duration': 2, 'scenes': [{'start': 0, 'end': 2, 'asset': 'a'}],
                                      'captions': [{'start': .2, 'end': 1.2, 'text': '测试字幕'}]})
        write(run / 'sources.json', [])
        brand = {'subtitle': {'font_file': resolve_font(root=root), 'size_ratio': .044,
                              'light_text': '#F5F2E9', 'dark_text': '#17283B'}}
        write(root / 'brand.json', brand)
        p = {'workflow_version': '2.2.0', 'width': 270, 'height': 480, 'fps': 25, 'title': 'SYNTHETIC FIXTURE',
             'brand': 'brand.json', 'transition': {'seconds': 0}, 'caption_motion': {'type': 'fade'},
             'visual_plan': {'file': 'plan.json'}, 'audio_output': {'mode': 'narration_only'},
             'opening': {'style': 'visible_smooth_lift', 'initial_brightness': .78, 'seconds': .8},
             'assets': [{'id': 'a', 'file': 'source.png', 'motion': 'static'}]}
        return ep, run, p, brand, base, narration

    def test_actual_narration_only_render_and_visible_lift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ep, run, p, brand, base, narration = self.fixture(root)
            original = sha(narration)
            with patch('finishing.mix_music', side_effect=AssertionError('Skip mixing')), patch('finishing.load_music', side_effect=AssertionError('Skip catalog')):
                finish_film(p, brand, ep, run, root, base)
            self.assertEqual(sha(narration), original)
            self.assertEqual(sorted(x.name for x in run.glob('film*.mp4')), ['film.mp4'])
            self.assertFalse((run / 'audio-mix').exists())
            self.assertFalse((run / 'MUSIC-CREDITS.txt').exists())
            report = json.loads((run / 'audio-output/report.json').read_text())
            self.assertEqual(report['music_stage'], 'skipped')
            self.assertEqual(report['music_tracks'], [])
            self.assertEqual(report['narration_source_sha256'], original)
            run_command(['ffmpeg', '-v', 'error', '-xerror', '-i', run / 'film.mp4', '-f', 'null', '-'])
            levels = []
            for time in ['0', '0.4', '0.8']:
                stats = run_command(['ffmpeg', '-v', 'error', '-ss', time, '-i', run / 'film.mp4', '-vf',
                                     'signalstats,metadata=print:file=-', '-frames:v', '1', '-f', 'null', '-']).stdout
                levels.append(float(next(line.split('=')[1] for line in stats.splitlines() if line.startswith('lavfi.signalstats.YAVG='))))
            self.assertGreater(levels[0], 50)
            self.assertLess(levels[0], levels[1])
            self.assertLess(levels[1], levels[2])
            self.assertAlmostEqual((levels[0] - 16) / (levels[2] - 16), .78, delta=.05)
            self.assertAlmostEqual((levels[1] - levels[0]) / (levels[2] - levels[0]), .5, delta=.08)
            write(ep / 'episode.json', p)
            from offline_review import inspect
            with contextlib.redirect_stdout(io.StringIO()):
                inspect(ep / 'episode.json', run, root)
            offline = json.loads((run / 'offline-qa/report.json').read_text())
            self.assertEqual([x['file'] for x in offline['movies']], ['film.mp4'])
            self.assertEqual(offline['audio_report_sha256'], sha(run / 'audio-output/report.json'))
            with self.assertRaisesRegex(ValueError, 'truncated'):
                mux_narration_only(base, narration, run / 'too-short.mp4', 1, 'TRUNCATION FIXTURE')

    def test_layout_fingerprint_includes_opening_and_audio_route(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ep, run, p, brand, base, narration = self.fixture(root)
            before = caption_signature(p, ep, run, root)
            p['opening']['initial_brightness'] = .9
            self.assertNotEqual(before, caption_signature(p, ep, run, root))
            before = caption_signature(p, ep, run, root)
            p['audio_output']['mode'] = 'licensed_bgm'
            self.assertNotEqual(before, caption_signature(p, ep, run, root))

    def test_actual_legacy_contract_keeps_black_fade_and_disabled_music_route(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ep, run, p, brand, base, narration = self.fixture(root)
            p['workflow_version'] = '2.1.0'
            p.pop('opening')
            p.pop('audio_output')
            p['bgm'] = {'enabled': False}
            finish_film(p, brand, ep, run, root, base)
            self.assertTrue((run / 'audio-mix/mix-report.json').is_file())
            self.assertFalse((run / 'audio-output/report.json').exists())
            stats = run_command(['ffmpeg', '-v', 'error', '-i', run / 'film.mp4', '-vf',
                                 'signalstats,metadata=print:file=-', '-frames:v', '1', '-f', 'null', '-']).stdout
            first = float(next(line.split('=')[1] for line in stats.splitlines() if line.startswith('lavfi.signalstats.YAVG=')))
            self.assertLess(first, 20)

    def test_release_gate_binds_clean_source_and_one_final_movie(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            ep, run = root / 'episode', root / 'run'
            ep.mkdir()
            (run / 'offline-qa').mkdir(parents=True)
            (run / 'audio-output').mkdir()
            (ep / 'response.md').write_text('SIMULATED TEST FIXTURE ONLY')
            (run / 'film.mp4').write_bytes(b'film fixture')
            (run / 'narration.wav').write_bytes(b'voice fixture')
            audio = run / 'audio-output/report.json'
            write(audio, {'mode': 'narration_only', 'music_stage': 'skipped', 'music_tracks': [],
                          'narration_source_sha256': sha(run / 'narration.wav'), 'output_sha256': sha(run / 'film.mp4')})
            report = run / 'offline-qa/report.json'
            write(report, {'signature': 'fixture', 'movies': [{'file': 'film.mp4', 'sha256': sha(run / 'film.mp4')}],
                           'evidence_sha256': {}, 'audio_output_mode': 'narration_only', 'audio_report_sha256': sha(audio)})
            write(ep / 'review.json', {'signature': 'fixture', 'status': 'passed', 'blocking_issues': [],
                                      'reviewer': 'Synthetic test fixture', 'observations': 'Test only',
                                      'agent_response_file': 'response.md', 'agent_response_sha256': sha(ep / 'response.md'),
                                      'offline_report_sha256': sha(report)})
            p = {'workflow_version': '2.2.0', 'caption_layout': {'review_file': 'review.json'}}
            with patch('finishing.caption_signature', return_value='fixture'):
                release_gate(p, ep, run, root)
                (run / 'narration.wav').write_bytes(b'changed voice fixture')
                with self.assertRaisesRegex(ValueError, 'source/output'):
                    release_gate(p, ep, run, root)


if __name__ == '__main__':
    unittest.main()
