"""Codex-orchestrated video MVP: structured research/assets -> speech -> timed film.

Research, editorial review and built-in Imagegen are agent stages, never faked as API calls.
Requires Python 3.10+, Pillow, NumPy, FFmpeg and a font with script coverage.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import fcntl
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
import wave

from portable import project_root, resolve_font
ROOT = project_root()
VERSION = '2.1.0'
UA = 'CodexVideoStudio/1.0 (local educational media research)'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def filehash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        while chunk := f.read(1024 * 1024): h.update(chunk)
    return h.hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.' + uuid.uuid4().hex + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def command(args):
    p = subprocess.run([str(a) for a in args], capture_output=True, text=True)
    if p.returncode: raise RuntimeError(p.stderr[-5000:])
    return p.stdout


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=45) as r:
        return json.load(r)


def clean_html(value):
    return html.unescape(re.sub('<[^>]*>', '', value or ''))


def validate(p):
    if p.get('workflow_version') != '2.1.0': raise ValueError('Expected workflow_version 2.1.0')
    if not p.get('assets') or not p.get('sentences'):
        raise ValueError('Episode is only initialized; fill storyboard assets and narration sentences before production')
    if not re.fullmatch(r'[a-z0-9-]+', p['id']): raise ValueError('Episode ID must be kebab-case')
    if p['width'] % 2 or p['height'] % 2 or p['fps'] <= 0: raise ValueError('Invalid video format')
    assets = {a['id']: a for a in p['assets']}
    if len(assets) != len(p['assets']): raise ValueError('Duplicate asset IDs')
    claims = {c['id'] for c in p['research']['claims']}
    source_ids = {s['id'] for s in p['research']['sources']}
    for claim in p['research']['claims']:
        if not claim.get('source_ids') or not set(claim['source_ids']) <= source_ids:
            raise ValueError('Claim has no valid research source: ' + claim['id'])
    for s in p['sentences']:
        if s['asset'] not in assets: raise ValueError('Unknown asset: ' + s['asset'])
        if not s['captions'] or any(not x.strip() for x in s['captions']): raise ValueError('Empty caption')
        if re.sub(r'\W', '', s['text']) != re.sub(r'\W', '', ''.join(s['captions'])):
            raise ValueError('Caption does not match narration: ' + s['text'])
        if not set(s.get('claims', [])) <= claims: raise ValueError('Unknown factual claim')
        previous_cut = 0
        for cut in s.get('visual_cuts', []):
            if cut['asset'] not in assets or not previous_cut < cut['caption'] < len(s['captions']):
                raise ValueError('Invalid visual cut')
            previous_cut = cut['caption']
        if s.get('spoken_texts'):
            if len(s['spoken_texts']) != len(s['captions']): raise ValueError('Spoken clip count differs')
            for spoken, caption in zip(s['spoken_texts'], s['captions']):
                if re.sub(r'\W', '', spoken) != re.sub(r'\W', '', caption): raise ValueError('Spoken clip differs from caption')
    for a in assets.values():
        if a['kind'] not in {'commons','generated','prepared_image','video'}:
            raise ValueError('Unknown asset provider: ' + a['kind'])
        if a['kind'] in {'prepared_image','video'} and not all(a.get(k) for k in ['file','record_file']):
            raise ValueError('Local media needs file and record_file')
        if a.get('motion', 'gentle') not in {'gentle', 'static'}:
            raise ValueError('Unknown asset motion')
        if a['kind'] == 'commons' and (not a.get('license') or not a.get('author') or not a.get('page')):
            raise ValueError('Real image requires provenance and license')
        if a['kind'] == 'generated' and not a.get('prompt_file'): raise ValueError('Missing image prompt')
    return True


class Workflow:
    def __init__(self, episode):
        self.source = Path(episode).resolve()
        self.p = json.loads(self.source.read_text())
        validate(self.p)
        from portable import validate_scope
        validate_scope(self.p,self.source.parent,ROOT)
        self.brand = json.loads((ROOT / self.p['brand']).read_text())
        self.brand['subtitle']['font_file'] = resolve_font(self.brand['subtitle'].get('font_file', 'auto'), ROOT)
        inputs = {'episode': self.p, 'brand': self.brand}
        if self.p['speech']['provider'] == 'local':
            from local_audio import source_signature
            inputs['local_audio_sha256'] = source_signature(self.p['speech'], ROOT)
        if self.p.get('workflow_version', '').startswith('2.'):
            from visual_plan import local, context_check, design_signature
            context_check(self.p, self.source.parent)
            inputs['plan_sha256'] = filehash(local(self.source.parent, self.p['visual_plan']['file']))
            inputs['design_sha256'] = design_signature(self.p, self.source.parent)
            inputs['runtime_sha256'] = {name: filehash(Path(__file__).with_name(name)) for name in
                ['run.py','visual_plan.py','media_assets.py','transitions.py','caption_motion.py',
                 'tts_minimax.py','local_audio.py','audio_direction.py','review_video.py','finishing.py','portable.py']}
        from finishing import modern, music_signature
        if modern(self.p):
            inputs['music']=music_signature(ROOT,self.p['bgm'])
            inputs['font_sha256']=filehash(self.brand['subtitle']['font_file'])
        self.input_manifest = inputs
        self.run = ROOT / 'runs' / (self.p['id'] + '-' + digest(inputs)[:10])
        self.run.mkdir(parents=True, exist_ok=True)
        self.state_file = self.run / 'status.json'
        self.state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {'version': VERSION, 'stages': {}}
        write_json(self.run / 'episode.json', self.p)
        write_json(self.run / 'brand.json', self.brand)
        write_json(self.run / 'research.json', self.p['research'])
        if self.p.get('workflow_version', '').startswith('2.'):
            write_json(self.run / 'input-manifest.json', self.input_manifest)

    def complete(self, name, detail):
        self.record(name, dict(status='completed', completed_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'), **detail))

    def record(self, name, detail):
        with (self.run / '.status.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {'version': VERSION, 'stages': {}}
            state['stages'][name] = detail
            write_json(self.state_file, state)
            self.state = state

    def search(self):
        results = []
        for asset in self.p['assets']:
            if not asset.get('search_query'): continue
            query = asset['search_query']
            dest = self.run / 'search' / (asset['id'] + '.json')
            if dest.exists():
                data = json.loads(dest.read_text())
            else:
                params = {'action': 'query', 'format': 'json', 'generator': 'search', 'gsrsearch': query,
                          'gsrnamespace': 6, 'gsrlimit': 6, 'prop': 'imageinfo', 'iiprop': 'url|extmetadata|size'}
                response = get_json('https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(params))
                candidates = []
                for page in response.get('query', {}).get('pages', {}).values():
                    info = page.get('imageinfo', [{}])[0]; meta = info.get('extmetadata', {})
                    candidates.append({'title': page['title'], 'url': info.get('url'), 'page': info.get('descriptionurl'),
                                       'width': info.get('width'), 'height': info.get('height'),
                                       'author': clean_html(meta.get('Artist', {}).get('value')),
                                       'license': clean_html(meta.get('LicenseShortName', {}).get('value')),
                                       'license_url': meta.get('LicenseUrl', {}).get('value'),
                                       'description': clean_html(meta.get('ImageDescription', {}).get('value'))})
                data = {'query': query, 'provider': 'Wikimedia Commons API', 'candidates': candidates,
                        'selection': asset.get('selection_reason'), 'selected_page': asset.get('page'),
                        'review': 'pending_actual_editorial_and_rights_review'}
                write_json(dest, data)
            results.append({'asset': asset['id'], 'candidates': len(data['candidates']), 'query': query})
        self.complete('search', {'queries': results})
        print('Search:', results, flush=True)

    def fetch(self):
        from visual_plan import load_plan
        plan = load_plan(self.p, self.source.parent, ROOT)
        if plan is not None:
            write_json(self.run/'visual-plan.json', plan)
            shutil.copy2(self.source.parent/self.p['visual_plan']['review_file'], self.run/'visual-plan-review.json')
        assets_dir = self.run / 'assets'; assets_dir.mkdir(exist_ok=True)
        provenance = []
        for a in self.p['assets']:
            suffix = '.mp4' if a['kind']=='video' else ('.jpg' if a['kind']=='commons' else '.png')
            target = assets_dir / (a['id'] + suffix)
            if a['kind'] == 'commons':
                # Selection is an explicit editorial decision; no first-search-result auto-admission.
                if not target.exists():
                    req = urllib.request.Request(a['url'], headers={'User-Agent': UA})
                    with urllib.request.urlopen(req, timeout=60) as r: data = r.read()
                    temp = target.with_suffix('.partial' + suffix); temp.write_bytes(data)
                    from PIL import Image
                    with Image.open(temp) as im: im.verify()
                    os.replace(temp, target)
            elif a['kind'] == 'generated':
                source = ROOT / a['file']
                if plan is not None:
                    from visual_plan import local
                    record=json.loads(local(ROOT,a.get('generation_record','')).read_text())
                    review=record.get('review',{})
                    prompt=local(ROOT,a['prompt_file'])
                    if record.get('prompt',{}).get('sha256')!=filehash(prompt):raise ValueError('Generated prompt record missing/stale: '+a['id'])
                    if a.get('reference') and a['reference'] not in {x.get('path') for x in record.get('references',[])}:raise ValueError('Primary reference missing in generation record: '+a['id'])
                    for reference in record.get('references',[]):
                        if filehash(local(ROOT,reference['path']))!=reference['sha256']:raise ValueError('Generated reference record stale: '+a['id'])
                    if (record.get('output',{}).get('sha256')!=filehash(source)
                            or review.get('assistant_result') not in {'pass','assistant_visual_pass'}
                            or review.get('veto_findings')!=[] or not review.get('reviewer')):
                        raise ValueError('Generated image lacks current visual review: '+a['id'])
                if not source.exists(): raise FileNotFoundError(f'Imagegen stage pending: {source}')
                if not target.exists() or filehash(source) != filehash(target): shutil.copy2(source, target)
                record_dir = self.run / 'generation' / a['id']; record_dir.mkdir(parents=True, exist_ok=True)
                prompt_path = ROOT / a['prompt_file']; reference_path = ROOT / a['reference'] if a.get('reference') else None
                shutil.copy2(prompt_path, record_dir / 'prompt.txt')
                if reference_path: shutil.copy2(reference_path, record_dir / ('reference' + reference_path.suffix))
                write_json(record_dir / 'provenance.json', {'provider': a['provider'], 'model': a['model'], 'seed': a['seed'],
                           'prompt_sha256': filehash(prompt_path), 'reference_sha256': filehash(reference_path) if reference_path else None,
                           'image_sha256': filehash(source), 'actual_call_record': a.get('generation_record', 'Codex conversation imagegen result; see episode prompt and asset')})
            elif a['kind'] in {'prepared_image','video'}:
                from media_assets import validate_local
                from visual_plan import local
                size, info = validate_local(a, ROOT, filehash)
                source=local(ROOT,a['file'])
                if not target.exists() or filehash(source)!=filehash(target):shutil.copy2(source,target)
                record_dir=self.run/'generation'/a['id'];record_dir.mkdir(parents=True,exist_ok=True)
                shutil.copy2(local(ROOT,a['record_file']),record_dir/'media-record.json')
            else: raise ValueError('Unknown asset provider: ' + a['kind'])
            from PIL import Image
            if a['kind']!='video':
                with Image.open(target) as im: size = list(im.size)
            entry=dict(a, local_file=str(target.relative_to(self.run)), sha256=filehash(target), dimensions=size)
            record=a.get('record_file') or a.get('generation_record')
            if record and (ROOT/record).is_file():entry['record_sha256']=filehash(ROOT/record)
            provenance.append(entry)
        write_json(self.run / 'sources.json', provenance)
        self.complete('assets', {'files': len(provenance), 'sha256': digest(provenance)})

    def audio(self):
        from visual_plan import load_plan
        load_plan(self.p, self.source.parent, ROOT)
        provider = self.p['speech']['provider']
        if provider == 'minimax-cn': return self.audio_minimax()
        if provider == 'local':
            from local_audio import prepare
            timeline = prepare(self.p, self.source.parent, self.run, ROOT)
            self.complete('audio', {'provider': 'local', 'seconds': timeline['duration'],
                          'audio_sha256': filehash(self.run/'narration.wav'), 'timing': timeline['timing_method']})
            return
        raise ValueError('Supported speech providers: minimax-cn, local')

    def audio_minimax(self):
        from tts_minimax import synthesize, align
        from audio_direction import load_direction
        import numpy as np
        text, direction = load_direction(self.p, self.source.parent)
        if direction:
            (self.run / 'tts-request-text.txt').write_text(text)
            write_json(self.run / 'audio-direction.json', direction)
        folder, record = synthesize(text, self.p['speech'], ROOT / 'runs/tts-cache/minimax-cn')
        with wave.open(str(folder / 'audio.wav')) as audio:
            sr = audio.getframerate()
            samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2')
        before, after = self.p['intro_pause'], self.p['outro_pause']
        timeline = align(self.p['sentences'], json.loads((folder / 'subtitles.json').read_text()),
                         len(samples) / sr, before, after)
        timeline['fps'] = self.p['fps']
        joined = np.concatenate([np.zeros(round(before*sr), dtype='<i2'), samples,
                                 np.zeros(round(after*sr), dtype='<i2')])
        with wave.open(str(self.run / 'narration.wav'), 'wb') as output:
            output.setparams((1, 2, sr, 0, 'NONE', 'not compressed'))
            output.writeframes(joined.astype('<i2').tobytes())
        plain_text = '\n'.join(s['text'] for s in self.p['sentences'])
        (self.run / 'narration.txt').write_text(self.p['title'] + '\n\n' + plain_text)
        write_json(self.run / 'speech_request.json', record['request'])
        write_json(self.run / 'speech_result.json', dict(record, cache_folder=str(folder)))
        shutil.copy2(folder / 'subtitles.json', self.run / 'native-subtitles.json')
        write_json(self.run / 'timeline.json', timeline)
        self.complete('audio', {'provider': 'minimax-cn', 'model': self.p['speech']['model'],
                               'voice': self.p['speech']['voice'], 'seconds': timeline['duration'],
                               'usage_characters': record['usage_characters'],
                               'cost_estimate': record.get('cost_estimate'),
                               'billing_verified': False, 'timing': timeline['timing_method'],
                               'audio_sha256': filehash(self.run / 'narration.wav')})
        print('MiniMax narration:', round(timeline['duration'], 2), 'seconds', flush=True)

    def render(self):
        from visual_plan import render_gate
        render_gate(self.p,self.source.parent,self.run,ROOT)
        return self._render_verified_inputs()

    def _render_verified_inputs(self):
        from PIL import Image, ImageDraw, ImageFont, ImageOps
        import numpy as np
        p = self.p; w, h, fps = p['width'], p['height'], p['fps']
        timeline = json.loads((self.run / 'timeline.json').read_text())
        sources = {a['id']: a for a in json.loads((self.run / 'sources.json').read_text())}
        out = self.run / 'render'; out.mkdir(exist_ok=True)
        fontfile = Path(self.brand['subtitle']['font_file'])
        font = ImageFont.truetype(str(fontfile), round(w * self.brand['subtitle']['size_ratio']))
        small = ImageFont.truetype(str(fontfile), round(w*.022))
        brandfont = ImageFont.truetype(str(fontfile), round(w*.028))
        boundaries = [0] + [round(s['end']*fps) for s in timeline['scenes']]
        from transitions import transition_layout, join_dissolves
        transition = p.get('transition', {})
        if transition.get('type', 'cut') not in {'cut', 'cross-dissolve'}:
            raise ValueError('Unknown transition type')
        half_frames = round(transition.get('seconds', .48)*fps/2) if transition.get('type') == 'cross-dissolve' else 0
        plans = transition_layout(boundaries, half_frames)
        def make_shot(index):
            scene=timeline['scenes'][index]; asset=sources[scene['asset']]; image_path=self.run/asset['local_file']
            frames=plans[index]['render_frames']
            shot_hash=digest({'asset':filehash(image_path),'frames':frames,'size':[w,h],'fps':fps,'kind':asset['kind'],
                              'motion':asset.get('motion','gentle'),'asset_spec':asset,
                              'renderer':filehash(Path(__file__)),'font':filehash(fontfile),'index':index,'version':VERSION})
            dest=out/f'shot_{index+1:02d}_{shot_hash[:8]}.mp4'
            if dest.exists(): return dest
            if asset['kind']=='video':
                from media_assets import render_video
                temporary=dest.with_suffix('.partial.mp4')
                render_video(asset,image_path,temporary,w,h,fps,frames)
                os.replace(temporary,dest)
                return dest
            image_input=image_path
            if asset['kind']=='commons':
                # Keep the whole real specimen. No generative alteration of its internal structure.
                base=Image.new('RGB',(w,h),self.brand['palette']['dark'])
                photo=Image.open(image_path).convert('RGB'); photo=ImageOps.contain(photo,(w,round(h*.64)))
                base.paste(photo,((w-photo.width)//2,round(h*.18)))
                dd=ImageDraw.Draw(base)
                dd.text((w*.075,h*.12),asset.get('label','Source')+' · Photo',font=brandfont,fill='#F2F0F0')
                dd.text((w*.075,h*.86),asset['author']+' · '+asset['license'],font=small,fill='#F2F0F0')
                image_input=out/f'photo_{index:02d}_{shot_hash[:8]}.png'; base.save(image_input)
            z0,z1=(1.015,1.055) if index%2==0 else (1.055,1.015)
            if asset.get('motion') == 'static':
                z0,z1=1.0,1.0
            progress=f'(1-cos(PI*on/{max(frames-1,1)}))/2'
            vf=(f"scale={w*2}:{h*2}:force_original_aspect_ratio=increase,crop={w*2}:{h*2},"
                f"zoompan=z='{z0}+({z1}-{z0})*{progress}':x='(iw-iw/zoom)*(.4+.2*{progress})':y='(ih-ih/zoom)*.45':"
                f"d={frames}:s={w}x{h}:fps={fps},setsar=1,format=yuv420p")
            temporary=dest.with_suffix('.partial.mp4')
            command(['ffmpeg','-v','error','-y','-i',image_input,'-vf',vf,'-frames:v',frames,'-an','-c:v','libx264','-preset','fast','-crf','20','-threads','2',temporary])
            os.replace(temporary,dest)
            print('Shot',index+1,frames,'frames',flush=True)
            return dest
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            clips=list(ex.map(make_shot,range(len(timeline['scenes']))))
        # Relative filenames generated by us are ASCII and need no path escaping.
        concat=out/'concat.txt'; concat.write_text(''.join(f"file '{c.name}'\n" for c in clips))
        base_video=out/'pictures.mp4'
        if half_frames:
            base_video=join_dissolves(clips,plans,fps,half_frames,out)
        else:
            command(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',concat,'-c','copy',base_video])
        from finishing import modern, finish_film
        if modern(p):
            duration=finish_film(p,self.brand,self.source.parent,self.run,ROOT,base_video)
            def timestamp(t):
                n=round(t*1000);hh,n=divmod(n,3600000);mm,n=divmod(n,60000);ss,ms=divmod(n,1000)
                return f'{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}'
            final_captions=json.loads((out/'caption-placement.json').read_text())
            (self.run/'captions.srt').write_text('\n\n'.join(f'{i+1}\n{timestamp(c["start"])} --> {timestamp(c["end"])}\n{c["text"]}' for i,c in enumerate(final_captions))+'\n')
            self.complete('render',{'file':'film.mp4','sha256':filehash(self.run/'film.mp4'),'seconds':duration,
                'resolution':[w,h],'fps':fps,'validation':'pending_offline_layout_and_mix_review'})
            print('Film saved (not played):',self.run/'film.mp4',flush=True)
            return
        raise ValueError('This public runtime requires workflow_version 2.1.0')

    def verify(self):
        from finishing import release_gate
        release_gate(self.p,self.source.parent,self.run,ROOT)
        return self._verify_technical()

    def _verify_technical(self):
        from PIL import Image,ImageDraw
        final=self.run/'film.mp4'
        probe=json.loads(command(['ffprobe','-v','error','-show_streams','-show_format','-of','json',final]))
        video=next(s for s in probe['streams'] if s['codec_type']=='video')
        audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
        timeline=json.loads((self.run/'timeline.json').read_text())
        if (video['width'],video['height']) != (self.p['width'],self.p['height']):raise ValueError('Wrong dimensions')
        duration=float(probe['format']['duration'])
        if abs(duration-timeline['duration'])>1/self.p['fps']+.03:raise ValueError('Audio/video duration mismatch')
        if not all(a['end']<=b['start'] for a,b in zip(timeline['captions'],timeline['captions'][1:])):raise ValueError('Subtitle overlap')
        command(['ffmpeg','-v','error','-xerror','-i',final,'-f','null','-'])
        qa=self.run/'qa';qa.mkdir(exist_ok=True)
        times=[c['start']+min(.5,(c['end']-c['start'])/2) for c in timeline['captions']]
        picks=times[::max(1,len(times)//6)][:6]
        sheet=Image.new('RGB',(900,600*((len(picks)+2)//3)),'#292720')
        for i,t in enumerate(picks):
            path=qa/f'frame_{i:02d}.png'
            command(['ffmpeg','-v','error','-y','-ss',t,'-i',final,'-frames:v','1','-vf','scale=300:-1',path])
            im=Image.open(path);sheet.paste(im,((i%3)*300,(i//3)*600+25))
            ImageDraw.Draw(sheet).text(((i%3)*300+10,(i//3)*600+5),f'{t:.2f}s',fill='white')
        sheet.save(qa/'contactsheet.jpg')
        scene_lengths = [s['end']-s['start'] for s in timeline['scenes']]
        sources = {s['id']: s for s in json.loads((self.run/'sources.json').read_text())}
        image_hashes = [filehash(self.run/sources[s['asset']]['local_file']) for s in timeline['scenes']]
        from media_assets import visual_identity
        from transitions import transition_layout
        transition=self.p.get('transition',{})
        half_frames=round(transition.get('seconds',.48)*self.p['fps']/2) if transition.get('type')=='cross-dissolve' else 0
        layouts=transition_layout([0]+[round(s['end']*self.p['fps']) for s in timeline['scenes']],half_frames)
        identities=[visual_identity(sources[s['asset']],self.run/sources[s['asset']]['local_file'],h,
                                    layout['render_frames'],self.p['fps'])
                    for s,h,layout in zip(timeline['scenes'],image_hashes,layouts)]
        repeats = len(identities)-len(set(identities))
        if self.p.get('no_repeated_images') and repeats:
            raise ValueError('Repeated visual content in a no-repeat episode')
        expected_frames = round(timeline['duration']*self.p['fps'])
        if int(video['nb_frames']) != expected_frames:
            raise ValueError('Unexpected frame count after transitions')
        transition_file = self.run/'render/transitions.json'
        transition_data = json.loads(transition_file.read_text()) if transition_file.exists() else {'events': []}
        if self.p.get('transition',{}).get('type') == 'cross-dissolve':
            if len(transition_data['events']) != len(image_hashes)-1:
                raise ValueError('Missing transition events')
        report={'full_decode_passed':True,'duration':duration,'video_codec':video['codec_name'],'audio_codec':audio['codec_name'],
                'resolution':[video['width'],video['height']],'captions':len(timeline['captions']),
                'shots':len(timeline['scenes']), 'unique_assets':len({s['asset'] for s in timeline['scenes']}),
                'unique_image_sha256':len({h for h,s in zip(image_hashes,timeline['scenes']) if sources[s['asset']]['kind']!='video'}),
                'repeat_occurrences':repeats, 'unique_visual_segments':len(set(identities)),
                'unique_media_sha256':len(set(image_hashes)),
                'asset_kinds':sorted({a['kind'] for a in sources.values()}),
                'adjacent_duplicate_images':sum(a==b and isinstance(a,str) for a,b in zip(identities,identities[1:])),
                'adjacent_duplicate_visual_segments':sum(a==b for a,b in zip(identities,identities[1:])),
                'video_frames':int(video['nb_frames']), 'transition_count':len(transition_data['events']),
                'transition':self.p.get('transition',{'type':'cut'}),
                'caption_motion':self.p.get('caption_motion',{'type':'cut'}),
                'longest_shot_seconds':max(scene_lengths),
                'subtitle_overlap':False,'human_listening':'pending','brand_identity_acceptance':'pending','sha256':filehash(final)}
        write_json(qa/'validation.json',report)
        from review_video import create_page
        create_page(self.run)
        self.complete('verify',report)
        print(json.dumps(report,ensure_ascii=False,indent=2))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('stage',choices=['validate','search','fetch','audio','render','verify','all','status'])
    ap.add_argument('--episode',required=True,
                    help='Explicit prepared episode.json path; no implicit historical episode is selected.')
    args=ap.parse_args(); job=Workflow(args.episode)
    print('Run:',job.run,flush=True)
    if args.stage=='validate':print('Input valid');return
    if args.stage=='status':print(json.dumps(job.state,ensure_ascii=False,indent=2));return
    stages=(['audio','search','fetch','render','verify'] if job.p.get('workflow_version','').startswith('2.') else
            ['search','fetch','audio','render','verify']) if args.stage=='all' else [args.stage]
    for stage in stages:
        try:getattr(job,stage)()
        except Exception as e:
            job.record(stage, {'status':'failed','error':str(e)})
            raise


if __name__=='__main__':main()
