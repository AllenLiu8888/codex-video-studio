"""Minimal portable local review page. No autoplay and no acceptance claims."""
import json,html
from pathlib import Path
from finishing import movie_names

def create_page(folder):
    folder=Path(folder);p=json.loads((folder/'episode.json').read_text());e=html.escape
    films=''.join(f'<section><h2>{e(n)}</h2><video controls preload="metadata" src="{e(n)}"></video><a href="{e(n)}">Download</a></section>' for n in movie_names(p))
    text=''.join('<p>'+e(s['text'])+'</p>' for s in p['sentences'])
    (folder/'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+e(p['title'])+'</title><style>body{font:17px/1.6 system-ui;background:#f5f2e9;color:#17283b;margin:24px auto;max-width:1100px}main{display:flex;gap:24px;flex-wrap:wrap}section{max-width:340px}video{width:100%}a{display:block}article{max-width:700px}</style><h1>'+e(p['title'])+'</h1><p>Technical evidence is separate from editorial, visual and listening acceptance.</p><main>'+films+'</main><a href="narration.wav">Narration</a><a href="captions.srt">Captions</a><a href="MUSIC-CREDITS.txt">Music credits</a><article>'+text+'</article>')
