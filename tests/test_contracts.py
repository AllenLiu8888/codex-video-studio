"""Synthetic test evidence, never production approval. No network or paid API calls."""
import sys,json,tempfile,copy,unittest,hashlib,wave
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'workflow'))
from initialize import create,write
from portable import sha,validate_scope
from run import validate,Workflow
from visual_plan import load_plan,design_signature
from audio_direction import validate_request_text,load_direction
from tts_minimax import align,synthesize
from finishing import validate_layout,resolve_captions,load_music
from local_audio import prepare,source_signature

class Contracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.ep=create(self.root,'test','Fixture','Models predict.\nPeople check.')
        self.p=json.loads((self.ep/'episode.json').read_text());self.plan=json.loads((self.ep/'visual-plan.json').read_text())
        for i,text in enumerate(['Models predict.','People check.'],1):
            aid=f'a{i}';self.p['assets'].append({'id':aid,'kind':'prepared_image','file':f'{self.ep.relative_to(self.root)}/assets/{aid}.png','record_file':f'{self.ep.relative_to(self.root)}/generation/{aid}.json'})
            self.p['sentences'].append({'text':text,'captions':[text],'asset':aid})
            task=f'prompts/s{i}.txt';(self.ep/task).write_text('SYNTHETIC FIXTURE diagram task')
            self.plan['shots'].append({'id':f's{i}','anchor':{'sentence':i,'caption':0},'asset_id':aid,'source_text':text,'segment_id':f'g{i}','meaning':'explanation','viewer_takeaway':'Fixture only','method':'annotated_static','source_type':'diagram','selection_reason':'Test','visual_description':'Fixture panel','task_file':task,'fallback':'Stop','complex_motion_segment':None,'caption_layout':{'box':[.08,.7,.84,.18],'theme':'light_text','align':'center','max_lines':2,'layout_group':f'g{i}','reason':'Fixture only','protected_regions':[]}})
        self.save()
    def save(self):write(self.ep/'episode.json',self.p);write(self.ep/'visual-plan.json',self.plan)
    def sign(self):
        response=self.ep/'reviews/visual-plan-agent.md';response.write_text('SIMULATED TEST FIXTURE ONLY')
        write(self.ep/'reviews/visual-plan-review.json',{'status':'passed','reviewer':'SIMULATED FIXTURE','plan_sha256':sha(self.ep/'visual-plan.json'),'design_sha256':design_signature(self.p,self.ep),'agent_response_file':'reviews/visual-plan-agent.md','agent_response_sha256':sha(response),'blocking_issues':[]})
    def test_init_is_unique_and_pending(self):
        other=create(self.root,'test','Fixture','Text');self.assertNotEqual(other,self.ep)
        self.assertEqual(json.loads((self.ep/'reviews/visual-plan-review.json').read_text())['status'],'pending')
    def test_caption_text_change_rejected(self):
        self.p['sentences'][0]['captions']=['Other words']
        with self.assertRaisesRegex(ValueError,'Caption does not match'):validate(self.p)
    def test_missing_shot_rejected(self):
        self.plan['shots'].pop();self.save()
        with self.assertRaisesRegex(ValueError,'cover every'):load_plan(self.p,self.ep,self.root,False)
    def test_pending_plan_rejected(self):
        with self.assertRaisesRegex(ValueError,'review missing'):load_plan(self.p,self.ep,self.root)
    def test_task_change_invalidates_review(self):
        self.sign();load_plan(self.p,self.ep,self.root)
        (self.ep/'prompts/s1.txt').write_text('Changed task')
        with self.assertRaisesRegex(ValueError,'stale'):load_plan(self.p,self.ep,self.root)
    def test_response_change_invalidates_review(self):
        self.sign();(self.ep/'reviews/visual-plan-agent.md').write_text('Changed')
        with self.assertRaisesRegex(ValueError,'response changed'):load_plan(self.p,self.ep,self.root)
    def test_claim_without_source_rejected(self):
        self.p['research']['claims']=[{'id':'x','source_ids':['missing']}]
        with self.assertRaisesRegex(ValueError,'valid research source'):validate(self.p)
    def test_script_lock_rejects_unlogged_change(self):
        (self.ep/'narration.txt').write_text('Changed')
        with self.assertRaisesRegex(ValueError,'Locked input changed'):validate_scope(self.p,self.ep,self.root)
    def test_scope_escape_rejected(self):
        self.p['assets'][0]['file']='../secret.png'
        with self.assertRaisesRegex(ValueError,'escapes'):validate_scope(self.p,self.ep,self.root)
    def test_copied_session_id_rejected(self):
        self.p['id']='other'
        with self.assertRaisesRegex(ValueError,'ID must match'):validate_scope(self.p,self.ep,self.root)
    def test_brand_profile_change_rejected(self):
        (self.ep/'brand.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'profile changed'):validate_scope(self.p,self.ep,self.root)
    def test_audio_direction_cannot_be_removed(self):
        self.p.pop('audio_direction')
        with self.assertRaisesRegex(ValueError,'requires audio-agent'):load_direction(self.p,self.ep)
    def test_narration_change_not_allowed_in_pause_tags(self):
        with self.assertRaises(ValueError):validate_request_text('Hello.','Goodbye.<#0.6#>')
        self.assertEqual(validate_request_text('One. Two.','One.<#0.6#> Two.'),1)
    def test_caption_region_conflict_rejected(self):
        l=self.plan['shots'][0]['caption_layout'];l['protected_regions']=[{'box':[.1,.7,.5,.1],'reason':'face'}]
        with self.assertRaisesRegex(ValueError,'collides'):validate_layout(l)
    def test_long_caption_crossing_unsafe_next_shot_rejected(self):
        self.plan['shots'][1]['caption_layout']['protected_regions']=[{'box':[.1,.7,.5,.1],'reason':'subject'}]
        t={'scenes':[{'start':0,'end':2,'asset':'a1'},{'start':2,'end':4,'asset':'a2'}],'captions':[{'start':1,'end':3,'text':'Text'}]}
        with self.assertRaises(ValueError):resolve_captions(self.plan,t,{})
    def test_voice_change_changes_run(self):
        with patch('run.ROOT',self.root):
            a=Workflow(self.ep/'episode.json');self.p['speech']['voice']='new';self.save();b=Workflow(self.ep/'episode.json')
        self.assertNotEqual(a.run,b.run)
    def test_one_music_track_allowed_and_hash_enforced(self):
        file=self.root/'music.wav';file.write_bytes(b'test fixture')
        t={'id':'a','file':'music.wav','sha256':sha(file),'license':'fixture','license_url':'fixture','detail_url':'fixture','attribution_text':'fixture','modification_disclosure':'fixture'}
        write(self.root/'music.json',{'tracks':[t]});c={'catalog_file':'music.json','default_track':'a','alternatives':[]}
        self.assertEqual(len(load_music(self.root,c)),1);file.write_bytes(b'changed')
        with self.assertRaises(ValueError):load_music(self.root,c)
    def test_music_can_be_disabled(self):self.assertEqual(load_music(self.root,{'enabled':False}),[])

    def test_replaced_local_wav_changes_run_fingerprint(self):
        wav=self.ep/'audio/input.wav';stamps=self.ep/'audio/words.json'
        wav.write_bytes(b'fixture audio version one');stamps.write_text('[]')
        self.p['speech']={'provider':'local','wav':str(wav.relative_to(self.root)),'timestamps':str(stamps.relative_to(self.root))};self.save()
        with patch('run.ROOT',self.root):
            first=Workflow(self.ep/'episode.json');wav.write_bytes(b'fixture audio version two');second=Workflow(self.ep/'episode.json')
        self.assertNotEqual(first.run,second.run)
        self.assertNotEqual(first.input_manifest['local_audio_sha256'],second.input_manifest['local_audio_sha256'])
    def test_replaced_timestamp_bytes_change_run_fingerprint(self):
        wav=self.ep/'audio/input.wav';stamps=self.ep/'audio/words.json'
        wav.write_bytes(b'fixture audio');stamps.write_text('[]')
        self.p['speech']={'provider':'local','wav':str(wav.relative_to(self.root)),'timestamps':str(stamps.relative_to(self.root))};self.save()
        with patch('run.ROOT',self.root):
            first=Workflow(self.ep/'episode.json');stamps.write_text('[{}]');second=Workflow(self.ep/'episode.json')
        self.assertNotEqual(first.run,second.run)
    def test_missing_local_file_is_explicit_during_planning(self):
        speech={'provider':'local','wav':'audio/not-yet.wav','timestamps':'audio/not-yet.json'}
        self.assertEqual(source_signature(speech,self.root),{'audio/not-yet.json':None,'audio/not-yet.wav':None})
        with self.assertRaisesRegex(ValueError,'source is missing'):source_signature(speech,self.root,True)
    def test_local_audio_cannot_escape_project(self):
        with self.assertRaisesRegex(ValueError,'escapes'):
            source_signature({'provider':'local','clips':[{'file':'../outside.wav'}]},self.root)

class SpeechTiming(unittest.TestCase):
    def setUp(self):
        self.sentences=[{'text':'Models predict.','captions':['Models','predict.'],'asset':'a'}]
        self.words=[{'timestamped_words':[{'word':'Models','time_begin':100,'time_end':700},{'word':'predict','time_begin':900,'time_end':1600}]}]
    def test_native_silence_and_intro_preserved(self):
        t=align(self.sentences,self.words,2,.4,1)
        self.assertEqual(t['captions'][0]['start'],.5);self.assertEqual(t['duration'],3.4)
    def test_missing_word_rejected(self):
        self.words[0]['timestamped_words'].pop()
        with self.assertRaisesRegex(ValueError,'exactly match'):align(self.sentences,self.words,2)
    def test_overlap_rejected(self):
        self.words[0]['timestamped_words'][1]['time_begin']=300
        with self.assertRaisesRegex(ValueError,'Invalid native'):align(self.sentences,self.words,2)
    def test_unknown_paid_result_never_retried(self):
        with tempfile.TemporaryDirectory() as temp:
            s={'model':'speech-2.8-hd','voice':'fixture','speed':1}
            with patch('tts_minimax.secret',return_value='SYNTHETIC_TEST_KEY'),patch('urllib.request.urlopen',side_effect=TimeoutError):
                with self.assertRaisesRegex(RuntimeError,'unknown'):synthesize('Fixture',s,temp)
            with patch('urllib.request.urlopen') as network:
                with self.assertRaisesRegex(RuntimeError,'unresolved'):synthesize('Fixture',s,temp)
                network.assert_not_called()

if __name__=='__main__':unittest.main()

class LocalAudioContract(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name).resolve()
        self.ep=create(self.root,'audio','Fixture','One. Two.')
        self.p=json.loads((self.ep/'episode.json').read_text());self.p['sentences']=[{'text':'One. Two.','captions':['One.','Two.'],'asset':'a'}]
        self.p['intro_pause']=.2;self.p['outro_pause']=.3
        self.p['speech']={'provider':'local','clips':[]}
        for i,text in enumerate(['One.','Two.']):
            f=self.ep/'audio'/f'{i}.wav'
            with wave.open(str(f),'wb') as w:w.setparams((1,2,24000,0,'NONE','not compressed'));w.writeframes(bytes(24000*2))
            self.p['speech']['clips'].append({'file':str(f.relative_to(self.root)),'text':text,'pause_after':.4})
        (self.ep/'audio/request-text.txt').write_text('One. Two.')
        (self.ep/'audio/agent-response.md').write_text('SIMULATED TEST FIXTURE ONLY')
        self.review={'status':'ready_for_synthesis','reviewer':{'mode':'subagent','task_id':'SYNTHETIC FIXTURE','response_file':'audio/agent-response.md','response_sha256':sha(self.ep/'audio/agent-response.md')},'narration_sha256':sha(self.ep/'narration.txt'),'request_text_sha256':sha(self.ep/'audio/request-text.txt'),'speech':self.p['speech'],'reasoning_summary':'Synthetic measurement test only','model_requirements':{'source_url':'local supplied fixture files'}}
        self.bind()
    def bind(self):
        self.review['local_audio_sha256']=source_signature(self.p['speech'],self.root,require_exists=True)
        write(self.ep/'audio/direction.json',self.review)
        self.p['audio_direction']['request_text_sha256']=sha(self.ep/'audio/request-text.txt');self.p['audio_direction']['review_sha256']=sha(self.ep/'audio/direction.json')
    def test_per_caption_clips_use_measured_duration(self):
        r=self.root/'run';r.mkdir();t=prepare(self.p,self.ep,r,self.root)
        self.assertAlmostEqual(t['duration'],2.9);self.assertAlmostEqual(t['captions'][1]['start'],1.6)
        with wave.open(str(r/'narration.wav')) as w:self.assertAlmostEqual(w.getnframes()/w.getframerate(),2.9)
    def test_changed_clip_text_rejected_before_conversion(self):
        self.p['speech']['clips'][0]['text']='Not approved';self.review['speech']=self.p['speech'];self.bind()
        r=self.root/'run';r.mkdir()
        with self.assertRaisesRegex(ValueError,'match every caption'):prepare(self.p,self.ep,r,self.root)
    def test_changed_raw_response_rejected(self):
        (self.ep/'audio/agent-response.md').write_text('Changed')
        with self.assertRaisesRegex(ValueError,'response missing or changed'):load_direction(self.p,self.ep)
    def test_changed_pause_rejected(self):
        (self.ep/'audio/request-text.txt').write_text('One.<#0.4#> Two.')
        with self.assertRaisesRegex(ValueError,'review stale'):load_direction(self.p,self.ep)
    def test_changed_voice_rejected(self):
        self.p['speech']['voice']='new';self.review['speech']=dict(self.review['speech']);self.review['speech'].pop('voice',None);self.bind()
        with self.assertRaisesRegex(ValueError,'different speech'):load_direction(self.p,self.ep)

    def test_changed_clip_bytes_invalidate_review_before_conversion(self):
        file=self.root/self.p['speech']['clips'][0]['file'];data=file.read_bytes();file.write_bytes(data[:-2]+b'\x01\x00')
        r=self.root/'run';r.mkdir()
        with patch('local_audio.pcm') as conversion:
            with self.assertRaisesRegex(ValueError,'review missing/stale'):prepare(self.p,self.ep,r,self.root)
            conversion.assert_not_called()
    def test_missing_local_hash_review_cannot_import(self):
        self.review.pop('local_audio_sha256');write(self.ep/'audio/direction.json',self.review)
        self.p['audio_direction']['review_sha256']=sha(self.ep/'audio/direction.json')
        r=self.root/'run';r.mkdir()
        with self.assertRaisesRegex(ValueError,'review missing/stale'):prepare(self.p,self.ep,r,self.root)
    def test_changed_timestamp_bytes_invalidate_review_before_conversion(self):
        wav=self.p['speech']['clips'][0]['file'];stamps=self.ep/'audio/words.json';stamps.write_text('[]')
        self.p['speech']={'provider':'local','wav':wav,'timestamps':str(stamps.relative_to(self.root))};self.review['speech']=self.p['speech'];self.bind()
        stamps.write_text('[{}]');r=self.root/'run';r.mkdir()
        with patch('local_audio.pcm') as conversion:
            with self.assertRaisesRegex(ValueError,'review missing/stale'):prepare(self.p,self.ep,r,self.root)
            conversion.assert_not_called()
