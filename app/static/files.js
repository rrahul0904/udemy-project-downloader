function escapeHtml(value) { return String(value ?? '').replace(/[&<>'"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'})[c]); }
function bytes(value) { const n=Number(value||0); if(!n) return '0 B'; const u=['B','KB','MB','GB','TB']; const i=Math.min(u.length-1,Math.floor(Math.log(n)/Math.log(1024))); return `${(n/(1024**i)).toFixed(i>1?1:0)} ${u[i]}`; }
function encoded(path) { return String(path).split('/').map(encodeURIComponent).join('/'); }
let files=[];
function render() {
  const q=document.querySelector('#file-search').value.trim().toLowerCase();
  const rows=files.filter((item)=>item.type==='file'&&(!q||`${item.name} ${item.path}`.toLowerCase().includes(q)));
  document.querySelector('#file-list').innerHTML=rows.length?rows.map((item)=>{
    const lower=item.name.toLowerCase();
    const study=/(csv|tsv|txt|xvg|pdb|gro|xyz|bib|tex|json)$/i.test(lower);
    const transcript=/\.(vtt|srt|json3|txt|md)$/i.test(lower);
    return `<div class="ci-list-row"><span style="min-width:0"><strong style="overflow-wrap:anywhere">${escapeHtml(item.name)}</strong><small class="ci-mono">${escapeHtml(item.path)} · ${bytes(item.size)}</small></span><span style="display:flex;gap:7px;flex-wrap:wrap;justify-content:flex-end"><a class="ci-badge" href="/files/${encoded(item.path)}" target="_blank" rel="noopener">open</a>${transcript?'<a class="ci-badge blue" href="/learn">learn</a>':''}${study?'<a class="ci-badge orange" href="/lab">Study Lab</a>':''}</span></div>`;
  }).join(''):'<div class="ci-empty">No matching files.</div>';
}
async function init(){ const response=await fetch('/api/downloads'); if(!response.ok) throw new Error('Unable to read download inventory.'); const payload=await response.json(); files=payload.files||[]; const actual=files.filter((x)=>x.type==='file'); document.querySelector('#files-count').textContent=actual.length; document.querySelector('#files-size').textContent=bytes(actual.reduce((s,x)=>s+Number(x.size||0),0)); document.querySelector('#files-root').textContent=payload.root==='persistent-storage'?'persistent':'local'; render(); document.querySelector('#file-search').addEventListener('input',render); }
init().catch((error)=>{document.querySelector('#file-list').innerHTML=`<div class="ci-empty">${escapeHtml(error.message)}</div>`;});
