"""Composition-aware captions, explicit audio routing and visible openings. No playback/UI.

V2.1/2.2 contracts retain their selected audio and opening behavior. Coordinates describe
the final frame, not the uncropped source. A caption never moves while visible.
"""
from pathlib import Path
import hashlib
import json
import math
import subprocess
from portable import resolve_font


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, value):
    Path(p).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def modern(p):
    return tuple(int(x) for x in p.get('workflow_version', '1.0').split('.')[:2]) >= (2, 1)


def audio_mode(p):
    """New productions skip music; frozen 2.1 configurations retain their route."""
    default = 'narration_only' if tuple(int(x) for x in p.get('workflow_version', '1.0').split('.')[:2]) >= (2, 2) else 'licensed_bgm'
    mode = p.get('audio_output', {}).get('mode', default)
    if mode not in {'narration_only', 'licensed_bgm'}:
        raise ValueError('Unknown audio output mode: ' + str(mode))
    return mode


def audio_signature(root, p):
    mode = audio_mode(p)
    return {'mode': mode} if mode == 'narration_only' else {'mode': mode, **music_signature(root, p['bgm'])}


def opening_graph(p, input_label, output_label):
    """Keep a continuous first shot; an explicit visible lift avoids a black first frame."""
    config = p.get('opening')
    if config is None:
        return f'[{input_label}]fade=t=in:st=0:d=0.3[{output_label}]'
    if config.get('style') != 'visible_smooth_lift':
        raise ValueError('Unknown opening style')
    initial = config.get('initial_brightness', .78)
    seconds = config.get('seconds', .8)
    if isinstance(initial, bool) or not isinstance(initial, (int, float)) or not math.isfinite(initial) or not 0 < initial <= 1:
        raise ValueError('Opening brightness must be visible and at most 1')
    if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('Opening duration must be positive')
    q = f'clip(T/{seconds},0,1)'
    ease = f'({q}*{q}*(3-2*{q}))'
    return (f'[{input_label}]split[opening-source][opening-dim];'
            f"[opening-dim]lut=y='16+(val-16)*{initial}':u='128+(val-128)*{initial}':v='128+(val-128)*{initial}'[opening-dimmed];"
            f"[opening-source][opening-dimmed]blend=all_expr='A+(B-A)*(1-{ease})':enable='lt(t,{seconds})'[{output_label}]")


def mux_narration_only(visual, narration, dest, duration, title, report_dir=None):
    """Normalize supplied clean narration and copy visuals; no music node is called."""
    if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('Final duration must be positive')
    visual, narration, dest = map(Path, (visual, narration, dest))
    out = Path(report_dir) if report_dir else dest.parent / 'audio-output'
    out.mkdir(parents=True, exist_ok=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    probe = json.loads(run_command(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', narration]).stdout)
    if len([s for s in probe['streams'] if s['codec_type'] == 'audio']) != 1:
        raise ValueError('Narration must contain exactly one audio stream')
    source_duration = float(probe['format']['duration'])
    if source_duration > duration + .05:
        raise ValueError('Narration would be truncated by the final visual duration')
    normalized = out / 'narration-normalized.wav'
    normalize(narration, normalized, target=-17)
    run_command(['ffmpeg', '-v', 'error', '-y', '-i', visual, '-i', normalized,
                 '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                 '-ar', '48000', '-af', 'apad', '-t', duration, '-movflags', '+faststart',
                 '-metadata', 'title=' + title, '-metadata', 'comment=Clean narration only; no background music', dest])
    loud = measure(dest)
    if abs(float(loud['input_i']) + 17) > 1 or float(loud['input_tp']) > -1.4:
        raise ValueError('Narration output loudness/true peak outside delivery tolerance')
    def video_hash(path):
        return run_command(['ffmpeg', '-v', 'error', '-i', path, '-map', '0:v:0', '-c', 'copy',
                            '-f', 'hash', '-hash', 'sha256', '-']).stdout.strip()
    visual_hash = video_hash(visual)
    if video_hash(dest) != visual_hash:
        raise ValueError('Narration mux changed the visual stream')
    report = {'mode': 'narration_only', 'music_stage': 'skipped', 'music_tracks': [],
              'narration_source': narration.name, 'narration_source_sha256': sha(narration),
              'narration_duration': source_duration, 'duration': duration,
              'normalized_narration_sha256': sha(normalized),
              'processing': 'Original narration, two-pass -17 LUFS normalization; silence padding only; no music mix',
              'video_stream_sha256': visual_hash, 'output_file': dest.name, 'output_sha256': sha(dest),
              'loudness': loud, 'subjective_listening': 'pending_user_acceptance'}
    write(out / 'report.json', report)
    return report


def box(value):
    if not isinstance(value, list) or len(value) != 4 or not all(
            isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value):
        raise ValueError('Layout box must be finite [x,y,width,height]')
    x,y,w,h=value
    if min(x,y)<0 or min(w,h)<=0 or x+w>1 or y+h>1:
        raise ValueError('Layout box outside frame')
    return value


def overlap(a,b):
    return min(a[0]+a[2],b[0]+b[2])>max(a[0],b[0]) and min(a[1]+a[3],b[1]+b[3])>max(a[1],b[1])


def validate_layout(layout):
    bounds=box(layout.get('box'))
    if bounds[0]<.05 or bounds[1]<.04 or bounds[0]+bounds[2]>.95 or bounds[1]+bounds[3]>.94:
        raise ValueError('Caption violates mobile safe margins')
    if layout.get('theme') not in {'light_text','dark_text'} or layout.get('align') not in {'center','left'}:
        raise ValueError('Unknown caption theme/alignment')
    if layout.get('max_lines') not in [1,2] or not layout.get('reason') or not layout.get('layout_group'):
        raise ValueError('Caption needs line limit, group and composition reason')
    if 'protected_regions' not in layout:
        raise ValueError('Caption needs reviewed subject regions')
    for r in layout['protected_regions']:
        if not r.get('reason') or overlap(bounds,box(r['box'])):
            raise ValueError('Caption collides with protected subject')


def resolve_captions(plan,timeline,settings):
    from caption_motion import display_intervals
    scenes=timeline['scenes']; shots=plan['shots']; result=[]
    handle=settings.get('transition_seconds',.48)/2
    for c in display_intervals(timeline['captions'],settings.get('bridge_gap',.18)):
        index=next((i for i,s in enumerate(scenes) if s['start']<=c['start']<s['end']),len(scenes)-1)
        layout=shots[index]['caption_layout'];validate_layout(layout)
        # During dissolves/short bridged gaps, the same text box must be safe in
        # both visible pictures. Never resolve this by jumping within a caption.
        for j,s in enumerate(scenes):
            if s['start']-handle<c['end'] and s['end']+handle>c['start']:
                for r in shots[j]['caption_layout']['protected_regions']:
                    if overlap(layout['box'],r['box']):
                        if j<index and c['start']>=scenes[index]['start']-1e-6:
                            c['start']=max(c['start'],s['end']+handle)
                        elif j>index and c['end']<=scenes[index]['end']+1e-6:
                            c['end']=min(c['end'],s['start']-handle)
                        else:raise ValueError(f'Caption crosses unsafe scene {j+1}: {c["text"]}')
        if c['end']-c['start']<.6:raise ValueError('Dissolve leaves too little subtitle reading time')
        result.append(dict(c,asset=scenes[index]['asset'],layout=layout))
    return result


def caption_signature(p,ep,run,root):
    plan=json.loads((ep/p['visual_plan']['file']).read_text())
    brand=json.loads((root/p['brand']).read_text())
    value={'plan':sha(ep/p['visual_plan']['file']),'timeline':sha(run/'timeline.json'),
           'sources':sha(run/'sources.json'),'font':sha(resolve_font(brand['subtitle'].get('font_file','auto'), root)),'subtitle_style':brand['subtitle'],
           'settings':{k:p.get(k) for k in ['caption_motion','caption_layout','transition','opening','audio_output','width','height','fps']},
           'assets':[(a['id'],sha(root/a['file']),a.get('motion','gentle')) for a in p['assets']],
           'renderer':sha(__file__)}
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def wrap(text,font,width,draw,max_lines):
    lines=['']
    for ch in text:
        if draw.textlength(lines[-1]+ch,font=font)>width and lines[-1]:lines.append(ch)
        else:lines[-1]+=ch
    if len(lines)>max_lines:raise ValueError('Caption needs a wider safe box or a natural subtitle split: '+text)
    return lines


def render_caption_layers(p,plan,timeline,brand,out):
    from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageColor
    w,h=p['width'],p['height'];font=ImageFont.truetype(brand['subtitle']['font_file'],round(w*brand['subtitle']['size_ratio']))
    resolved=resolve_captions(plan,timeline,dict(p.get('caption_motion',{}),transition_seconds=p['transition'].get('seconds',0)))
    layers=[];records=[]
    for i,c in enumerate(resolved):
        l=c['layout']; x,y,bw,bh=[round(v*s) for v,s in zip(l['box'],[w,h,w,h])]
        layer=Image.new('RGBA',(w,h));d=ImageDraw.Draw(layer)
        lines=wrap(c['text'],font,bw-30,d,l['max_lines']); step=round(font.size*1.38);text_h=step*len(lines)
        if text_h+30>bh:raise ValueError('Caption too tall for planned safe box')
        top=y+(bh-text_h)//2
        widths=[d.textlength(t,font=font) for t in lines];left=x+(bw-max(widths))/2 if l['align']=='center' else x+15
        ink=(round(left),top,round(left+max(widths)),top+text_h)
        # A small blurred plate follows the text's fade. No full-screen bottom scrim.
        dark=l['theme']=='dark_text'
        # Blur alpha only. Blurring straight RGBA also darkens RGB at transparent
        # edges, producing an unintended dirty halo on ivory paper.
        style=brand['subtitle']; light=ImageColor.getrgb(style.get('light_text','#F5F2E9')); ink_dark=ImageColor.getrgb(style.get('dark_text','#17283B'))
        plate=Image.new('RGBA',(w,h),(*light,0) if dark else (*ink_dark,0))
        mask=Image.new('L',(w,h));pd=ImageDraw.Draw(mask)
        pd.rounded_rectangle((ink[0]-12,ink[1]-8,ink[2]+12,ink[3]+8),radius=18,fill=85 if dark else 105)
        plate.putalpha(mask.filter(ImageFilter.GaussianBlur(14)))
        layer=plate;d=ImageDraw.Draw(layer)
        for n,text in enumerate(lines):
            tx=x+bw/2 if l['align']=='center' else x+15
            d.text((tx,top+n*step),text,font=font,anchor='mt' if l['align']=='center' else 'lt',
                   fill=ink_dark if dark else light,stroke_width=1,
                   stroke_fill=(*light,90) if dark else (*ink_dark,170))
        layer.save(out/f'caption_{i:03d}.png');layers.append(layer)
        records.append(dict(index=i,text=c['text'],start=c['start'],end=c['end'],asset=c['asset'],
                            box=l['box'],ink_pixels=list(ink),lines=lines,font_size=font.size,theme=l['theme']))
    write(out/'caption-placement.json',records)
    return layers,resolved


def run_command(args):
    p=subprocess.run([str(x) for x in args],capture_output=True,text=True)
    if p.returncode:raise RuntimeError(p.stderr[-4000:])
    return p


def measure(file,target=-17,lra=7):
    p=run_command(['ffmpeg','-hide_banner','-nostats','-i',file,'-af',f'loudnorm=I={target}:TP=-1.5:LRA={lra}:print_format=json','-f','null','-'])
    return json.loads(p.stderr[p.stderr.rfind('{'):p.stderr.rfind('}')+1])


def normalize(source,dest,target=-17):
    v=measure(source,target=target,lra=7)
    f=(f'loudnorm=I={target}:TP=-1.5:LRA=7:measured_I={v["input_i"]}:measured_TP={v["input_tp"]}:'
       f'measured_LRA={v["input_lra"]}:measured_thresh={v["input_thresh"]}:offset={v["target_offset"]}:linear=true:print_format=json')
    run_command(['ffmpeg','-v','error','-y','-i',source,'-af',f,'-ar','48000','-c:a','pcm_s24le',dest])
    return measure(dest)


def load_music(root,config):
    if config.get('enabled') is False: return []
    catalog_path=(root/config['catalog_file']).resolve()
    if not catalog_path.is_relative_to(root.resolve()):raise ValueError('Music catalog outside project')
    catalog=json.loads(catalog_path.read_text())
    by_id={t['id']:t for t in catalog['tracks']}
    ids=[config['default_track']]+config.get('alternatives',[])
    if not 1<=len(ids)<=3 or len(set(ids))!=len(ids):raise ValueError('Choose one default and zero to two distinct BGM alternatives')
    tracks=[]
    for tid in ids:
        t=by_id[tid];file=(root/t['file']).resolve()
        if not file.is_relative_to(root.resolve()) or sha(file)!=t['sha256']:raise ValueError('BGM bytes missing/changed: '+tid)
        for k in ['license','license_url','detail_url','attribution_text','modification_disclosure']:
            if not t.get(k):raise ValueError('Incomplete music license: '+tid)
        tracks.append(t)
    return tracks


def music_signature(root,config):
    tracks=load_music(root,config)
    return {'catalog':sha(root/config['catalog_file']) if tracks else None,'tracks':{t['id']:t['sha256'] for t in tracks}}


def mix_music(root,run,p,duration):
    """Calibrate each cue, then slow envelope ducking; preserve original voice stem."""
    import numpy as np
    tracks=load_music(root,p['bgm']);out=run/'audio-mix';out.mkdir(exist_ok=True)
    if not tracks:
        final=out/'voice-only.wav'; metrics=normalize(run/'narration.wav',final)
        results=[{'role':'default','mix_file':str(final.relative_to(run)),'attribution_text':'No background music','license_url':'','modification_disclosure':'Narration normalized','mixed_wav_loudness':metrics,'subjective_listening':'pending'}]
        write(out/'mix-report.json',{'voice_source_sha256':sha(run/'narration.wav'),'duration':duration,'processing':'voice-only normalized','tracks':results})
        return results
    def pcm(file,extra=()):
        return np.frombuffer(subprocess.check_output(['ffmpeg','-v','error',*extra,'-i',str(file),'-t',str(duration),
                    '-f','f32le','-ar','48000','-ac','2','-']),dtype='<f4').reshape(-1,2).copy()
    normalize(run/'narration.wav',out/'voice-calibrated.wav',target=-18)
    voice=pcm(out/'voice-calibrated.wav');n=round(duration*48000);voice=np.pad(voice,((0,max(0,n-len(voice))),(0,0)))[:n]
    hop=4800; blocks=math.ceil(n/hop)
    levels=np.array([np.sqrt(np.mean(voice[i*hop:(i+1)*hop]**2)+1e-12) for i in range(blocks)])
    active=levels>10**(-38/20); gain=[];g=1.0;hold=0
    for a in active:
        if a:hold=5
        else:hold=max(0,hold-1)
        target=10**(-4/20) if hold else 1.0
        g+=(target-g)*(0.8 if target<g else .065);gain.append(g)
    envelope=np.interp(np.arange(n),np.arange(blocks)*hop,gain)
    results=[]
    def wav(path,data):
        pr=subprocess.run(['ffmpeg','-v','error','-y','-f','f32le','-ar','48000','-ac','2','-i','-',
                           '-c:a','pcm_s24le',str(path)],input=np.asarray(data,dtype='<f4').tobytes(),capture_output=True)
        if pr.returncode:raise RuntimeError(pr.stderr.decode())
    wav(out/'voice-normalized.wav',voice)
    for i,t in enumerate(tracks):
        music=pcm(root/t['file'],['-ss',str(p['bgm'].get('start_seconds',0))])
        if len(music)<n:raise ValueError('Music too short; choose a longer cue, do not silently loop')
        music=music[:n];raw=out/f'{i:02d}-trim.wav';wav(raw,music);level=measure(raw)
        # Music is -36 LUFS before another 4 dB attenuation during narration.
        db=p['bgm'].get('bed_lufs',-36)-float(level['input_i']);music*=10**(db/20)
        fade=np.minimum(np.arange(n)/(48000*p['bgm'].get('fade_in_seconds',2.2)),1)
        fade*=np.minimum(np.arange(n)[::-1]/(48000*p['bgm'].get('fade_out_seconds',3)),1)
        music*= (fade*envelope)[:,None]
        stem=out/f'{i:02d}-{t["id"]}-music.wav';wav(stem,music)
        ratios=[]
        for j in range(blocks):
            if active[j]:
                v=voice[j*hop:(j+1)*hop];m=music[j*hop:(j+1)*hop]
                ratios.append(20*math.log10((np.sqrt(np.mean(v*v))+1e-9)/(np.sqrt(np.mean(m*m))+1e-9)))
        # Limit unusually strong cues relative to the speech-active aggregate.
        mask=np.repeat(active,hop)[:n]
        diff=20*math.log10(np.sqrt(np.mean(voice[mask]**2))/max(np.sqrt(np.mean(music[mask]**2)),1e-9))
        correction=min(0,diff-20)
        if correction<0:
            music*=10**(correction/20);db+=correction;ratios=[x-correction for x in ratios];wav(stem,music)
        if np.max(np.abs(voice+music))>=1:raise ValueError('Mix would clip before normalization; lower input gain')
        mix=out/f'{i:02d}-mix-raw.wav';wav(mix,voice+music)
        final=out/f'{i:02d}-mix.wav';metrics=normalize(mix,final)
        results.append({'role':'default' if i==0 else f'alternative-{i:02d}',**t,'mix_file':str(final.relative_to(run)),
                        'music_stem':str(stem.relative_to(run)),'gain_db':round(db,2),'music_before_duck_lufs':p['bgm'].get('bed_lufs',-36),
                        'speech_active_rms_separation_db':round(max(20,diff),2),
                        'short_window_separation_p10_db':round(float(np.percentile(ratios,10)),2),
                        'mixed_wav_loudness':metrics,'subjective_listening':'pending_user_acceptance; no playback'})
    write(out/'mix-report.json',{'voice_source_sha256':sha(run/'narration.wav'),'duration':duration,
                               'processing':'voice -18 LUFS, each music cue calibrated, slow 4 dB duck, head/tail fades, final two-pass normalization',
                               'tracks':results})
    return results


def finish_film(p,brand,episode,run,root,base_video):
    from PIL import Image
    from caption_motion import write_overlay
    plan=json.loads((episode/p['visual_plan']['file']).read_text());timeline=json.loads((run/'timeline.json').read_text())
    w,h,fps=p['width'],p['height'],p['fps'];frames=round(timeline['duration']*fps);duration=frames/fps
    out=run/'render';layers,resolved=render_caption_layers(p,plan,timeline,brand,out)
    overlay=out/'composition-captions.mov'
    proc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgba','-s',f'{w}x{h}','-r',str(fps),'-i','-',
                           '-an','-c:v','qtrle',str(overlay)],stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:write_overlay(proc,layers,Image.new('RGBA',(w,h)),resolved,frames,fps,dict(p['caption_motion'],bridge_gap=0))
    finally:proc.stdin.close()
    err=proc.stderr.read().decode();proc.stderr.close()
    if proc.wait():raise RuntimeError(err)
    visual=out/'finished-visual.mp4'
    run_command(['ffmpeg','-v','error','-y','-i',base_video,'-i',overlay,'-filter_complex',
                 '[0:v][1:v]overlay=0:0:shortest=1[composite];' + opening_graph(p, 'composite', 'opened')
                 + f';[opened]fade=t=out:st={duration-.6}:d=0.6[v]',
                 '-map','[v]','-an','-c:v','libx264','-preset','fast','-crf','19','-threads','4','-pix_fmt','yuv420p','-t',duration,visual])
    if audio_mode(p) == 'narration_only':
        mux_narration_only(visual, run/'narration.wav', run/'film.mp4', duration, p['title'])
        write(out/'layout-inputs.json', {'signature': caption_signature(p, episode, run, root), 'status': 'rendered_pending_offline_layout_review'})
        return duration
    tracks=mix_music(root,run,p,duration)
    for i,t in enumerate(tracks):
        dest=run/('film.mp4' if i==0 else f'film-bgm-alt-{i:02d}.mp4')
        run_command(['ffmpeg','-v','error','-y','-i',visual,'-i',run/t['mix_file'],'-map','0:v','-map','1:a',
                     '-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000','-t',duration,'-movflags','+faststart',
                     '-metadata','title='+p['title'],'-metadata','comment='+t['attribution_text']+' '+t['modification_disclosure'],dest])
    write(out/'layout-inputs.json',{'signature':caption_signature(p,episode,run,root),'status':'rendered_pending_offline_layout_review'})
    (run/'MUSIC-CREDITS.txt').write_text('\n\n'.join(t['role']+'\n'+t['attribution_text']+'\n'+t['license_url']+'\n'+t['modification_disclosure'] for t in tracks)+'\n\n发布时请将所选曲目的署名与许可链接放入发布文案；文件元数据不能代替发布文案。\n')
    return duration


def release_gate(p,episode,run,root):
    if not modern(p):return
    review=json.loads((episode/p['caption_layout']['review_file']).read_text())
    if (review.get('signature')!=caption_signature(p,episode,run,root) or review.get('status')!='passed'
            or review.get('blocking_issues')!=[] or not review.get('reviewer') or not review.get('observations')):
        raise ValueError('Final caption layout review missing/stale')
    response=(episode/review['agent_response_file']).resolve()
    if not response.is_relative_to(episode.resolve()) or sha(response)!=review.get('agent_response_sha256'):
        raise ValueError('Actual independent layout response missing/changed')
    if sha(run/'offline-qa/report.json')!=review.get('offline_report_sha256'):raise ValueError('Actual reviewed offline report changed')
    report=json.loads((run/'offline-qa/report.json').read_text())
    if {m['file'] for m in report['movies']}!=set(movie_names(p)):raise ValueError('Incomplete final movie evidence for audio mode')
    if audio_mode(p) == 'narration_only':
        audio_report = run/'audio-output/report.json'
        if report.get('audio_output_mode') != 'narration_only' or report.get('audio_report_sha256') != sha(audio_report):
            raise ValueError('Narration-only audio evidence missing/changed')
        validate_narration_report(run)
    for name,expected in report['evidence_sha256'].items():
        if sha(run/'offline-qa'/name)!=expected:raise ValueError('Actual reviewed frame evidence changed')
    if report['signature']!=review['signature']:raise ValueError('Offline report is stale')
    for movie in report['movies']:
        if sha(run/movie['file'])!=movie['sha256']:raise ValueError('Final film changed after offline review')


def movie_names(p):
    if audio_mode(p) == 'narration_only':
        return ['film.mp4']
    count=1 if p.get('bgm',{}).get('enabled') is False else 1+len(p.get('bgm',{}).get('alternatives',[]))
    return ['film.mp4']+[f'film-bgm-alt-{i:02d}.mp4' for i in range(1,count)]


def validate_narration_report(run):
    report = json.loads((run/'audio-output/report.json').read_text())
    if (report.get('mode') != 'narration_only' or report.get('music_stage') != 'skipped' or report.get('music_tracks') != []
            or report.get('narration_source_sha256') != sha(run/'narration.wav')
            or report.get('output_sha256') != sha(run/'film.mp4')):
        raise ValueError('Narration-only source/output evidence differs')
