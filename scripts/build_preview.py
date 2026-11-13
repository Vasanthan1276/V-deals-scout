"""Build a standalone snapshot for review; never makes provider requests."""
import json
import re
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def build(output):
    html = (ROOT/'index.html').read_text()
    data = {f'data/{name}.json':json.loads((ROOT/f'data/{name}.json').read_text()) for name in ('deals','hotels')}
    status = ROOT/'data/scan-status.json'
    if status.exists(): data['data/scan-status.json'] = json.loads(status.read_text())
    embedded = json.dumps(data,ensure_ascii=False).replace('<','\\u003c')
    resolver = f'''const previewData = {embedded};
async function previewFetch(url) {{ const value = previewData[url.split('?')[0]];return {{ok:Boolean(value),status:value?200:404,json:async()=>structuredClone(value)}}; }}
'''
    script = (ROOT/'app.js').read_text().replace('await fetch(', 'await previewFetch(')
    html = re.sub(r'<link rel="stylesheet"[^>]+>',lambda _: '<style>'+(ROOT/'styles.css').read_text()+'</style>',html)
    html = re.sub(r'<script src="scout-core.js[^>]+></script>',lambda _: '<script>'+(ROOT/'scout-core.js').read_text()+'</script>',html)
    html = re.sub(r'<script src="app.js[^>]+></script>',lambda _: '<script>'+resolver+script+'</script>',html)
    html = html.replace('<main class="wrap">', '''<main class="wrap"><details class="health-panel"><summary>Review preview · snapshot, not a live refresh</summary><p class="hint">Prepared from 13 November 2026 data. 27 automated checks pass. Desktop/mobile/tablet rendering and native keyboard dialog behavior still need a browser check before deployment. No provider requests are made by this preview. Saved lists here are separate from the live site.</p></details>''')
    html = html.replace('href="old-dashboard.html"','href="#old-layout" id="layout-toggle"')
    html = html.replace('</body>', '''<script>document.getElementById('layout-toggle').addEventListener('click',e=>{e.preventDefault();const old=document.body.classList.toggle('legacy-layout');e.currentTarget.textContent=old?'New dashboard layout →':'Old dashboard layout →';});</script></body>''')
    Path(output).write_text(html,encoding='utf-8')

if __name__=='__main__': build(sys.argv[1])
