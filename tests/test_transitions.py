import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'workflow'))
"""Verify real encoded dissolves preserve timing and blend both source images."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from transitions import transition_layout, join_dissolves, execute

class DissolveChecks(unittest.TestCase):
    def test_timeline_is_not_shortened(self):
        plan=transition_layout([0,75,175,250],6)
        bodies=sum(p['body_end']-p['body_start'] for p in plan)
        self.assertEqual(bodies+12*(len(plan)-1),250)
        self.assertEqual(plan[0]['pre'],0)
        self.assertEqual(plan[-1]['post'],0)
        with self.assertRaises(ValueError):transition_layout([0,10,20,30],6)

    def test_encoded_blend_and_frame_count(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d); plan=transition_layout([0,50,100,150],6)
            clips=[]
            for i,(color,p) in enumerate(zip(['red','blue','green'],plan)):
                clip=folder/f'{i}.mp4';clips.append(clip)
                execute(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color={color}:s=160x240:r=25',
                         '-frames:v',p['render_frames'],'-c:v','libx264','-pix_fmt','yuv420p',clip])
            output=join_dissolves(clips,plan,25,6,folder)
            data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(output)]))
            self.assertEqual(int(data['streams'][0]['nb_frames']),150)
            self.assertAlmostEqual(float(data['streams'][0]['duration']),6,places=3)
            pixel=subprocess.check_output(['ffmpeg','-v','error','-ss','2','-i',str(output),'-frames:v','1',
                                           '-vf','scale=1:1','-f','rawvideo','-pix_fmt','rgb24','-'])
            red,green,blue=pixel
            self.assertGreater(red,70)
            self.assertGreater(blue,70)
            self.assertLess(green,25)
            events=json.loads((folder/'transitions.json').read_text())['events']
            self.assertEqual(len(events),2)
            self.assertEqual(events[0]['center'],2)

if __name__=='__main__':unittest.main()
