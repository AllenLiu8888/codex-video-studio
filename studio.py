#!/usr/bin/env python3
"""Portable, explicit CLI for an agent-directed brand-video workflow."""
from pathlib import Path
import argparse,os,sys,json,shutil,importlib.util
CODE_ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(CODE_ROOT/'workflow'))

def doctor():
    from portable import resolve_font
    checks={x:importlib.util.find_spec(x) is not None for x in ['PIL','numpy']}
    checks.update({x:shutil.which(x) for x in ['ffmpeg','ffprobe']})
    try:checks['font']=resolve_font()
    except ValueError as e:checks['font']=None;checks['font_error']=str(e)
    checks['python_supported']=sys.version_info>=(3,10)
    checks['platform_supported']=sys.platform!='win32'
    print(json.dumps(checks,indent=2))
    return 0 if all(checks[k] for k in ['PIL','numpy','ffmpeg','ffprobe','font','python_supported','platform_supported']) else 1

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--project',type=Path,default=CODE_ROOT)
    sub=ap.add_subparsers(dest='stage',required=True)
    sub.add_parser('doctor');i=sub.add_parser('init');i.add_argument('--slug',required=True);i.add_argument('--title',required=True);i.add_argument('--narration-file',required=True);i.add_argument('--source-file',type=Path)
    d=sub.add_parser('demo');d.add_argument('--output',type=Path,required=True)
    for stage in ['validate','design','reviewed','audio','search','fetch','timing','preview','render-ready','render','offline-review','verify','status','signature']:
        p=sub.add_parser(stage);p.add_argument('--episode',required=True,type=Path)
    a=ap.parse_args();a.project=a.project.resolve();os.environ['STUDIO_PROJECT_ROOT']=str(a.project)
    if a.stage=='doctor':return doctor()
    if a.stage=='init':
        from initialize import create
        narration=sys.stdin.read() if a.narration_file=='-' else Path(a.narration_file).read_text()
        print(create(a.project,a.slug,a.title,narration,a.source_file.read_text() if a.source_file else None));return 0
    if a.stage=='demo':
        if a.output.exists() and any(a.output.iterdir()):raise ValueError('Demo output must be absent or empty; existing work is never overwritten')
        os.environ['STUDIO_PROJECT_ROOT']=str(a.output.resolve())
        from demo import generate
        generate(a.output);return 0
    from run import Workflow
    from visual_plan import load_plan,write,measured_timing,preview,render_gate,design_signature,sha
    ep=a.episode.resolve();job=Workflow(ep);print('Run:',job.run,flush=True)
    if a.stage in {'validate','design','reviewed'}:
        load_plan(job.p,ep.parent,a.project,reviewed=a.stage=='reviewed');print('Contract valid; not artistic acceptance')
    elif a.stage=='signature':print(json.dumps({'plan_sha256':sha(ep.parent/job.p['visual_plan']['file']),'design_sha256':design_signature(job.p,ep.parent)},indent=2))
    elif a.stage=='timing':write(job.run/'timing-plan.json',measured_timing(job.p,ep.parent,job.run,a.project))
    elif a.stage=='preview':print(preview(job.p,ep.parent,job.run,a.project))
    elif a.stage=='render-ready':render_gate(job.p,ep.parent,job.run,a.project);print('Render gate passed')
    elif a.stage=='offline-review':
        from offline_review import inspect
        inspect(ep,job.run,a.project)
    elif a.stage=='status':print(json.dumps(job.state,indent=2))
    else:getattr(job,a.stage.replace('-','_'))()
    return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,KeyError,TypeError,OSError) as e:raise SystemExit('STUDIO ERROR: '+str(e))
