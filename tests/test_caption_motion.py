import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'workflow'))
import io
import unittest
from caption_motion import display_intervals, opacity_at, write_overlay

class CaptionMotionChecks(unittest.TestCase):
    def test_bridge_preserves_original_and_long_pause(self):
        captions=[{'start':0.,'end':1.},{'start':1.05,'end':2.},{'start':2.5,'end':3.}]
        shown=display_intervals(captions)
        self.assertEqual(captions[0]['end'],1.)
        self.assertEqual(shown[0]['end'],1.05)
        self.assertEqual(shown[1]['end'],2.)
        self.assertTrue(all(a['end']<=b['start'] for a,b in zip(shown,shown[1:])))

    def test_short_caption_remains_readable_and_fades(self):
        self.assertEqual(opacity_at(.3,0,.6),255)
        self.assertTrue(0<opacity_at(.04,0,.6)<opacity_at(.08,0,.6)<255)
        self.assertTrue(0<opacity_at(.56,0,.6)<opacity_at(.52,0,.6)<255)
        self.assertEqual(opacity_at(.6,0,.6),0)

    def test_empty_gap_keeps_scrim_and_correct_frame_count(self):
        from PIL import Image
        class Sink:
            stdin=io.BytesIO()
        sink=Sink();scrim=Image.new('RGBA',(2,2),(32,29,24,95))
        layer=Image.new('RGBA',(2,2),(0,0,0,0));layer.putpixel((0,0),(242,240,240,255))
        write_overlay(sink,[layer],scrim,[{'start':.4,'end':.9}],30,25,{})
        data=sink.stdin.getvalue();self.assertEqual(len(data),30*16)
        for f in [0,5,24,29]:self.assertEqual(data[f*16:(f+1)*16],scrim.tobytes())

if __name__=='__main__':unittest.main()
