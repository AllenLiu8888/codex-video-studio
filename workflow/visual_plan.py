"""V2 planning gates: design -> independent review -> measured timing -> preview review.

No model or network calls. Design is immutable per run; timing lives in the run.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from portable import project_root, resolve_font
ROOT = project_root()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def local(base, name):
    path = (Path(base) / name).resolve()
    if not path.is_relative_to(Path(base).resolve()):
        raise ValueError('Planning path escapes its scope: ' + name)
    return path


def norm(text):
    return re.sub(r'\W', '', text)


def expected_shots(p):
    result = []
    for i, sentence in enumerate(p['sentences'], 1):
        cuts = [{'caption': 0, 'asset': sentence['asset']}] + sentence.get('visual_cuts', [])
        for n, cut in enumerate(cuts):
            end = cuts[n+1]['caption'] if n+1 < len(cuts) else len(sentence['captions'])
            result.append({'anchor': {'sentence': i, 'caption': cut['caption']},
                           'asset_id': cut['asset'],
                           'source_text': ''.join(sentence['captions'][cut['caption']:end])})
    return result


def is_v2(p):
    return str(p.get('workflow_version', '1')).split('.')[0] == '2'


def context_check(p, episode):
    if not is_v2(p):
        return
    ep = Path(episode)
    spec = p.get('visual_plan', {})
    for key in ['file', 'review_file']:
        if not spec.get(key):
            raise ValueError('Missing visual_plan.' + key)
        local(ep, spec[key])
    plan = json.loads(local(ep, spec['file']).read_text())
    if plan.get('schema_version') != 1 or plan.get('episode_id') != p['id']:
        raise ValueError('Wrong plan schema or episode')
    if plan.get('narration_sha256') != sha(ep / 'narration.txt'):
        raise ValueError('Plan belongs to a different narration')
    snapshot=json.loads((ep/'generation/seed-snapshot.json').read_text())
    for file_name, rule_name in [('workflow-version.json','workflow/version.json'),('visual-methods.json','workflow/visual-methods.json')]:
        if sha(ep/'generation'/file_name)!=snapshot['rule_files'].get(rule_name):
            raise ValueError('Frozen planning contract changed: '+file_name)
    frozen = json.loads((ep / 'generation/workflow-version.json').read_text())
    if frozen['workflow_version'] != p['workflow_version']:
        raise ValueError('Workflow version differs from episode snapshot')


def design_signature(p, episode):
    plan_file = local(episode, p['visual_plan']['file'])
    plan = json.loads(plan_file.read_text())
    tasks = {s['task_file']: sha(local(episode, s['task_file'])) for s in plan.get('shots', []) if s.get('task_file')}
    value = {'plan_sha256': sha(plan_file), 'tasks': tasks, 'methods_sha256':sha(Path(episode)/'generation/visual-methods.json'), 'assets': p['assets'], 'sentences': p['sentences']}
    from finishing import modern
    if modern(p):value['caption_settings']={k:p.get(k) for k in ['caption_layout','caption_motion','transition']}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def load_plan(p, episode, root=ROOT, reviewed=True):
    if not is_v2(p):
        return None
    ep = Path(episode)
    context_check(p, ep)
    plan_file = local(ep, p['visual_plan']['file'])
    plan = json.loads(plan_file.read_text())
    if ''.join(re.sub(r'\s', '', s['text']) for s in p['sentences']) != re.sub(r'\s', '', (ep/'narration.txt').read_text()):
        raise ValueError('Episode narration differs from locked script')
    methods = json.loads((ep/'generation/visual-methods.json').read_text())['methods']
    expected = expected_shots(p)
    shots = plan.get('shots', [])
    if not shots or len(shots) != len(expected):
        raise ValueError('Plan must cover every configured shot exactly once')
    seen = set(); motion_ids = []; previous = None; closed = set()
    assets = {a['id']: a for a in p['assets']}
    for shot, target in zip(shots, expected):
        sid = shot.get('id')
        if not sid or sid in seen:
            raise ValueError('Missing or duplicate shot id')
        seen.add(sid)
        if any(shot.get(k) != target[k] for k in ['anchor', 'asset_id']):
            raise ValueError('Shot anchor/asset does not match narration order: ' + sid)
        if norm(shot.get('source_text', '')) != norm(target['source_text']):
            raise ValueError('Shot source text differs: ' + sid)
        for key in ['segment_id', 'viewer_takeaway', 'selection_reason', 'visual_description', 'fallback']:
            if not isinstance(shot.get(key), str) or not shot[key].strip():
                raise ValueError('Missing shot ' + key + ': ' + sid)
        if shot.get('meaning') not in {'fact', 'explanation', 'legend', 'metaphor', 'brand'}:
            raise ValueError('Unknown meaning: ' + sid)
        method = methods.get(shot.get('method'))
        if not method or method.get('enabled') is False:
            raise ValueError('Unknown visual method: ' + sid)
        if shot.get('source_type') not in method['source_types']:
            raise ValueError('Source type incompatible with method: ' + sid)
        asset = assets[shot['asset_id']]
        if asset['kind'] not in method['asset_kinds']:
            raise ValueError('Asset kind incompatible with method: ' + sid)
        if shot.get('source_type') in {'real_photo', 'real_video', 'archive'}:
            required = ['page', 'author', 'license', 'license_url', 'subject', 'relevance', 'rights_review']
            if any(not asset.get(k) for k in required):
                raise ValueError('Real media lacks identity/rights/provenance: ' + sid)
        task = local(ep, shot.get('task_file', ''))
        if not task.is_file() or not task.read_text().strip():
            raise ValueError('Missing actual production task: ' + sid)
        from finishing import modern, validate_layout
        if modern(p):validate_layout(shot.get('caption_layout', {}))
        mid = shot.get('complex_motion_segment')
        if bool(mid) != method['complex_motion']:
            raise ValueError('Complex motion classification differs: ' + sid)
        if mid != previous:
            if previous:
                closed.add(previous)
            if mid in closed:
                raise ValueError('Noncontiguous animation segment reused: ' + str(mid))
        if mid:
            motion_ids.append(mid)
        previous = mid
    if len(set(motion_ids)) > 2:
        raise ValueError('More than two complex motion segments')
    if reviewed:
        review = json.loads(local(ep, p['visual_plan']['review_file']).read_text())
        if (review.get('status') != 'passed' or review.get('plan_sha256') != sha(plan_file)
                or review.get('design_sha256') != design_signature(p, ep)):
            raise ValueError('Plan review missing or stale')
        response = local(ep, review.get('agent_response_file', ''))
        if not review.get('reviewer') or not response.is_file() or not response.read_text().strip():
            raise ValueError('Missing actual independent review response')
        if review.get('agent_response_sha256') != sha(response):
            raise ValueError('Independent review response changed')
        if review.get('blocking_issues') != []:
            raise ValueError('Plan still has blocking issues')
    return plan


def measured_timing(p, episode, run, root=ROOT):
    plan = load_plan(p, episode, root)
    if plan is None:
        raise ValueError('Timing plan requires an explicit v2 episode')
    run = Path(run)
    if json.loads((run/'episode.json').read_text()) != p:
        raise ValueError('Run episode is not the current configuration')
    t = json.loads((run/'timeline.json').read_text())
    if len(t['scenes']) != len(plan['shots']):
        raise ValueError('Timeline shot count differs')
    shots = []
    for shot, scene in zip(plan['shots'], t['scenes']):
        if scene['asset'] != shot['asset_id'] or scene['sentence'] != shot['anchor']['sentence']:
            raise ValueError('Timeline does not follow reviewed shot plan')
        shots.append({'id': shot['id'], 'asset_id': scene['asset'], 'start': scene['start'],
                      'end': scene['end'], 'complex_motion_segment': shot.get('complex_motion_segment'),
                      'source_type': shot['source_type']})
    return {'schema_version': 1, 'plan_sha256': sha(local(episode, p['visual_plan']['file'])),
            'audio_sha256': sha(run/'narration.wav'), 'timeline_sha256': sha(run/'timeline.json'),
            'duration': t['duration'], 'shots': shots,
            'complex_motion_segments':len({s['complex_motion_segment'] for s in shots if s['complex_motion_segment']}),
            'complex_shot_seconds':round(sum(s['end']-s['start'] for s in shots if s['complex_motion_segment']),3),
            'motion_measurement_note':'Complex shot duration is an exposure upper bound, not measured active movement time.'}


def render_gate(p, episode, run, root=ROOT):
    if not is_v2(p):
        return
    run = Path(run)
    current = measured_timing(p, episode, run, root)
    if json.loads((run/'timing-plan.json').read_text()) != current:
        raise ValueError('Measured timing plan missing/stale; run plan timing again')
    review = json.loads((run/'visual-preview-review.json').read_text())
    if review.get('status') != 'passed' or review.get('timing_sha256') != sha(run/'timing-plan.json'):
        raise ValueError('Preview review missing or stale')
    evidence = local(run, review.get('preview_file', ''))
    if not evidence.is_file() or review.get('preview_sha256') != sha(evidence):
        raise ValueError('Preview evidence missing or changed')
    if not review.get('reviewer') or not review.get('observations') or review.get('blocking_issues') != []:
        raise ValueError('Preview review is incomplete')
    # New file bytes at an existing path must not reuse an accepted preview.
    assets = {a['id']: a for a in json.loads((run/'sources.json').read_text())}
    if review.get('sources_sha256')!=sha(run/'sources.json'):
        raise ValueError('Fetched asset specifications changed since preview')
    configured={a['id']:a for a in p['assets']}
    if set(assets)!=set(configured):raise ValueError('Fetched asset set differs')
    for aid,asset in assets.items():
        if any(asset.get(k)!=v for k,v in configured[aid].items()):
            raise ValueError('Fetched specification differs from configuration: '+aid)
        record=asset.get('record_file') or asset.get('generation_record')
        if record and asset.get('record_sha256')!=sha(local(root,record)):
            raise ValueError('Asset review record changed: '+aid)
    actual = {aid: sha(local(run, a['local_file'])) for aid, a in assets.items()}
    if review.get('asset_sha256') != actual:
        raise ValueError('Assets changed since preview review')
    for aid, a in assets.items():
        if a['kind']=='video':
            playback=review.get('clip_playback', {}).get(aid, {})
            spec=hashlib.sha256(json.dumps(a,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            if (playback.get('source_sha256')!=actual[aid] or playback.get('asset_spec_sha256')!=spec
                    or playback.get('played') is not True or not playback.get('reviewer')
                    or not playback.get('observations') or playback.get('blocking_issues')!=[]):
                raise ValueError('Actual video segment playback missing/stale: '+aid)
        if a['sha256'] != actual[aid]:
            raise ValueError('Fetched source changed: ' + aid)
        if a.get('file') and sha(local(root, a['file'])) != actual[aid]:
            raise ValueError('Original asset changed; fetch and review again: ' + aid)


def preview(p, episode, run, root=ROOT):
    """Cheap timed storyboard from fetched image/video first frames; not a final film."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    import subprocess
    run = Path(run); timing = measured_timing(p, episode, run, root)
    write(run/'timing-plan.json', timing)
    sources_file=run/'sources.json'
    sources = {a['id']: a for a in json.loads(sources_file.read_text())} if sources_file.exists() else {}
    plan = load_plan(p, episode, root)
    folder = run/'planning-preview'; folder.mkdir(exist_ok=True)
    brand = json.loads(local(root, p['brand']).read_text())
    brand['subtitle']['font_file'] = resolve_font(brand['subtitle'].get('font_file', 'auto'), root)
    font = ImageFont.truetype(brand['subtitle']['font_file'], 17)
    w,h=270,480; fps=p['fps']; clips=[]
    for index,(s,design) in enumerate(zip(timing['shots'],plan['shots'])):
        asset=sources.get(s['asset_id']); source=local(run,asset['local_file']) if asset else None
        if asset and asset['kind']=='video':
            still=folder/f'{index:03d}-source.png'
            subprocess.run(['ffmpeg','-v','error','-y','-ss',str(asset.get('in_seconds',0)),'-i',str(source),'-frames:v','1',str(still)],check=True)
            source=still
        canvas=Image.new('RGB',(w,h),brand.get('palette',{}).get('dark','#17283B'))
        if source:
            im=ImageOps.contain(Image.open(source).convert('RGB'),(w,h-80)); canvas.paste(im,((w-im.width)//2,0))
        else:
            draw=ImageDraw.Draw(canvas)
            text=design['visual_description']
            for j in range(0,min(len(text),120),14):draw.text((8,45+j//14*25),text[j:j+14],font=font,fill='#EFE2C8')
        d=ImageDraw.Draw(canvas); d.text((6,h-72),design['id']+' / '+design['method'],font=font,fill='#EFE2C8')
        d.text((6,h-42),f"{s['start']:.2f}–{s['end']:.2f}s",font=font,fill='#EFE2C8')
        img=folder/f'{index:03d}.png'; canvas.save(img)
        clip=folder/f'{index:03d}.mp4'; frames=round(s['end']*fps)-round(s['start']*fps)
        subprocess.run(['ffmpeg','-v','error','-y','-loop','1','-i',str(img),'-r',str(fps),'-frames:v',str(frames),'-c:v','libx264','-pix_fmt','yuv420p','-an',str(clip)],check=True)
        clips.append(clip)
    listing=folder/'concat.txt';listing.write_text(''.join(f"file '{c.name}'\n" for c in clips))
    dest=run/'storyboard-preview.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-i',str(run/'narration.wav'),'-c:v','copy','-c:a','aac','-shortest',str(dest)],check=True)
    review=run/'visual-preview-review.json'
    if not review.exists():
        write(review,{'status':'pending','reviewer':None,'observations':None,'blocking_issues':None,'clip_playback':{},
                      'timing_sha256':sha(run/'timing-plan.json'),'preview_file':dest.name,'preview_sha256':sha(dest),
                      'sources_sha256':sha(sources_file) if sources_file.exists() else None,
                      'asset_sha256':{k:sha(local(run,v['local_file'])) for k,v in sources.items()},
                      'note':'Still-board preview only. Complex motion and transitions also require actual segment playback.'})
    return dest


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stage',choices=['signature','design','reviewed','timing','preview','render-ready'])
    ap.add_argument('--episode',required=True);ap.add_argument('--run')
    args=ap.parse_args(); ep=Path(args.episode).resolve();p=json.loads(ep.read_text())
    if args.stage in {'timing','preview','render-ready'} and not args.run:ap.error('--run is required')
    if args.stage=='signature':
        print(json.dumps({'plan_sha256':sha(local(ep.parent,p['visual_plan']['file'])),
                          'design_sha256':design_signature(p,ep.parent)},indent=2))
    elif args.stage in {'design','reviewed'}:load_plan(p,ep.parent,reviewed=args.stage=='reviewed')
    elif args.stage=='timing':write(Path(args.run)/'timing-plan.json',measured_timing(p,ep.parent,args.run))
    elif args.stage=='preview':print(preview(p,ep.parent,args.run))
    else:render_gate(p,ep.parent,args.run)
    print('PLAN PASS:',args.stage,'(file/contract checks; not human aesthetic acceptance)')


if __name__=='__main__':
    try:main()
    except (ValueError,KeyError,TypeError,OSError) as e:raise SystemExit('PLAN FAIL: '+str(e))
