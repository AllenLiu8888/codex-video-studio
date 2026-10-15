"""Import measured local audio, either timed words or one WAV per editorial caption."""
from pathlib import Path
import json, wave, shutil, subprocess
import numpy as np
from audio_direction import load_direction
from tts_minimax import align, normalized
from visual_plan import local
from portable import sha

def source_signature(speech, root, require_exists=False):
    """Bind local audio sources by project-relative path and current bytes.

    Planning may refer to not-yet-delivered files, represented explicitly as
    null. Importing audio requires all referenced sources to exist. Only the
    active import mode is hashed: WAV+timestamps or per-caption clips.
    """
    root = Path(root).resolve()
    if speech.get('wav') or speech.get('timestamps'):
        names = [speech[k] for k in ['wav', 'timestamps'] if speech.get(k)]
    else:
        names = [clip['file'] for clip in speech.get('clips', [])]
    result = {}
    for name in names:
        path = local(root, name)
        key = path.relative_to(root).as_posix()
        if not path.is_file():
            if require_exists:
                raise ValueError('Local audio source is missing: ' + key)
            result[key] = None
        else:
            result[key] = sha(path)
    return dict(sorted(result.items()))


def pcm(source,dest):
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-ar','24000','-ac','1','-c:a','pcm_s16le',str(dest)],check=True)
    with wave.open(str(dest)) as f:return np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').copy()

def prepare(p,episode,run,root):
    _, direction = load_direction(p,episode)
    source_hashes = source_signature(p['speech'], root, require_exists=True)
    if not direction or direction['review'].get('local_audio_sha256') != source_hashes:
        raise ValueError('Local audio source review missing/stale; review the current audio and timestamp bytes')
    speech=p['speech']; sr=24000;before=p['intro_pause'];after=p['outro_pause']
    imported=run/'imported-audio';imported.mkdir(exist_ok=True)
    if speech.get('wav') and speech.get('timestamps'):
        source=local(root,speech['wav']);samples=pcm(source,imported/'source.wav')
        stamps=json.loads(local(root,speech['timestamps']).read_text())
        timeline=align(p['sentences'],stamps,len(samples)/sr,before,after)
        timeline['timing_method']='User-supplied word timestamps; exact text match; audio measured locally'
        voice=np.concatenate([np.zeros(round(before*sr),dtype='<i2'),samples,np.zeros(round(after*sr),dtype='<i2')])
        records=[{'file':speech['wav'],'sha256':sha(source),'timestamps_sha256':sha(local(root,speech['timestamps']))}]
    elif speech.get('clips'):
        expected=[c for s in p['sentences'] for c in s['captions']]
        clips=speech['clips']
        if len(clips)!=len(expected) or any(normalized(c.get('text',''))!=normalized(t) for c,t in zip(clips,expected)):
            raise ValueError('Local clips must match every caption exactly, in order')
        parts=[];rows=[];cursor=0;records=[]
        # Each whole caption is a measured utterance; no guessed whole-narration character timing.
        for i,c in enumerate(clips):
            source=local(root,c['file']);samples=pcm(source,imported/f'{i:03d}.wav');n=len(samples)
            if not n:raise ValueError('Empty local narration clip')
            rows.append({'timestamped_words':[{'word':c['text'],'time_begin':cursor/sr*1000,'time_end':(cursor+n)/sr*1000}]})
            parts.append(samples);cursor+=n
            pause=float(c.get('pause_after',.25)) if i<len(clips)-1 else 0
            if not 0<=pause<=5:raise ValueError('Local clip pause outside 0..5 seconds')
            silence=np.zeros(round(pause*sr),dtype='<i2');parts.append(silence);cursor+=len(silence)
            records.append({'file':c['file'],'sha256':sha(source),'text':c['text'],'measured_seconds':n/sr})
        joined=np.concatenate(parts);timeline=align(p['sentences'],rows,len(joined)/sr,before,after)
        timeline['timing_method']='Measured local per-caption clips; no inferred narration timing'
        voice=np.concatenate([np.zeros(round(before*sr),dtype='<i2'),joined,np.zeros(round(after*sr),dtype='<i2')])
    else:raise ValueError('Local audio requires speech.wav + speech.timestamps or speech.clips matching all captions')
    if source_signature(speech, root, require_exists=True) != source_hashes:
        raise ValueError('Local audio source changed during import; no final audio was written')
    with wave.open(str(run/'narration.wav'),'wb') as f:
        f.setparams((1,2,sr,0,'NONE','not compressed'));f.writeframes(voice.astype('<i2').tobytes())
    timeline['fps']=p['fps'];(run/'timeline.json').write_text(json.dumps(timeline,ensure_ascii=False,indent=2))
    (run/'narration.txt').write_text((Path(episode)/'narration.txt').read_text())
    (run/'local-audio-record.json').write_text(json.dumps({'sources':records,'source_sha256':source_hashes,'audio_sha256':sha(run/'narration.wav'),'subjective_listening':'pending'},ensure_ascii=False,indent=2))
    return timeline
