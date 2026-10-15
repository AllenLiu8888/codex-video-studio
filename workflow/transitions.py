"""Frame-exact centered dissolves without shortening the speech timeline."""
from pathlib import Path
import concurrent.futures
import subprocess
import json


def transition_layout(boundaries, half_frames):
    if half_frames < 0:
        raise ValueError('Negative transition duration')
    result = []
    count = len(boundaries)-1
    for i in range(count):
        nominal = boundaries[i+1]-boundaries[i]
        pre = half_frames if i else 0
        post = half_frames if i < count-1 else 0
        if nominal <= pre+post:
            raise ValueError('Shot too short for selected transitions')
        result.append({'nominal_frames': nominal, 'pre': pre, 'post': post,
                       'render_frames': nominal+pre+post,
                       'body_start': 2*pre, 'body_end': nominal+pre-post})
    return result


def execute(args):
    process = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    if process.returncode:
        raise RuntimeError(process.stderr[-4000:])


def join_dissolves(clips, layout, fps, half_frames, folder):
    folder = Path(folder)
    encoding = ['-an','-c:v','libx264','-preset','fast','-crf','18','-threads','2','-pix_fmt','yuv420p','-r',fps]
    tasks = []
    ordered = []
    transitions = []
    duration = 2*half_frames/fps
    for i,(clip,plan) in enumerate(zip(clips,layout)):
        target=folder/f'body-{i:03d}.mp4'
        vf=f'trim=start_frame={plan["body_start"]}:end_frame={plan["body_end"]},setpts=PTS-STARTPTS,setsar=1'
        tasks.append(['ffmpeg','-v','error','-y','-i',clip,'-vf',vf,'-frames:v',plan['body_end']-plan['body_start'],*encoding,target])
        ordered.append(target)
        if i == len(clips)-1:
            continue
        target=folder/f'dissolve-{i:03d}.mp4'
        start=plan['render_frames']-2*half_frames
        graph=(f'[0:v]trim=start_frame={start},setpts=PTS-STARTPTS,settb=AVTB,format=yuv420p[a];'
               f'[1:v]trim=end_frame={2*half_frames},setpts=PTS-STARTPTS,settb=AVTB,format=yuv420p[b];'
               f'[a][b]xfade=transition=fade:duration={duration:.6f}:offset=0,'
               f'trim=end_frame={2*half_frames},setpts=PTS-STARTPTS,format=yuv420p[v]')
        tasks.append(['ffmpeg','-v','error','-y','-filter_complex_threads','1','-i',clip,'-i',clips[i+1],
                      '-filter_complex',graph,'-map','[v]','-frames:v',2*half_frames,*encoding,target])
        ordered.append(target)
        center=sum(x['nominal_frames'] for x in layout[:i+1])/fps
        transitions.append({'boundary':i+1,'start':center-half_frames/fps,'center':center,
                            'end':center+half_frames/fps,'type':'cross-dissolve'})
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(execute,tasks))
    listing=folder/'dissolve-concat.txt'
    listing.write_text(''.join(f"file '{p.name}'\n" for p in ordered))
    target=folder/'pictures.mp4'
    execute(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',listing,'-c','copy',target])
    (folder/'transitions.json').write_text(json.dumps({'half_frames':half_frames,'fps':fps,
        'output_frames':sum(x['nominal_frames'] for x in layout),'events':transitions},indent=2))
    return target
