"""Live map page and self-contained, scoped HTML exports."""

from html import escape
from map_details import render_details


MAP_CSS = """.ed-system-map *{box-sizing:border-box}
.ed-system-map{color-scheme:dark;margin:0;background:#0b0d10;background-image:radial-gradient(ellipse at top right,#39231055,transparent 55%);color:#e9e5df;font:15px/1.6 system-ui,sans-serif}
.ed-system-map main{max-width:1600px;margin:auto;padding:36px 40px}
.ed-system-map header{border-bottom:1px solid #e9923638;padding-bottom:24px}
.ed-system-map .eyebrow{color:#ffad52;text-transform:uppercase;letter-spacing:.2em;font:12px/1.5 Consolas,monospace}
.ed-system-map h1{font-size:clamp(28px,4vw,48px);line-height:1.2;margin:10px 0;overflow-wrap:anywhere}
.ed-system-map .meta,.ed-system-map footer{color:#a8a49f;font-size:13px}
.ed-system-map .meta{display:flex;gap:24px;flex-wrap:wrap}
.ed-system-map footer{border-top:1px solid #e9923638;margin-top:32px;padding-top:18px}
.ed-system-map pre{font:clamp(14px,1.3vw,19px)/1.9 Consolas,monospace;overflow:auto;padding:24px;background:#111b2a;border:1px solid #28384f;border-radius:12px;min-height:220px}
.ed-system-map nav{display:flex;align-items:center;flex-wrap:wrap;gap:20px;margin-top:24px}
.ed-system-map a{color:#ffb454}
.ed-system-map form{display:flex;align-items:center;flex-wrap:wrap;gap:10px}
.ed-system-map input,.ed-system-map button{font:inherit;padding:7px 12px;border:1px solid #61503e;border-radius:6px;background:#201b16;color:inherit}
.ed-system-map button{cursor:pointer;color:#ffb454}
.ed-system-map input{max-width:100%;width:230px}
.ed-system-map .stats{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin:24px 0 16px}
.ed-system-map .stats>div{background:#171716;border:1px solid #383026;border-radius:10px;padding:16px 20px}
.ed-system-map .stats strong{display:block;font:30px/1.3 Consolas,monospace;color:#ffb454}
.ed-system-map .stats span{font-size:12px;color:#bdb1a2}
.ed-system-map .scan-status{color:#cfbb9e;font-size:13px}
.ed-system-map .live-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#ffad52;margin-right:10px;box-shadow:0 0 10px #ffad5244}
.ed-system-map .overview{display:flex;flex-wrap:wrap;gap:14px 36px;margin:20px 0}
.ed-system-map .overview dt{font-size:11px;text-transform:uppercase;color:#9b938a;letter-spacing:.08em}
.ed-system-map .overview dd{margin:2px 0;font-size:14px}
.ed-system-map .section-heading{display:flex;align-items:baseline;justify-content:space-between;gap:16px;flex-wrap:wrap;margin:30px 0 14px}
.ed-system-map .section-heading h2{font-size:15px;letter-spacing:.12em;text-transform:uppercase;margin:0;color:#ffb454}
.ed-system-map .section-heading>span{color:#96918b;font-size:12px}
.ed-system-map .tree,.ed-system-map .tree ul{list-style:none;padding:0;margin:0}
.ed-system-map .tree ul{margin:10px 0 12px 19px;padding-left:25px;border-left:1px solid #73502e}
.ed-system-map .tree li{position:relative;margin:10px 0}
.ed-system-map .tree ul>li:before{content:'';position:absolute;left:-25px;top:32px;width:25px;border-top:1px solid #73502e}
.ed-system-map .body-card{--accent:#c5ac91;background:linear-gradient(110deg,#1c1a17,#131518);border:1px solid #35312c;border-left:3px solid var(--accent);border-radius:8px;padding:16px 20px;min-width:0;box-shadow:0 4px 15px #0002}
.ed-system-map .star{--accent:#ffc477}
.ed-system-map .ice{--accent:#9ed7ed}
.ed-system-map .water{--accent:#66c5d4}
.ed-system-map .gas{--accent:#c7a2e6}
.ed-system-map .ammonia{--accent:#b5cd7a}
.ed-system-map .rock{--accent:#c5a17c}
.ed-system-map .ring{--accent:#ddbd68}
.ed-system-map .barycentre{--accent:#a2a6ad}
.ed-system-map .earthlike{--accent:#70d98b}
.ed-system-map .body-card.earthlike{background:linear-gradient(110deg,#182c20,#111b16);border-color:#365d42;border-left-color:var(--accent)}
.ed-system-map .earthlike>.body-heading h3{color:#b9f0c7}
.ed-system-map .body-heading{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.ed-system-map .body-heading h3{margin:0;font-size:17px;color:#f6e5ce;overflow-wrap:anywhere}
.ed-system-map .body-id{margin-left:auto;color:#a69d93;font:11px/1.5 Consolas,monospace}
.ed-system-map .orb{flex:0 0 20px;height:20px;border-radius:50%;background:radial-gradient(circle at 30% 25%,#fff9,var(--accent) 40%,#0009);box-shadow:0 0 14px #0004}
.ed-system-map .star>.body-heading>.orb{box-shadow:0 0 16px #ffc47755}
.ed-system-map .barycentre>.body-heading>.orb{background:none;border:1px dashed var(--accent)}
.ed-system-map .spectral-o{--accent:#91aaff}
.ed-system-map .spectral-b{--accent:#b5caff}
.ed-system-map .spectral-a{--accent:#e4eaff}
.ed-system-map .spectral-f{--accent:#fff3cf}
.ed-system-map .spectral-g{--accent:#ffe28a}
.ed-system-map .spectral-k{--accent:#ffb45d}
.ed-system-map .spectral-m{--accent:#ff714a}
.ed-system-map .spectral-l{--accent:#cd5035}
.ed-system-map .spectral-t{--accent:#a94760}
.ed-system-map .spectral-y{--accent:#885269}
.ed-system-map .carbon-star{--accent:#ed6840}
.ed-system-map .white-dwarf{--accent:#d5e9ff}
.ed-system-map .neutron{--accent:#92dfff}
.ed-system-map .black-hole{--accent:#c6bbef}
.ed-system-map .unknown-star{--accent:#c4c8ce}
.ed-system-map .stellar>.body-heading>.orb{position:relative;flex-basis:24px;height:24px;margin:2px;background:radial-gradient(circle,#fff 0%,var(--accent) 58%,var(--accent) 70%,transparent 73%);box-shadow:0 0 12px var(--accent);outline:1px solid var(--accent);outline-offset:3px}
.ed-system-map .stellar.white-dwarf>.body-heading>.orb,.ed-system-map .stellar.neutron>.body-heading>.orb{background:radial-gradient(circle,#fff 0 20%,var(--accent) 30%,#111 42%,transparent 65%)}
.ed-system-map .stellar.neutron>.body-heading>.orb:after{content:'';position:absolute;left:10px;top:-8px;width:3px;height:40px;background:linear-gradient(transparent,var(--accent),#fff,var(--accent),transparent);transform:rotate(35deg)}
.ed-system-map .stellar.black-hole>.body-heading>.orb{background:#050508;box-shadow:0 0 8px var(--accent),inset 0 0 3px var(--accent);outline-offset:1px}
.ed-system-map .stellar.black-hole>.body-heading>.orb:after{content:'';position:absolute;inset:7px -7px;border:2px solid var(--accent);border-radius:50%;transform:rotate(-25deg)}
.ed-system-map .chip{display:inline-block;border:1px solid #6b62574d;background:#a9957910;color:#c7beb1;border-radius:5px;padding:2px 7px;font-size:11px;line-height:1.5}
.ed-system-map .body-heading>.chip{color:var(--accent);border-color:var(--accent);background:#0002}
.ed-system-map .chip.positive{color:#99d6b0;border-color:#72b88750}
.ed-system-map .chip.signal{color:#a2e5b0;border-color:#72b88760;background:#24442b55}
.ed-system-map .chip.material{color:#c1c5cb}
.ed-system-map .chip.ring{color:#ddbd68;border-color:#ddbd6860}
.ed-system-map .metrics{display:flex;gap:10px 26px;flex-wrap:wrap;margin:12px 0}
.ed-system-map .metrics>div>span{display:block;color:#a39b91;font-size:10px;text-transform:uppercase;letter-spacing:.07em}
.ed-system-map .metrics strong{font:14px/1.7 Consolas,monospace;font-weight:400;color:#e3ddd4}
.ed-system-map .badges,.ed-system-map .materials{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.ed-system-map .mini-label{font-size:11px;color:#aaa196;margin-right:4px;align-self:center}
.ed-system-map .environment{display:flex;flex-wrap:wrap;gap:6px 22px;font-size:12px;color:#c9c0b5}
.ed-system-map .environment b{font-weight:400;color:#999086;margin-right:5px}
.ed-system-map .ringline{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:8px 0;font-size:12px}
.ed-system-map .muted{color:#a29b93}
.ed-system-map .empty{padding:30px;border:1px dashed #554536;border-radius:8px}
.ed-system-map details{border-top:1px solid #ffffff0d;margin-top:8px;padding-top:6px}
.ed-system-map summary{cursor:pointer;color:#b4a695;font-size:12px;padding:4px 0;overflow-wrap:anywhere}
.ed-system-map summary:hover{color:#ffb454}
.ed-system-map details[open]>summary{color:#ffb454}
.ed-system-map details details{margin-left:12px}
.ed-system-map summary:focus-visible,.ed-system-map a:focus-visible,.ed-system-map button:focus-visible{outline:2px solid #ffb454;outline-offset:4px}
.ed-system-map .fields{margin:8px 0;font-size:12px}
.ed-system-map .fields>div{display:grid;grid-template-columns:minmax(130px,25%) minmax(0,1fr);gap:14px;padding:7px 10px;border-bottom:1px solid #ffffff08}
.ed-system-map .fields>div:nth-child(odd){background:#ffffff03}
.ed-system-map .fields dt{color:#afa396;overflow-wrap:anywhere}
.ed-system-map .fields dd{margin:0;overflow-wrap:anywhere;white-space:pre-wrap;color:#ddd7cf}
.ed-system-map .fields .fields{margin:0}
.ed-system-map .fields .fields>div{padding:4px 6px}
.ed-system-map .records{padding-left:20px;margin:0}
.ed-system-map .records>li{padding:4px 0}
.ed-system-map .toolbar{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}
.ed-system-map .toolbar button{font-size:12px}
@media(max-width:700px){.ed-system-map main{padding:20px 14px}
.ed-system-map .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
.ed-system-map .stats>div{padding:12px}
.ed-system-map .tree ul{margin-left:7px;padding-left:11px}
.ed-system-map .tree ul>li:before{left:-11px;width:11px}
.ed-system-map .body-card{padding:12px}
.ed-system-map .body-heading h3{font-size:15px}
.ed-system-map .body-id{margin-left:0}
.ed-system-map .fields>div{grid-template-columns:1fr;gap:3px}
.ed-system-map .metrics{gap:8px 16px}
.ed-system-map pre{padding:14px}
}
@media print{.ed-system-map nav,.ed-system-map .toolbar,.ed-system-map #connection{display:none}
.ed-system-map details{break-inside:avoid}
.ed-system-map{background:#fff;color:#111}
.ed-system-map .body-card{break-inside:avoid}
}
"""


def render_map_page(result=None, *, system=None, message=None, export=False):
    title = str((result or {}).get("system_name") or "System map")
    value = (result or {}).get("system_address")
    address = str(value if value is not None else system or "")
    mode = "Current / last system" if system is None else "Saved system"
    tree = (result or {}).get("simple_text") or message or "Waiting for journal data. No system map is available yet."
    updated = str((result or {}).get("last_updated") or "Not recorded yet")
    model = (result or {}).get("model")
    content = render_details(model) if model is not None else '<pre aria-label="System body hierarchy">' + escape(tree) + '</pre>'
    mode = "Saved snapshot" if export else mode
    section = (
        '<section' + ('' if export else ' id="map" data-system="' + escape(address, quote=True) + '"')
        + '><header><div class="eyebrow">Elite State \u00b7 ' + escape(mode) + '</div>'
        + '<h1>' + escape(title) + '</h1><div class="meta"><span>System ID: '
        + escape(address or "Unknown") + '</span><span>Journal update: '
        + escape(updated) + '</span></div></header>' + content + '</section>'
    )
    footer = "Journal-based schematic \u00b7 Distances from arrival in light-seconds \u00b7 Not to scale"
    if export:
        return ('<style>\n' + MAP_CSS + '\n</style>\n<div class="ed-system-map"><main>'
                + section + '<footer>' + footer + '</footer></main></div>')
    export_url = "/map/export" + ("?system=" + address if address.isascii() and address.isdecimal() else "")
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + escape(title) + """ | Elite State Map</title>
<style>""" + MAP_CSS + """</style></head><body class="ed-system-map"><main>
<div class="toolbar"><button type="button" id="expand">Expand all details</button><button type="button" id="collapse">Collapse details</button></div>
""" + section + """
<footer>""" + footer + """
<div id="connection" role="status">Live · Refreshes every 5 seconds</div></footer>
<nav><a id="export-map" href=""" + '"' + escape(export_url, quote=True) + '"' + """ download>Export WordPress HTML</a><a href="/map">Follow current system</a><form action="/map" method="get">
<label for="system">System ID</label><input id="system" name="system" inputmode="numeric" pattern="[0-9]+" required value=""" + '"' + escape(str(system or ""), quote=True) + '"' + """ placeholder="SystemAddress"><button>View map</button></form></nav>
</main><script>
document.getElementById('expand').onclick=()=>document.querySelectorAll('#map details').forEach(item=>item.open=true);
document.getElementById('collapse').onclick=()=>document.querySelectorAll('#map details').forEach(item=>item.open=false);
let lastMarkup=document.getElementById('map').innerHTML;
async function refresh(){
 try{
  const response=await fetch(location.href,{cache:'no-store',signal:AbortSignal.timeout(15000)});
  if(!response.ok && response.status!==404)throw new Error('Refresh failed');
  const page=new DOMParser().parseFromString(await response.text(),'text/html');
  const next=page.getElementById('map');
  if(!next)throw new Error('Map unavailable');
  const current=document.getElementById('map');
  if(lastMarkup!==next.innerHTML || current.dataset.system!==next.dataset.system){
   lastMarkup=next.innerHTML;
   const sameSystem=current.dataset.system===next.dataset.system;
   const expanded=new Set([...current.querySelectorAll('details[open]')].map(item=>item.dataset.key));
   const focused=document.activeElement;
   const focusKey=focused?.tagName==='SUMMARY'?focused.parentElement.dataset.key:null;
   const anchor=[...current.querySelectorAll('.body-card')].find(item=>item.getBoundingClientRect().bottom>0);
   const top=anchor?.getBoundingClientRect().top;
   const left=current.querySelector('pre')?.scrollLeft||0;
   current.replaceWith(next);
   if(sameSystem){
    next.querySelectorAll('details').forEach(item=>{item.open=expanded.has(item.dataset.key);if(item.dataset.key===focusKey)item.querySelector('summary').focus({preventScroll:true});});
    const replacement=anchor?document.getElementById(anchor.id):null;
    if(replacement)window.scrollBy(0,replacement.getBoundingClientRect().top-top);
    const pre=next.querySelector('pre');if(pre)pre.scrollLeft=left;
   }
  }
  document.title=page.title;
  document.getElementById('export-map').href=page.getElementById('export-map').getAttribute('href');
  document.getElementById('connection').textContent='Live · Refreshes every 5 seconds';
 }catch(error){document.getElementById('connection').textContent='Connection interrupted · Showing last map · Retrying…';}
 finally{setTimeout(refresh,5000);}
}
setTimeout(refresh,5000);
</script></body></html>"""
