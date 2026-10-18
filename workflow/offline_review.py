"""Headless final-film evidence. Never opens a player or claims listening passed."""
from pathlib import Path
import argparse
import json
import math
import subprocess

from portable import resolve_font
from finishing import sha,write,measure,caption_signature,run_command,movie_names,audio_mode,validate_narration_report


def inspect(episode,run,root):
    from PIL import Image,ImageDraw,ImageFont
    p=json.loads(episode.read_text());timeline=json.loads((run/'timeline.json').read_text())
    placements=json.loads((run/'render/caption-placement.json').read_text())
    out=run/'offline-qa';out.mkdir(exist_ok=True)
    fps=p['fps'];frames=round(timeline['duration']*fps);sample={}
    def add(t,label):
        n=max(0,min(frames-1,round(t*fps)));sample.setdefault(n,[]).append(label)
    for c in placements:
        a,b=c['start'],c['end'];d=min(.20,(b-a)/3)
        for t,k in [(a+d,'in'),((a+b)/2,'mid'),(b-d,'out')]:add(t,f'C{c["index"]+1:02d} {k} {c["text"]}')
    for i,s in enumerate(timeline['scenes']):
        add((s['start']+s['end'])/2,f'S{i+1:02d} middle')
        if i:
            for t in [s['start']-.20,s['start'],s['start']+.20]:add(t,f'cut {i:02d}')
    add(0,'start');add((frames-1)/fps,'end')
    ordered=sorted(sample);selection='+'.join(f'eq(n,{n})' for n in ordered)
    run_command(['ffmpeg','-v','error','-y','-i',run/'film.mp4','-vf',f'select={selection.replace(",",chr(92)+",")}',
                 '-fps_mode','vfr','-q:v','2',out/'frame-%03d.jpg'])
    mapping=[{'file':f'frame-{i+1:03d}.jpg','frame':n,'time':n/fps,'labels':sample[n]} for i,n in enumerate(ordered)]
    write(out/'samples.json',mapping)
    brand=json.loads((root/p['brand']).read_text())
    font=ImageFont.truetype(resolve_font(brand['subtitle'].get('font_file','auto'),root),16)
    sheets=[]
    for offset in range(0,len(mapping),16):
        sheet=Image.new('RGB',(864,1648),'#e5dfd2');d=ImageDraw.Draw(sheet)
        for j,item in enumerate(mapping[offset:offset+16]):
            im=Image.open(out/item['file']);im.thumbnail((216,384))
            x=(j%4)*216;y=(j//4)*412;sheet.paste(im,(x,y))
            d.text((x+3,y+385),f'{offset+j+1:03d} · {item["time"]:.2f}s',font=font,fill='#25251f')
        dest=out/f'contact-{offset//16+1:02d}.jpg';sheet.save(dest,quality=91);sheets.append(dest.name)
    movies=[];visual_hashes=[]
    for name in movie_names(p):
        path=run/name
        probe=json.loads(run_command(['ffprobe','-v','error','-show_streams','-show_format','-of','json',path]).stdout)
        v=next(s for s in probe['streams'] if s['codec_type']=='video')
        if [v['width'],v['height']]!=[p['width'],p['height']] or v['r_frame_rate']!=f'{fps}/1' or int(v['nb_frames'])!=frames:
            raise ValueError('Final dimensions/fps/frame count differ')
        run_command(['ffmpeg','-v','error','-xerror','-i',path,'-f','null','-'])
        loud=measure(path)
        if abs(float(loud['input_i'])+17)>1.0 or float(loud['input_tp'])>-1.4:
            raise ValueError('Final loudness/true peak outside delivery tolerance: '+name)
        video_hash=run_command(['ffmpeg','-v','error','-i',path,'-map','0:v:0','-c','copy','-f','hash','-hash','sha256','-']).stdout.strip()
        visual_hashes.append(video_hash)
        movies.append({'file':name,'sha256':sha(path),'duration':float(probe['format']['duration']),
                       'frames':int(v['nb_frames']),'full_decode':'passed','loudness':loud,'video_stream_sha256':video_hash})
    if len(set(visual_hashes))!=1:raise ValueError('Final variants do not share identical video stream')
    if audio_mode(p) == 'narration_only':
        validate_narration_report(run)
    report={'validation_mode':'offline_no_playback','signature':caption_signature(p,episode.parent,run,root),
            'audio_output_mode':audio_mode(p),'audio_report_sha256':sha(run/'audio-output/report.json') if audio_mode(p)=='narration_only' else None,
            'movies':movies,'samples':len(mapping),'contact_sheets':sheets,'captions':len(placements),
            'subjective_listening':'pending_user_acceptance','human_acceptance':'pending',
            'evidence_sha256':{f.name:sha(f) for f in out.iterdir() if f.name=='samples.json' or f.name.startswith(('frame-','contact-'))},
            'layout_review':'pending_independent_agent','notes':'Final rendered subtitles and dissolves sampled; no UI/player opened.'}
    write(out/'report.json',report)
    print(json.dumps({'report':str(out/'report.json'),'samples':len(mapping),'movies':[(x['file'],x['loudness']['input_i'],x['loudness']['input_tp']) for x in movies]},ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--episode',required=True,type=Path);ap.add_argument('--run',required=True,type=Path)
    a=ap.parse_args();inspect(a.episode.resolve(),a.run.resolve(),Path(__file__).resolve().parents[1])
