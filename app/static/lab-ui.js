const RECENT_KEY='course-intelligence-recent-tools';
let activeFilter='all';
const grid=document.querySelector('#tool-grid');
const search=document.querySelector('#tool-search');
const recentRoot=document.querySelector('#recent-tools');

function readRecent(){try{return JSON.parse(localStorage.getItem(RECENT_KEY)||'[]').filter(Boolean).slice(0,5)}catch(_){return[]}}
function writeRecent(tool){const next=[tool,...readRecent().filter((item)=>item!==tool)].slice(0,5);localStorage.setItem(RECENT_KEY,JSON.stringify(next));renderRecent(next);}
function labelFor(tool){return grid.querySelector(`[data-tool="${CSS.escape(tool)}"] h3`)?.textContent||tool;}
function renderRecent(items=readRecent()){
  if(!items.length){recentRoot.innerHTML='';return;}
  recentRoot.innerHTML=`<div class="ci-list-row"><span><strong>Recently used</strong><small>Stored only in this browser.</small></span><span style="display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end">${items.map((tool)=>`<button class="ci-badge orange" type="button" data-recent-tool="${tool}">${labelFor(tool)}</button>`).join('')}</span></div>`;
  recentRoot.querySelectorAll('[data-recent-tool]').forEach((button)=>button.addEventListener('click',()=>grid.querySelector(`[data-open="${CSS.escape(button.dataset.recentTool)}"]`)?.click()));
}
function applyFilters(){const query=search.value.trim().toLowerCase();grid.querySelectorAll('.tool-card').forEach((card)=>{const categoryMatch=activeFilter==='all'||card.dataset.category===activeFilter;const searchMatch=!query||String(card.dataset.search||'').includes(query)||card.textContent.toLowerCase().includes(query);card.hidden=!(categoryMatch&&searchMatch);});}
document.querySelectorAll('[data-filter]').forEach((button)=>button.addEventListener('click',()=>{activeFilter=button.dataset.filter;document.querySelectorAll('[data-filter]').forEach((item)=>item.classList.toggle('active',item===button));applyFilters();}));
search.addEventListener('input',applyFilters);
grid.addEventListener('click',(event)=>{const button=event.target.closest('[data-open]');if(button)writeRecent(button.dataset.open);});
renderRecent();
