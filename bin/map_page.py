"""Standalone, self-refreshing HTML view for the Elite State server."""

from html import escape


def render_map_page(result=None, *, system=None, message=None):
    title = str((result or {}).get("system_name") or "System map")
    address = str((result or {}).get("system_address") or system or "")
    mode = "Current / last system" if system is None else "Saved system"
    tree = (result or {}).get("simple_text") or message or "Waiting for journal data. No system map is available yet."
    updated = str((result or {}).get("last_updated") or "Not recorded yet")
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>""" + escape(title) + """ | Elite State Map</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}
body{margin:0;background:#090e16;color:#e9eef7;font:16px/1.6 system-ui,sans-serif}
main{max-width:1500px;margin:auto;padding:32px}
header{border-bottom:1px solid #334155;padding-bottom:20px}
.eyebrow{color:#ffb454;text-transform:uppercase;letter-spacing:.16em;font-size:13px}
h1{font-size:clamp(28px,4vw,48px);line-height:1.2;margin:10px 0;overflow-wrap:anywhere}
.meta,footer{color:#a6b6cd;font-size:14px}.meta{display:flex;gap:24px;flex-wrap:wrap}
pre{font:clamp(14px,1.3vw,19px)/1.9 Consolas,monospace;overflow:auto;padding:24px;background:#111b2a;border:1px solid #28384f;border-radius:12px;min-height:220px}
nav{display:flex;align-items:center;flex-wrap:wrap;gap:20px;margin-top:24px}
a{color:#ffb454}form{display:flex;align-items:center;flex-wrap:wrap;gap:10px}
input,button{font:inherit;padding:7px 12px;border:1px solid #52617a;border-radius:6px;background:#162235;color:inherit}
button{cursor:pointer;color:#ffb454}input{max-width:100%;width:230px}
@media(max-width:600px){main{padding:16px}pre{padding:14px}}
</style></head><body><main>
<section id="map"><header><div class="eyebrow">Elite State · """ + escape(mode) + """</div>
<h1>""" + escape(title) + """</h1><div class="meta"><span>System ID: """ + escape(address or "Unknown") + """</span><span>Journal update: """ + escape(updated) + """</span></div></header>
<pre aria-label="System body hierarchy">""" + escape(tree) + """</pre></section>
<footer>Journal-based schematic · Distances from arrival in light-seconds · Not to scale
<div id="connection" role="status">Live · Refreshes every 5 seconds</div></footer>
<nav><a href="/map">Follow current system</a><form action="/map" method="get">
<label for="system">System ID</label><input id="system" name="system" inputmode="numeric" pattern="[0-9]+" required value=""" + '"' + escape(str(system or ""), quote=True) + '"' + """ placeholder="SystemAddress"><button>View map</button></form></nav>
</main><script>
async function refresh(){
 try{
  const response=await fetch(location.href,{cache:'no-store',signal:AbortSignal.timeout(15000)});
  if(!response.ok && response.status!==404)throw new Error('Refresh failed');
  const page=new DOMParser().parseFromString(await response.text(),'text/html');
  const next=page.getElementById('map');
  if(!next)throw new Error('Map unavailable');
  const current=document.getElementById('map');
  if(current.innerHTML!==next.innerHTML){
   const left=current.querySelector('pre').scrollLeft;
   current.replaceWith(next);next.querySelector('pre').scrollLeft=left;
  }
  document.title=page.title;
  document.getElementById('connection').textContent='Live · Refreshes every 5 seconds';
 }catch(error){document.getElementById('connection').textContent='Connection interrupted · Showing last map · Retrying…';}
 finally{setTimeout(refresh,5000);}
}
setTimeout(refresh,5000);
</script></body></html>"""
