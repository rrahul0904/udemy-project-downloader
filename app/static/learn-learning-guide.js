// Full instructional synthesis. No generic seven-item recap is substituted on error.
const button = document.querySelector("#learning-guide-generate");
const output = document.querySelector("#learning-guide-content");
const status = document.querySelector("#learning-guide-status");
let context = null;
let poller = null;
let generation = 0;
const safe = (v) => String(v ?? "").replace(/[&<>'"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[c]));
const stamp = ms => {if(ms === null || ms === undefined)return "untimed";const t = Math.floor(Math.max(0,Number(ms))/1000);return Math.floor(t/60)+":"+String(t%60).padStart(2,"0");};
function link(c) {
  if(!context || !Number.isFinite(Number(c.start_ms)))return "";
  const t = Math.max(0, Math.floor(Number(c.start_ms)));
  return '<a class="source-citation" href="/viewer?lesson='+encodeURIComponent(context.lesson.id)+'&t='+t+'" title="See original evidence">↗ '+stamp(t)+'</a>';
}
const cite = items => '<span class="learning-citations">'+(items||[]).map(link).join(" ")+"</span>";
const para = v => '<p>'+safe(v)+'</p>';
const numeric = n => Number.isFinite(Number(n)) ? Number(n) : 0;
function visuals(items) {
  if(!context || !items?.length)return "";
  return '<div class="learning-frames">'+items.map(item=>{
    const frame = String(item.frame_file||"").split("/").pop();
    if(!/^(periodic|scene)-\d{4}\.jpg$/.test(frame))return "";
    const url = '/api/v1/lessons/'+encodeURIComponent(context.lesson.id)+'/visuals/frame/'+encodeURIComponent(frame);
    return '<figure><img loading="lazy" src="'+url+'" alt="Sampled lecture frame—unverified"/><figcaption>Visual evidence near '+stamp(item.timestamp_ms)+' — '+safe(item.category||'frame')+'. OCR and details require review.</figcaption></figure>';
  }).join("")+"</div>";
}
function render(artifact) {
  const guide = artifact?.content || artifact;
  if(!guide?.chapters?.length)throw Error("Generated artifact is missing instructional chapters.");
  const cards = (guide.takeaways||[]).map((item,i)=>
    '<li><span class="learning-list-num">'+(i+1)+'.</span> '+safe(item.text)+' '+cite(item.citations)+'</li>').join("");
  const chapters = (guide.chapters||[]).map((part,i)=>
    '<article class="learning-chapter"><p class="ci-eyebrow">LESSON '+(i+1)+'</p>'+
    '<h3>'+safe(part.heading)+'</h3>'+para(part.explanation)+
    '<h4>Why it matters</h4>'+para(part.why_it_matters)+
    '<h4>How to do it</h4><ol>'+(part.steps||[]).map(step=>'<li>'+safe(step)+'</li>').join('')+'</ol>'+
    visuals(part.visuals)+
    '<h4>What to check / common pitfalls</h4>'+para(part.pitfalls)+
    '<div class="learning-source">Original lecture '+cite(part.citations)+'</div></article>'
  ).join("");
  const ex = guide.worked_example || {};
  const tasks = (guide.practice||[]).map((q,i)=>
    '<details class="learning-exercise"><summary>Exercise '+(i+1)+': '+safe(q.question)+'</summary>'+
    '<div class="learning-exercise-answer"><h4>Worked answer</h4>'+para(q.model_answer)+cite(q.citations)+'</div></details>'
  ).join("");
  output.innerHTML =
    '<div class="learning-disclaimer"><strong>Model-generated teaching draft — review required.</strong> Each lesson links to the source. Source links are evidence, not independent proof of every claim.</div>'+
    '<header class="learning-intro"><span class="ci-eyebrow">WHAT YOU LEARNED</span><h2>'+safe(guide.title)+'</h2>'+para(guide.overview)+
    '<h3>Learning outcomes</h3><ul>'+(guide.learning_outcomes||[]).map(x=>'<li>'+safe(x)+'</li>').join('')+'</ul></header>'+
    '<section class="learning-takeaways"><h3>Key concepts and takeaways</h3><ol>'+cards+'</ol></section>'+
    '<section class="learning-chapters"><h2>Learn the workflow, step by step</h2>'+chapters+'</section>'+
    '<section class="learning-example"><h2>Worked example</h2><h3>Scenario</h3>'+para(ex.scenario)+
    '<ol>'+(ex.steps||[]).map(x=>'<li>'+safe(x)+'</li>').join('')+'</ol>'+
    '<h3>How to interpret the result</h3>'+para(ex.expected_result)+
    '<h3>Limitations</h3>'+para(ex.limitations)+cite(ex.citations)+'</section>'+
    '<section class="learning-practice"><h2>Test your understanding</h2>'+tasks+'</section>'+
    '<section class="learning-audit"><h2>Review before operational use</h2>'+
    '<ul>'+(guide.evidence_limits||[]).concat(guide.review_flags||[]).map(x=>'<li>'+safe(x)+'</li>').join('')+'</ul></section>';
}
function clearPoll(){if(poller!==null){clearInterval(poller);poller=null;}}
async function request(path, options) {
  const response = await fetch(path, {cache:"no-store",...options});
  let data = {};
  try{data=await response.json();}catch(_) {}
  if(!response.ok)throw Error(typeof data.detail==="string" ? data.detail : "Request failed ("+response.status+")");
  return data;
}
async function loadExisting(lessonId, current) {
  const result = await request('/api/v1/lessons/'+encodeURIComponent(lessonId)+'/artifacts?kind=learning_guide');
  if(current!==generation)return;
  const found = (result.artifacts||[]).sort((a,b)=>numeric(b.version)-numeric(a.version))[0];
  if(found){
    render(found);
    status.textContent = 'Generated lesson version '+found.version+' · AI draft requiring source review.';
    button.textContent = 'Regenerate full lesson';
  }else{
    status.textContent = 'No complete learning guide yet. Configure a local Ollama model and generate one.';
  }
}
function fail(error) {
  clearPoll();
  button.disabled=false;
  status.textContent=error.message || "Unable to generate a full lesson.";
}
window.addEventListener('ci:lesson-opened',event=>{
  context=event.detail;
  generation++;
  clearPoll();
  button.disabled=false;
  button.textContent='Generate full learning material';
  output.innerHTML='<div class="ci-empty">No complete instructional lesson yet. Original source transcript and visual evidence remain available in other tabs.</div>';
  if(context?.lesson?.id)loadExisting(context.lesson.id,generation).catch(fail);
});
async function poll(lessonId, jobId, current){
  if(current!==generation)return;
  try{
    const job = await request('/api/v1/lessons/'+encodeURIComponent(lessonId)+'/learning-guide/jobs/'+encodeURIComponent(jobId));
    if(current!==generation)return;
    if(job.status==='failed')throw Error(job.error||'Local model rejected the output. Nothing was published.');
    if(job.status==='complete'){
      clearPoll();
      button.disabled=false;
      const artifact=await request('/api/v1/artifacts/'+encodeURIComponent(job.artifact_id));
      if(current===generation){
        render(artifact);
        status.textContent='Full instructional lesson generated and saved (draft v'+artifact.version+'). Review source citations.';
        button.textContent='Regenerate full lesson';
      }
      return;
    }
    status.textContent = 'Generating detailed instruction: source review, concepts, workflows, examples and answers. Status: '+safe(job.status)+'.';
  }catch(error){if(current===generation)fail(error);}
}
button?.addEventListener("click",async()=>{
  if(!context?.lesson?.id)return;
  const current=generation, lessonId=context.lesson.id;
  button.disabled=true;
  status.textContent='Starting source-grounded lesson generation…';
  try{
    const job=await request('/api/v1/lessons/'+encodeURIComponent(lessonId)+'/learning-guide/jobs',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({transcript_id:context.transcript?.id||null}),
    });
    if(current!==generation)return;
    await poll(lessonId,job.id,current);
    if(current===generation && poller===null && button.disabled){
      poller=setInterval(()=>poll(lessonId,job.id,current),2500);
    }
  }catch(error){if(current===generation)fail(error);}
});
