"""Readable text fades over a stable scrim, with no overlapping sentences."""

def display_intervals(captions, bridge_gap=.18):
    intervals = [dict(c) for c in captions]
    for left, right in zip(intervals, intervals[1:]):
        if 0 <= right['start']-left['end'] <= bridge_gap:
            left['end'] = right['start']
    return intervals


def opacity_at(t, start, end, fade_in=.12, fade_out=.16):
    if not start <= t < end:
        return 0
    length = end-start
    # Short captions retain at least 60% of their interval at full opacity.
    incoming = min(fade_in, length*.2)
    outgoing = min(fade_out, length*.2)
    x = min(1., (t-start)/incoming if incoming > 0 else 1.,
            (end-t)/outgoing if outgoing > 0 else 1.)
    return round(255*x*x*(3-2*x))


def write_overlay(proc, layers, backdrop, captions, frames, fps, settings):
    import numpy as np
    from PIL import Image
    intervals = display_intervals(captions, settings.get('bridge_gap', .18))
    base = backdrop.tobytes()
    ci = 0
    cache = {}
    for frame in range(frames):
        t = frame/fps
        while ci < len(intervals) and intervals[ci]['end'] <= t:
            ci += 1
            cache = {}
        if ci >= len(intervals):
            proc.stdin.write(base)
            continue
        c = intervals[ci]
        opacity = opacity_at(t, c['start'], c['end'], settings.get('fade_in', .12), settings.get('fade_out', .16))
        if not opacity:
            proc.stdin.write(base)
            continue
        if opacity not in cache:
            layer = np.asarray(layers[ci]).copy()
            layer[:,:,3] = (layer[:,:,3].astype(np.uint16)*opacity//255).astype(np.uint8)
            cache[opacity] = Image.alpha_composite(backdrop, Image.fromarray(layer)).tobytes()
        proc.stdin.write(cache[opacity])
    return intervals
