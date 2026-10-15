"""Allocate an isolated episode and freeze the actual starting material."""
from pathlib import Path
from datetime import datetime
import json,shutil,re,fcntl
from portable import CODE_ROOT,sha

def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')

def create(root,slug,title,narration,source=None):
    root=Path(root).resolve()
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*',slug) or len(slug)>40:raise ValueError('Slug must be kebab-case, maximum 40 characters')
    if not title.strip() or not narration.strip():raise ValueError('Title and narration are required')
    root.mkdir(parents=True,exist_ok=True);(root/'brand').mkdir(exist_ok=True)
    profile=root/'brand/profile.json'
    if not profile.exists():write(profile,{'name':'Your Brand','palette':{'dark':'#17283B','light':'#F5F2E9','accent':'#E5856B'},'subtitle':{'font_file':'auto','size_ratio':.044},'status':'draft_needs_brand_design'})
    defaults=root/'brand/production-defaults.json'
    if not defaults.exists():write(defaults,{'width':1080,'height':1920,'fps':25,'intro_pause':.4,'outro_pause':1.2,'speech':{'provider':'local'},'transition':{'type':'cross-dissolve','seconds':.48},'caption_motion':{'type':'fade','fade_in':.12,'fade_out':.16,'bridge_gap':.18},'bgm':{'enabled':False},'no_repeated_images':True})
    active=root/'brand/active-ip.json'
    if not active.exists():write(active,{'status':'optional_not_configured','references':[]})
    identity=json.loads(active.read_text());references=identity.get('references',[])
    for item in references:
        p=(root/item['file']).resolve()
        if not p.is_relative_to(root) or not p.is_file() or sha(p)!=item['sha256']:raise ValueError('Invalid brand reference file/hash: '+item['file'])
        if not item.get('role'):raise ValueError('Brand reference must say its role')
    episodes=root/'episodes';episodes.mkdir(exist_ok=True)
    with (episodes/'.allocate.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        nums=[int(m[1]) for p in episodes.iterdir() if (m:=re.fullmatch(r'ep-(\d+)-.*',p.name))]
        eid=f'ep-{max(nums,default=0)+1:04d}-{slug}';ep=episodes/eid;ep.mkdir()
    for d in ['source','prompts','assets','generation','reviews','audio']:(ep/d).mkdir()
    (ep/'narration.txt').write_text(narration)
    (ep/'source/original.txt').write_text(source if source is not None else narration)
    write(ep/'source/locked-inputs.json',{'files':{'narration.txt':sha(ep/'narration.txt'),'source/original.txt':sha(ep/'source/original.txt')}})
    shutil.copy2(profile,ep/'brand.json');shutil.copy2(defaults,ep/'generation/production-defaults.json')
    write(ep/'generation/brand-snapshot.json',{'profile_sha256':sha(ep/'brand.json'),'active_ip':identity,'references':references,'created_at':datetime.now().astimezone().isoformat()})
    for name in ['version.json','visual-methods.json']:
        shutil.copy2(CODE_ROOT/'workflow'/name,ep/'generation'/('workflow-version.json' if name=='version.json' else name))
    write(ep/'generation/seed-snapshot.json',{'rule_files':{'workflow/version.json':sha(ep/'generation/workflow-version.json'),'workflow/visual-methods.json':sha(ep/'generation/visual-methods.json')}})
    settings=json.loads(defaults.read_text());p=dict(settings,id=eid,title=title,workflow_version='2.1.0',brand=str((ep/'brand.json').relative_to(root)),series_label='',research={'sources':[],'claims':[]},assets=[],sentences=[],visual_plan={'file':'visual-plan.json','review_file':'reviews/visual-plan-review.json'},audio_direction={'request_text_file':'audio/request-text.txt','review_file':'audio/direction.json','request_text_sha256':None,'review_sha256':None},caption_layout={'review_file':'reviews/caption-layout-review.json'})
    write(ep/'episode.json',p)
    write(ep/'visual-plan.json',{'schema_version':1,'workflow_version':'2.1.0','episode_id':eid,'narration_sha256':sha(ep/'narration.txt'),'distinctive_content':None,'shots':[]})
    write(ep/'reviews/visual-plan-review.json',{'status':'pending','plan_sha256':None,'design_sha256':None,'reviewer':None,'agent_response_file':'reviews/visual-plan-agent.md','agent_response_sha256':None,'blocking_issues':None})
    write(ep/'audio/direction.json',{'schema_version':1,'status':'pending_audio_agent','reviewer':None,'narration_sha256':sha(ep/'narration.txt'),'request_text_sha256':None,'speech':p['speech'],'model_requirements':None,'reasoning_summary':None})
    write(ep/'reviews/caption-layout-review.json',{'status':'pending','reviewer':None,'observations':None,'blocking_issues':None})
    (ep/'BRIEF.md').write_text('# '+title+'\n\nState: initialized; script locked; storyboard, audio, images and film pending.\n\nUse only this episode directory and its run. Record user constraints, sources, edits, QA and acceptance separately.\n')
    return ep
