"""Import reviewed local images/clips; normalize video without inventing motion."""
import json
from pathlib import Path
import subprocess
import math


def probe(path):
    result = subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,check=True)
    data=json.loads(result.stdout)
    video=next((x for x in data['streams'] if x['codec_type']=='video'),None)
    if video is None:raise ValueError('Asset has no video stream')
    return {'width':video['width'],'height':video['height'],
            'seconds':float(video.get('duration',data['format'].get('duration',0))),
            'audio_present':any(x['codec_type']=='audio' for x in data['streams'])}


def validate_local(asset, root, filehash):
    from visual_plan import local
    source=local(root,asset['file']); record_path=local(root,asset['record_file'])
    record=json.loads(record_path.read_text())
    if record.get('asset_sha256') != filehash(source) or record.get('status') != 'assistant_visual_pass':
        raise ValueError('Local media record missing/stale: '+asset['id'])
    if not record.get('provenance') or not record.get('reviewer') or not record.get('observations'):
        raise ValueError('Local media needs actual provenance and visual review')
    if asset['kind']=='video':
        info=probe(source)
        if asset.get('audio_policy')!='discard':raise ValueError('Clip audio must be explicitly discarded; final narration is mixed once')
        start=asset.get('in_seconds',0);end=asset.get('out_seconds',info['seconds'])
        if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in [start,end]) or not 0<=start<end<=info['seconds']+.02:
            raise ValueError('Invalid video source interval')
        if asset.get('fit') not in {'contain','cover'}:raise ValueError('Video fit must be explicit')
        if asset['fit']=='cover':
            if not all(0<=asset.get(k,-1)<=1 for k in ['crop_x','crop_y']):raise ValueError('Cover crop needs reviewed normalized x/y')
        return [info['width'],info['height']],info
    from PIL import Image
    with Image.open(source) as im:im.verify()
    with Image.open(source) as im:return list(im.size),None


def render_video(asset, source, dest, width, height, fps, frames):
    info=probe(source);start=asset.get('in_seconds',0);end=asset.get('out_seconds',info['seconds'])
    if end>info['seconds']+.02 or end<=start:raise ValueError('Invalid video trim')
    available=end-start; needed=frames/fps
    hold=asset.get('end_hold_seconds',0)
    if hold<0 or hold>0 and not asset.get('hold_reason'):raise ValueError('End hold must be explicit with a reason')
    if available+hold+1e-6<needed:
        raise ValueError('Video too short including transition handles; supply a longer clip or explicit end hold')
    if asset['fit']=='cover':
        fit=f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}:(iw-ow)*{asset['crop_x']}:(ih-oh)*{asset['crop_y']}"
    else:
        fit=f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x17283B'
    vf=f'trim=start={start}:end={end},setpts=PTS-STARTPTS,{fit},fps={fps},setsar=1,format=yuv420p'
    if hold:vf+=f',tpad=stop_mode=clone:stop_duration={hold}'
    args=['ffmpeg','-v','error','-y','-i',str(source),'-vf',vf,'-frames:v',str(frames),'-an','-c:v','libx264','-preset','fast','-crf','20','-threads','2',str(dest)]
    result=subprocess.run(args,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(result.stderr[-2000:])
    return dest


def visual_identity(asset, source, source_hash, frames, fps):
    """Repeated source clips may show different intervals; crops cannot hide repeats."""
    if asset['kind']!='video':return source_hash
    start=asset.get('in_seconds',0)
    end=asset.get('out_seconds')
    if end is None:end=probe(source)['seconds']
    shown_end=min(end,start+frames/fps)
    return (source_hash,round(start,6),round(shown_end,6),
            round(max(0,frames/fps-(shown_end-start)),6))
