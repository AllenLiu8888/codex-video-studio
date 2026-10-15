"""Deterministic offline engineering fixture, never a production-review shortcut.

Produces a complete inspectable project; tone audio is not speech and generated
geometric cards are not AI artwork. All editorial acceptance records stay pending.
"""
from pathlib import Path
import json,math,wave,shutil
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from initialize import create,write
from portable import resolve_font,sha

def tone(path,seconds,frequency,modulation=True):
    sr=24000;t=np.arange(round(seconds*sr))/sr
    envelope=(.55+.45*np.sin(2*np.pi*.7*t)**2) if modulation else np.ones(len(t))
    fade=np.minimum(t/.08,1)*np.minimum((seconds-t)/.08,1)
    audio=(.15*np.sin(2*np.pi*frequency*t)*envelope*fade*32767).astype('<i2')
    with wave.open(str(path),'wb') as f:f.setparams((1,2,sr,0,'NONE','not compressed'));f.writeframes(audio.tobytes())

def generate(root):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    script='A model predicts patterns.\nEvidence checks the answer.\nKeep the question in view.'
    ep=create(root,'offline-demo','Unseen Lab — engineering fixture',script)
    brand=json.loads((ep/'brand.json').read_text());brand['name']='Unseen Lab';brand['subtitle']['size_ratio']=.044
    write(ep/'brand.json',brand);snap=json.loads((ep/'generation/brand-snapshot.json').read_text());snap['profile_sha256']=sha(ep/'brand.json');write(ep/'generation/brand-snapshot.json',snap)
    p=json.loads((ep/'episode.json').read_text());p.update(width=360,height=640,fps=25,speech={'provider':'local','fixture_only':True},technical_fixture=True)
    plan=json.loads((ep/'visual-plan.json').read_text());plan['distinctive_content']='Deterministic engineering smoke test: geometric cards and test tones, no speech.'
    assets=[];sources=[];captions=[];scenes=[]
    font=ImageFont.truetype(resolve_font(root=root),20);small=ImageFont.truetype(resolve_font(root=root),14)
    for i,text in enumerate(script.splitlines()):
        aid=f'card-{i+1:02d}';file=ep/'assets'/f'{aid}.png';prompt=ep/'prompts'/f'{aid}.txt'
        im=Image.new('RGB',(360,640),['#17283B','#F5F2E9','#213F52'][i]);d=ImageDraw.Draw(im)
        fg='#F5F2E9' if i!=1 else '#17283B';accent='#E5856B'
        # Subject moves between middle and lower frame; captions use two actual safe regions.
        y=400 if i==1 else 230
        for j in range(6):
            x=65+j*45;yy=y+round(math.sin(j+i)*35)
            d.ellipse((x-13,yy-13,x+13,yy+13),fill=accent,outline=fg,width=2)
            if j:d.line((x-45,y+round(math.sin(j-1+i)*35),x,yy),fill=fg,width=2)
        d.text((25,35),'UNSEEN LAB',font=font,fill=fg);d.text((25,75),'OFFLINE ENGINEERING FIXTURE',font=small,fill=fg)
        d.text((25,560),f'{i+1:02d} / Geometric test image',font=small,fill=fg);im.save(file)
        prompt.write_text('Programmatic geometric engineering card; no generative image service. Not a production asset.\n')
        record=ep/'generation'/f'{aid}.json';write(record,{'status':'technical_fixture_only','asset_sha256':sha(file),'provenance':{'source_or_creation_record':'workflow/demo.py deterministic drawing','license':'MIT project test fixture'},'reviewer':None,'observations':None,'human_acceptance':'pending'})
        asset={'id':aid,'kind':'prepared_image','file':str(file.relative_to(root)),'record_file':str(record.relative_to(root)),'motion':'gentle'};assets.append(asset)
        sentence={'text':text,'captions':[text],'asset':aid,'claims':[]};p['sentences'].append(sentence)
        start=i*3.6;end=(i+1)*3.6
        scenes.append({'index':i+1,'sentence':i+1,'asset':aid,'start':start,'end':end,'text':text,'kind':'fixture'})
        captions.append({'start':start+.35,'end':end-.35,'text':text,'sentence':i+1})
        box=[.08,.14,.84,.20] if i==1 else [.08,.66,.84,.20]
        protected=[{'box':[.1,(y-65)/640,.8,130/640],'reason':'Actual geometric card subject'}]
        plan['shots'].append({'id':f'shot-{i+1:02d}','segment_id':f'segment-{i+1}','anchor':{'sentence':i+1,'caption':0},'asset_id':aid,'source_text':text,'meaning':'explanation','viewer_takeaway':'Test the renderer, not the factual script','method':'annotated_static','source_type':'diagram','selection_reason':'Deterministic image for offline reproducibility','visual_description':'Geometric test image with known safe region','task_file':str(prompt.relative_to(ep)),'fallback':'Stop if engineering image is missing','complex_motion_segment':None,'caption_layout':{'box':box,'theme':'dark_text' if i==1 else 'light_text','align':'center','max_lines':2,'layout_group':f'fixture-{i}','reason':'Measured empty region outside the geometric subject','protected_regions':protected}})
    p['assets']=assets
    # Test music is original generated tone material; it is never marketed as a finished soundtrack.
    music=root/'fixture-music.wav';tone(music,15,110,False)
    write(root/'music.json',{'tracks':[{'id':'test-tone','file':music.name,'sha256':sha(music),'license':'MIT (programmatic test fixture)','license_url':'https://opensource.org/license/mit','detail_url':'workflow/demo.py','attribution_text':'Codex Video Studio original engineering test tone','modification_disclosure':'Trimmed, normalized and ducked for a technical test'}]})
    p['bgm']={'enabled':True,'catalog_file':'music.json','default_track':'test-tone','alternatives':[],'bed_lufs':-36,'fade_in_seconds':1,'fade_out_seconds':1}
    write(ep/'episode.json',p);write(ep/'visual-plan.json',plan)
    from run import Workflow
    job=Workflow(ep/'episode.json');(job.run/'assets').mkdir(exist_ok=True)
    for asset in assets:
        f=root/asset['file'];target=job.run/'assets'/f.name;shutil.copy2(f,target)
        sources.append(dict(asset,local_file=str(target.relative_to(job.run)),sha256=sha(f),dimensions=[360,640],record_sha256=sha(root/asset['record_file'])))
    write(job.run/'sources.json',sources)
    tone(job.run/'narration.wav',10.8,260);(job.run/'narration.txt').write_text('TEST TONES ONLY — no spoken narration.\n'+script)
    write(job.run/'timeline.json',{'duration':10.8,'fps':25,'scenes':scenes,'captions':captions,'timing_method':'Deterministic synthetic fixture, no actual speech alignment claim'})
    write(job.run/'demo-status.json',{'status':'technical_fixture_only','paid_api_calls':0,'production_reviews':'pending','narration':'synthetic test tone; not speech','images':'programmatic test cards; not AI output'})
    job._render_verified_inputs()
    from offline_review import inspect
    inspect(ep/'episode.json',job.run,root)
    job._verify_technical()
    # Override nothing in production records; label technical fixture distinctly.
    write(root/'DEMO-RESULT.json',{'film':str((job.run/'film.mp4').relative_to(root)),'episode':str((ep/'episode.json').relative_to(root)),'qa':str((job.run/'qa/validation.json').relative_to(root)),'production_ready':False,'human_acceptance':'pending','notes':'Technical fixture only. Tones are not narration; cards are not AI artwork. Production commands still require genuine review evidence.'})
    print('OFFLINE DEMO:',root/'DEMO-RESULT.json')
