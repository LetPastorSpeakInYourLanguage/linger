// storylens UI — vanilla JS, hash routes: #/  #/title/<id>/<tab>  #/job/<id>  #/jobs  #/tasks  #/settings  #/help
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const ts = s => { s = Math.max(0, Math.floor(s||0)); const h=Math.floor(s/3600), m=Math.floor(s%3600/60), x=s%60; return (h?h+":":"")+String(m).padStart(2,"0")+":"+String(x).padStart(2,"0"); };
const tier = t => `<span class="tier ${esc(t)}">${esc(t)}</span>`;
async function api(path, opts={}) {
  const o = {headers:{"Content-Type":"application/json"}, ...opts};
  if (o.body && typeof o.body !== "string" && !(o.body instanceof FormData)) o.body = JSON.stringify(o.body);
  if (o.body instanceof FormData) delete o.headers;
  const r = await fetch(path, o);
  if (!r.ok) { let m = await r.text(); try { m = JSON.parse(m).detail || m } catch(e){}; throw new Error(m); }
  return r.json();
}
function modal(html){ $("#modal-content").innerHTML = html; $("#modal").classList.remove("hidden"); }
function closeModal(){ $("#modal").classList.add("hidden"); $("#modal-content").innerHTML=""; }
let timer = null, STATUS = null;
function poll(fn, ms=2000){ clearInterval(timer); timer = setInterval(fn, ms); }
async function refreshStatus(){
  try { STATUS = await api("/api/status");
    $("#badge").textContent = `${STATUS.answerer==="mock"?"offline answers":"Claude"} · ${STATUS.settings.autonomy}`;
    const n = STATUS.open_tasks + STATUS.reviews;
    $("#nav-tasks").textContent = n ? `Claude tasks (${STATUS.open_tasks}${STATUS.reviews?` · ${STATUS.reviews} review`:""})` : "Claude tasks";
  } catch(e) { $("#badge").textContent = "server offline"; }
}
async function route(){
  clearInterval(timer); await refreshStatus();
  const [_, page, a, b] = location.hash.split("/");
  try {
    if (!page) return home();
    if (page==="title") return titlePage(a, b||"overview");
    if (page==="job") return jobPage(a);
    if (page==="jobs") return jobsPage();
    if (page==="explore") return explorePage(a||"all");
    if (page==="tasks") return tasksPage(a||"open");
    if (page==="settings") return settingsPage();
    if (page==="help") return helpPage();
  } catch(e){ $("#app").innerHTML = `<div class="card">⚠ ${esc(e.message)}</div>`; }
}
window.addEventListener("hashchange", route); window.addEventListener("load", route);

// ------------------------------------------------------------ library
async function home(){
  const ts_ = await api("/api/titles");
  $("#app").innerHTML = `
  <div class="row"><h1>Library</h1><span class="spacer"></span><button onclick="addTitle()">+ Add title</button></div>
  ${STATUS.open_tasks ? `<div class="card small">⏳ <b>${STATUS.open_tasks} task(s) are waiting for Claude.</b> In the Claude desktop app, open the workspace folder
     <code>${esc(STATUS.workspace)}</code> and say <i>"do the storylens queue"</i> (Claude follows <code>CLAUDE.md</code>). <a href="#/tasks">See the tasks</a>.</div>`:""}
  <div class="grid">${ts_.map(t=>`<a class="card" style="text-decoration:none;color:inherit" href="#/title/${t.id}">
     <b>${esc(t.name)}</b><div class="muted small">${t.kind} · ${t.media.length} media · understanding ${t.understanding_version||"—"}</div></a>`).join("")||
     `<div class="card muted">No titles yet. Click <b>Add title</b>, or run <code>storylens demo</code> in a terminal for a sample.</div>`}</div>`;
}
function addTitle(){
  modal(`<h2>Add a title</h2>
  <label>Name</label><input id="t-name" style="width:100%" placeholder="e.g. My Telenovela">
  <div class="row"><div><label>Kind</label><select id="t-kind">${["film","series","podcast","talkshow","sermon","lecture"].map(k=>`<option>${k}</option>`).join("")}</select></div>
  <div style="flex:1"><label>Cast / character or speaker names (optional, comma-separated)</label><input id="t-cast" style="width:100%"></div></div>
  <label>Scan a folder on this computer (video/audio + .srt/.vtt/.ass/.txt transcripts paired by name) — optional</label><input id="t-folder" style="width:100%" placeholder="D:\\Shows\\Season 1">
  <p class="small muted">You can also add individual files on the title page.</p>
  <button onclick="createTitle()">Create</button>`);
}
async function createTitle(){
  const t = await api("/api/titles", {method:"POST", body:{name:$("#t-name").value, kind:$("#t-kind").value, cast:$("#t-cast").value, folder:$("#t-folder").value}});
  closeModal(); location.hash = `#/title/${t.id}`;
}

// ------------------------------------------------------------ title
const TABS = [["overview","Overview"],["story","Story"],["characters","Characters"],["facts","Fact ledger"],["lenses","Lenses"],["recap","Make a recap"],["jobs","Jobs"]];
async function titlePage(tid, tab){
  const d = await api(`/api/titles/${tid}`); const t = d.title, u = d.understanding;
  const head = `<div class="row"><h1>${esc(t.name)}</h1><span class="muted">${t.kind} · ${t.media.length} media · understanding ${u?u.version:"—"}</span></div>
   <div class="tabs">${TABS.map(([k,v])=>`<a class="${k===tab?"on":""}" href="#/title/${tid}/${k}">${v}</a>`).join("")}</div><div id="tab"></div>`;
  $("#app").innerHTML = head;
  const T = $("#tab");
  if (tab==="overview") return overview(T, d);
  if (!u && tab!=="jobs") { T.innerHTML = `<div class="card">Run <b>Understand</b> on the Overview tab first.</div>`; return; }
  if (tab==="story") return storyTab(T, tid, d);
  if (tab==="characters") return charactersTab(T, tid, d);
  if (tab==="facts") return factsTab(T, tid, d);
  if (tab==="lenses") return lensesTab(T, tid, d);
  if (tab==="recap") return recapTab(T, tid, d);
  if (tab==="jobs") return jobsList(T, tid);
}
function overview(T, d){
  const t = d.title, u = d.understanding, m = u && u.manifest;
  T.innerHTML = `
  <div class="card"><h2>Media</h2>
   <table><tr><th>id</th><th>label</th><th>video</th><th>subtitles</th><th>cues</th><th></th></tr>
   ${t.media.map(x=>`<tr><td>${x.id}</td><td>${esc(x.label)}${x.season?` <span class="pill">S${x.season}E${x.episode}</span>`:""}</td>
     <td class="small">${esc(x.video||"—")}</td><td class="small">${esc(x.subs||"embedded / —")}</td><td>${(d.media_info[x.id]||{}).cues||""}</td>
     <td><button class="secondary" onclick="delMedia('${t.id}','${x.id}')">remove</button></td></tr>`).join("")}</table>
   <div class="row" style="margin-top:10px">
     <input id="m-video" placeholder="video path (optional)" style="flex:1"><input id="m-subs" placeholder="subtitle path (.srt/.vtt/.ass) — optional if embedded" style="flex:1">
     <button onclick="addMedia('${t.id}')">Add</button></div>
   <div class="row" style="margin-top:6px"><input id="m-folder" placeholder="…or scan a folder" style="flex:1"><button class="secondary" onclick="scanFolder('${t.id}')">Scan</button>
     <input type="file" id="m-upload" accept=".srt,.vtt,.ass,.ssa"><button class="secondary" onclick="uploadSubs('${t.id}')">Upload subtitles</button></div>
  </div>
  <div class="card"><div class="row"><h2>Understanding</h2><span class="spacer"></span>
     <select id="u-auto"><option value="">review gate (default)</option><option value="autopilot">autopilot (approve if metrics pass)</option><option value="auto">approve everything</option></select>
     <select id="u-vision"><option value="auto">vision: auto</option><option value="on">vision: on</option><option value="off">vision: off</option></select>
     <button onclick="runUnderstand('${t.id}')" ${t.media.length?"":"disabled"}>${u?"Re-run":"Understand"}</button></div>
   ${u ? `<p><b>${esc(u.bible.logline||"")}</b></p><p class="muted">${esc(u.bible.genre_tone||"")}</p>
     <div class="row">${["P0","P1","P2","P3"].map(k=>`${tier(k)} ${u.tiers[k]}`).join(" &nbsp; ")}
      <span class="pill">${m.beats} beats</span><span class="pill">${m.facts} facts</span><span class="pill">${m.scenes} scenes</span>
      <span class="pill">coverage ${Math.round(100*m.coverage)}%</span><span class="pill">unknown speakers ${Math.round(100*m.unknown_speaker_rate)}%</span>
      <span class="pill">answered by ${esc(m.answered_by||"")}</span><span class="pill">${(m.usage||{}).tasks||0} Claude tasks (${(m.usage||{}).cached||0} reused)</span></div>
     <h3>Turning points</h3>${(u.bible.turning_points||[]).map(x=>`<div class="small">${esc(x.tp)} → ${esc(x.beat_id)}</div>`).join("")}`
   : `<p class="muted">Not understood yet. This queues one Claude task per part of each episode (scene cards, beats with their causes, and a fact ledger for every character or speaker), then one integration task for the global story, then asks you to review (gate G1).</p>`}
  </div>
  <div class="card"><h2>Title instructions</h2><p class="small muted">Merged into every prompt for this title (e.g. "the twins are played by one actor", "skip the dream sequences").</p>
   <textarea id="t-ins">${esc(d.instructions)}</textarea><button class="secondary" onclick="saveTitleIns('${t.id}')">Save</button></div>
  <div class="card"><button class="danger" onclick="delTitle('${t.id}')">Delete title</button> <span class="small muted">(removes it from the workspace; your media files are untouched)</span></div>`;
}
async function addMedia(tid){ try { await api(`/api/titles/${tid}/media`, {method:"POST", body:{video:$("#m-video").value.trim(), subs:$("#m-subs").value.trim()}}); route(); } catch(e){ alert(e.message) } }
async function scanFolder(tid){ try { const r = await api(`/api/titles/${tid}/scan`, {method:"POST", body:{folder:$("#m-folder").value.trim()}}); alert(`added ${r.length} media`); route(); } catch(e){ alert(e.message) } }
async function uploadSubs(tid){ const f=$("#m-upload").files[0]; if(!f) return; const fd=new FormData(); fd.append("file", f); await api(`/api/titles/${tid}/upload-subs`, {method:"POST", body:fd}); route(); }
async function delMedia(tid, mid){ await api(`/api/titles/${tid}/media/${mid}`, {method:"DELETE"}); route(); }
async function delTitle(tid){ if(confirm("Delete this title from the workspace?")){ await api(`/api/titles/${tid}`, {method:"DELETE"}); location.hash="#/"; } }
async function saveTitleIns(tid){ await api(`/api/titles/${tid}/instructions`, {method:"PUT", body:{text:$("#t-ins").value}}); alert("saved"); }
async function runUnderstand(tid){ const r = await api(`/api/titles/${tid}/understand`, {method:"POST", body:{autonomy:$("#u-auto").value, vision:$("#u-vision").value}}); location.hash = `#/job/${r.job}`; }

// story (beats) with tier corrections and line viewer
async function storyTab(T, tid){
  T.innerHTML = `<div class="row"><select id="b-tier"><option value="">all tiers</option><option>P0</option><option>P1</option><option>P2</option><option>P3</option></select>
    <input id="b-q" placeholder="filter text / character"><button class="secondary" id="b-go">Filter</button>
    <span class="spacer"></span><input id="s-q" placeholder="full-text search (lines, facts, beats)"><button class="secondary" id="s-go">Search</button></div><div id="b-list"></div>`;
  const load = async () => {
    const bs = await api(`/api/titles/${tid}/beats?tier=${$("#b-tier").value}&q=${encodeURIComponent($("#b-q").value)}`);
    $("#b-list").innerHTML = `<table><tr><th>tier</th><th>where</th><th>beat</th><th>who</th><th>score</th><th></th></tr>${bs.map(b=>`
     <tr><td><select onchange="setTier('${tid}','${b.id}',this.value)">${["P0","P1","P2","P3"].map(k=>`<option ${k===b.tier?"selected":""}>${k}</option>`).join("")}</select></td>
     <td class="small">${b.media} ${ts(b.t0)}<br>L${b.lines[0]}–${b.lines[1]}</td><td>${esc(b.text)}<div class="small muted">${esc(b.kind)} · ${esc(b.emotion)}</div></td>
     <td class="small">${esc(b.who.join(", "))}</td><td>${b.score}</td><td><button class="secondary" onclick="showLines('${tid}','${b.media}',${b.lines[0]},${b.lines[1]},${b.t0})">lines</button></td></tr>`).join("")}</table>`;
  };
  $("#b-go").onclick = load; $("#s-go").onclick = async () => {
    const r = await api(`/api/titles/${tid}/search?q=${encodeURIComponent($("#s-q").value)}`);
    modal(`<h2>Search</h2><table>${r.map(x=>`<tr><td><span class="pill">${x.kind}</span></td><td class="small">${esc(x.ref)}</td><td>${esc(x.text)}</td></tr>`).join("")}</table>`);
  };
  load();
}
async function setTier(tid, id, v){ await api(`/api/titles/${tid}/corrections`, {method:"POST", body:{target:id, field:"tier", value:v, reason:"set in UI"}}); }
async function showLines(tid, media, l0, l1, t0){
  const ls = await api(`/api/titles/${tid}/lines?media=${media}&l0=${l0}&l1=${l1}&pad=2`);
  modal(`<h2>${media} · L${l0}–L${l1}</h2>
    <video controls preload="metadata" src="/api/titles/${tid}/video/${media}#t=${Math.max(0,t0-1)}"></video>
    <table>${ls.map(l=>`<tr><td class="small muted">L${l.idx} ${ts(l.t0)}</td><td class="small">${esc(l.speaker||"")}</td><td>${esc(l.text)}</td></tr>`).join("")}</table>`);
}

async function charactersTab(T, tid, d){
  const cs = d.understanding.characters.slice().sort((a,b)=>(b.importance||0)-(a.importance||0));
  T.innerHTML = `<table><tr><th>character</th><th>role</th><th>arc</th><th>facts</th><th>lines</th><th></th></tr>${cs.map(c=>`
    <tr><td><b>${esc(c.name)}</b><div class="small muted">${esc((c.aliases||[]).join(", "))}</div></td><td>${esc(c.role)}</td><td class="small">${esc(c.arc)}</td>
    <td>${c.facts||0}</td><td>${c.lines||0}</td>
    <td><button class="secondary" onclick="quickLens('${tid}',{kind:'character',name:${JSON.stringify(c.name).replace(/"/g,"&quot;")}})">Character lens</button>
        <a class="btn secondary" href="#/title/${tid}/facts" onclick="sessionStorage.factActor=${JSON.stringify(c.name).replace(/"/g,"&quot;")}">Ledger</a></td></tr>`).join("")}</table>`;
}
async function quickLens(tid, lens){ const r = await api(`/api/titles/${tid}/lens`, {method:"POST", body:{lens}}); location.hash = `#/job/${r.job}`; }

async function factsTab(T, tid){
  const ACTS = ["","helps","comforts","defends","protects","rescues","sacrifices","gifts","advises","encourages","thanks","apologizes","forgives","confesses","reveals","discovers","decides","plans","refuses","quits","leaves","returns","jokes","teases","mocks","flirts","kisses","rejects","breaks_up","argues","accuses","lies","deceives","betrays","steals","threatens","attacks","kills","other"];
  T.innerHTML = `<p class="small muted">The ledger records what every character does, learns, feels, reveals — including minor characters. Lenses and trait compilations are built from it.</p>
   <div class="row"><input id="f-actor" placeholder="character" value="${esc(sessionStorage.factActor||"")}"><select id="f-act">${ACTS.map(a=>`<option>${a}</option>`).join("")}</select>
   <select id="f-kind"><option></option><option>act</option><option>state</option><option>reveal</option><option>quote</option><option>joke</option><option>moment</option></select>
   <input id="f-q" placeholder="text"><button class="secondary" id="f-go">Filter</button></div><div id="f-list"></div>`;
  sessionStorage.factActor = "";
  const load = async () => {
    const fs = await api(`/api/titles/${tid}/facts?actor=${encodeURIComponent($("#f-actor").value)}&act=${$("#f-act").value}&kind=${$("#f-kind").value}&q=${encodeURIComponent($("#f-q").value)}`);
    $("#f-list").innerHTML = `<p class="small muted">${fs.length} facts</p><table><tr><th>where</th><th>kind</th><th>actor → target</th><th>fact</th><th></th></tr>${fs.map(f=>`
      <tr><td class="small">${f.media} ${ts(f.t0)}<br>L${f.lines[0]}</td><td><span class="pill">${f.kind}${f.act_type?":"+f.act_type:""}${f.field?":"+f.field:""}</span></td>
      <td class="small">${esc(f.actor)}${f.target?" → "+esc(f.target):""}</td><td>${esc(f.text)}${f.value&&f.kind!=="act"?`<div class="small muted">${esc(f.value)}</div>`:""}</td>
      <td><button class="secondary" onclick="showLines('${tid}','${f.media}',${f.lines[0]},${f.lines[1]},${f.t0})">lines</button></td></tr>`).join("")}</table>`;
  };
  $("#f-go").onclick = load; load();
}

function lensForm(d){
  const cs = d.understanding.characters.map(c=>c.name), th = (d.understanding.bible.threads||[]);
  return `<div class="row"><select id="l-kind" onchange="lensKind()"><option value="main">Main story</option><option value="character">Character story</option>
    <option value="topic">What someone said about a topic</option><option value="trait">Trait / theme compilation</option><option value="thread">Storyline</option><option value="pattern">How a speaker builds ideas (pattern)</option>${d.collection?`<option value="overview">Overview of every title</option>`:""}</select>
    <span id="l-char"><select id="l-name">${cs.map(c=>`<option>${esc(c)}</option>`).join("")}</select></span>
    <span id="l-trait"><select id="l-actor"><option value="">(any character)</option>${cs.map(c=>`<option>${esc(c)}</option>`).join("")}</select>
      <input id="l-query" placeholder="e.g. being a good friend" size="28"><label style="display:inline"><input type="checkbox" id="l-deep"> deep sweep</label></span>
    <span id="l-topic"><select id="l-speaker"><option value="">(anyone)</option>${cs.map(c=>`<option>${esc(c)}</option>`).join("")}</select>
      <input id="l-tquery" placeholder="e.g. women and marriage / the meaning of life" size="34"></span>
    <span id="l-pattern"><select id="l-pspeaker"><option value="">(main speaker)</option>${cs.map(c=>`<option>${esc(c)}</option>`).join("")}</select></span>
    <span id="l-thread"><select id="l-th">${th.map(x=>`<option value="${esc(x.id)}">${esc(x.title)}</option>`).join("")}</select></span></div>`;
}
function lensKind(){ const k=$("#l-kind").value; $("#l-char").style.display=k==="character"?"":"none"; $("#l-trait").style.display=k==="trait"?"":"none";
  $("#l-thread").style.display=k==="thread"?"":"none"; $("#l-topic").style.display=k==="topic"?"":"none"; $("#l-pattern").style.display=k==="pattern"?"":"none"; }
function lensValue(){ const k=$("#l-kind").value;
  if(k==="character") return {kind:k, name:$("#l-name").value};
  if(k==="trait") return {kind:k, query:$("#l-query").value, actor:$("#l-actor").value, deep:$("#l-deep").checked};
  if(k==="thread") return {kind:k, thread:$("#l-th").value};
  if(k==="topic") return {kind:k, query:$("#l-tquery").value, speaker:$("#l-speaker").value};
  if(k==="overview") return {kind:k};
  if(k==="pattern") return {kind:k, speaker:$("#l-pspeaker").value};
  return {kind:"main"}; }

async function lensesTab(T, tid, d){
  const vs = await api(`/api/titles/${tid}/views`);
  T.innerHTML = `<div class="card"><h2>Build a lens</h2>${lensForm(d)}<div style="margin-top:8px"><button onclick="buildLens('${tid}')">Build</button></div></div>
   <div class="card"><h2>Lenses</h2><table><tr><th>lens</th><th>kind</th><th>items</th><th>version</th></tr>${vs.map(v=>`
    <tr class="click" onclick="openView('${tid}','${v.id}')"><td>${esc(v.title)}</td><td>${v.kind}</td><td>${v.items}</td><td>${v.version}</td></tr>`).join("")}</table></div>`;
  lensKind();
}
async function buildLens(tid){ const r = await api(`/api/titles/${tid}/lens`, {method:"POST", body:{lens:lensValue(), force:true}}); location.hash = `#/job/${r.job}`; }
async function openView(tid, vid){
  const v = await api(`/api/titles/${tid}/views/${vid}`);
  modal(`<h2>${esc(v.title)}</h2><p>${esc(v.summary||"")}</p>${v.arc?`<p class="muted">${esc(v.arc)}</p>`:""}
   ${(v.hidden_gems||[]).length?`<h3>Hidden gems</h3>${v.hidden_gems.map(g=>`<div>💎 ${esc(g)}</div>`).join("")}`:""}
   <h3>${v.items.length} items${v.candidates?` (from ${v.candidates} candidates)`:""}</h3>
   <table>${v.items.map(i=>`<tr><td>${tier(i.tier)}</td><td class="small">${esc(i.title||"")} ${i.media.split("::").pop()} ${ts(i.t0)}</td><td>${i.speaker?`<b>${esc(i.speaker)}${i.speaker_uncertain?"?":""}</b>: `:""}${esc(i.text)}${i.why?`<div class="small muted">${esc(i.why)}</div>`:""}</td><td>${i.salience}</td></tr>`).join("")}</table>
   <button onclick="closeModal();location.hash='#/title/${tid}/recap';sessionStorage.lens='${esc(JSON.stringify({kind:v.kind,...v.params}))}'">Make a recap from this lens</button>`);
}

async function recapTab(T, tid, d){
  const styles = [["recap_channel","Recap channel (hooky, dense, quotes)"],["dramatic_comedic","Dramatic / comedic"],["short_direct","Short & direct"],
    ["clips","Clips only — no narrator (talks, podcasts, sermons)"],["fan_silent","Fan cut (original audio moments, no narration)"],["detailed_full","Detailed / full"],["character","Character story"],["compilation","Compilation / supercut"]];
  T.innerHTML = `<div class="card"><h2>Make a recap</h2>${lensForm(d)}
   <div class="row"><div><label>Style</label><select id="r-style">${styles.map(([k,v])=>`<option value="${k}">${v}</option>`).join("")}</select></div>
   <div><label>Duration</label><select id="r-dur"><option value="60">1 min</option><option value="180" selected>3 min</option><option value="300">5 min</option>
     <option value="600">10 min</option><option value="900">15 min</option><option value="1800">30 min</option><option value="3600">60 min</option><option value="0">unlimited</option></select></div>
   <div><label>Voice</label><select id="r-voice"><option value="">default (${esc(STATUS.settings.voice)})</option>${["am_michael","am_adam","am_onyx","af_heart","af_bella","bm_george","bf_emma"].map(v=>`<option>${v}</option>`).join("")}</select></div>
   <div><label>Review</label><select id="r-auto"><option value="">gates (I review the script)</option><option value="autopilot">autopilot</option><option value="auto">approve everything</option></select></div></div>
   <div class="row" style="margin-top:8px"><label style="display:inline"><input type="checkbox" id="r-render" checked> render video</label>
    <label style="display:inline"><input type="checkbox" id="r-review" ${STATUS.settings.review?"checked":""}> extra Claude review of the script</label>
    <label style="display:inline"><input type="checkbox" id="r-blur"> blur burned-in subtitles</label></div>
   <label>Instructions for this recap</label><textarea id="r-ins" placeholder="e.g. make the villain sympathetic; no spoilers about the ending"></textarea>
   <button onclick="startRecap('${tid}')">Start</button>
   <p class="small muted">Pipeline: lens → nested duration selection → Claude writes the script from the exact lines → automatic checks (citations, quotes) → <b>you review the script (G2)</b> → voice + render → closed-loop duration fit → <b>final cut review (G3)</b>.</p></div>`;
  lensKind();
  if (sessionStorage.lens){ const l = JSON.parse(sessionStorage.lens); sessionStorage.lens=""; $("#l-kind").value=l.kind; lensKind();
    if(l.name) $("#l-name").value=l.name; if(l.query) $("#l-query").value=l.query; if(l.actor) $("#l-actor").value=l.actor; if(l.thread) $("#l-th").value=l.thread; }
}
async function startRecap(tid){
  const body = {lens:lensValue(), style:$("#r-style").value, duration:+$("#r-dur").value, render:$("#r-render").checked, review:$("#r-review").checked,
                hardsub_blur:$("#r-blur").checked, voice:$("#r-voice").value||null, autonomy:$("#r-auto").value, instructions:$("#r-ins").value};
  const r = await api(`/api/titles/${tid}/recap`, {method:"POST", body}); location.hash = `#/job/${r.job}`;
}

// ------------------------------------------------------------ jobs
async function jobsList(T, tid){
  const js = await api(`/api/jobs${tid?`?title=${tid}`:""}`);
  T.innerHTML = `<table><tr><th>job</th><th>kind</th><th>title</th><th>status</th><th>stage</th></tr>${js.map(j=>`
    <tr class="click" onclick="location.hash='#/job/${j.id}'"><td class="small">${j.id}</td><td>${j.kind}</td><td>${esc(j.title)}</td>
    <td class="status-${j.state.status}">${j.state.status}</td><td class="small">${esc(j.state.stage||"")}</td></tr>`).join("")}</table>`;
}
async function jobsPage(){ $("#app").innerHTML = `<h1>Jobs</h1><div id="tab"></div>`; jobsList($("#tab")); poll(()=>jobsList($("#tab")), 3000); }

async function jobPage(jid){
  const draw = async () => {
    const d = await api(`/api/jobs/${jid}`); const st = d.state, j = d.job;
    const open = d.gates.filter(g=>!g.decision);
    const vcheck = {}; ((d.verify||{}).checks||[]).forEach(c=>vcheck[c.index]=c);
    const art = d.artifacts;
    const keepScroll = window.scrollY;
    $("#app").innerHTML = `
    <div class="row"><h1>${j.kind}: ${esc(j.title)}</h1><span class="muted small">${jid}</span><span class="spacer"></span>
      <a class="btn secondary" href="#/title/${j.title}">Open title</a>
      ${["interrupted","failed","cancelled"].includes(st.status)?`<button class="secondary" onclick="rerunJob('${jid}')">Run again (answers are reused)</button>`:""}
      ${["running","awaiting_review","queued","waiting_for_claude"].includes(st.status)?`<button class="danger" onclick="api('/api/jobs/${jid}/cancel',{method:'POST'})">Cancel</button>`:""}</div>
    <div class="card"><div class="row"><b class="status-${st.status}">${st.status}</b><span>${esc(st.stage||"")}</span><span class="spacer"></span><span class="small muted">${esc(st.message||"")}</span></div>
      <div class="bar" style="margin-top:8px"><i style="width:${Math.round(100*(st.progress||0))}%"></i></div>
      ${st.status==="waiting_for_claude"?`<p>⏳ waiting for Claude: ${d.tasks.filter(t=>t.status==="open").length} open task(s) — ask Claude desktop to <i>"do the storylens queue"</i>, or <a href="#/tasks">answer here</a>.</p>`:""}
      ${d.tasks.length?`<details><summary class="small">${d.tasks.length} Claude task(s) in this job</summary>${d.tasks.map(t=>`<div class="small"><a href="#/tasks/${t.id}">${esc(t.id)}</a> — ${t.status} — ${esc(t.summary)}</div>`).join("")}</details>`:""}</div>
    ${open.map(g=>gateCard(jid, g, d, vcheck)).join("")}
    ${art.includes("recap.mp4")?`<div class="card"><h2>Recap</h2><video controls src="/api/jobs/${jid}/artifacts/recap.mp4"></video>
       <div class="row" style="margin-top:6px"><a class="btn secondary" href="/api/jobs/${jid}/artifacts/recap.mp4" download>Download</a></div></div>`:""}
    ${d.script && !open.length ? `<div class="card"><h2>${esc(d.script.title||"Script")}</h2>${d.script.segments.map((s,i)=>segView(s,i,vcheck[i])).join("")}</div>`:""}
    <div class="card"><h2>Send an instruction to this job</h2><div class="row"><input id="j-msg" style="flex:1" placeholder="e.g. less snark in the ending">
      <button class="secondary" onclick="sendMsg('${jid}')">Send</button></div><p class="small muted">Messages are merged into the following steps' prompts.</p></div>
    <div class="card"><h2>Gates</h2>${d.gates.map(g=>`<div class="small">${g.gate}: ${g.decision?`<b>${g.decision.decision}</b> by ${esc(g.decision.by||"")} ${esc(g.decision.warnings||"")}`:"open"}</div>`).join("")||"<span class='muted small'>none yet</span>"}
     <h2>Artifacts</h2>${art.map(a=>`<a class="pill" href="/api/jobs/${jid}/artifacts/${a}" target="_blank">${a}</a>`).join("")||"<span class='muted small'>none yet</span>"}
     <h2>Events</h2><div class="events">${d.events.slice().reverse().map(e=>`${new Date(e.t*1000).toLocaleTimeString()} ${esc(e.event)} ${esc(e.msg||e.stage||e.task||e.gate||e.error||"")}`).join("<br>")}</div></div>`;
    window.scrollTo(0, keepScroll);
    if (!["running","queued","awaiting_review","waiting_for_claude"].includes(st.status) || open.length) clearInterval(timer);
  };
  await draw(); poll(draw, 2500);
}
function segView(s, i, c){ return `<div class="seg ${c?c.verdict:""}"><span class="pill">${s.type}</span> <span class="small muted">${s.media} L${s.lines[0]}–${s.lines[1]} · ${esc(s.mood||"")}</span>
  <div>${esc(s.text||"(original audio)")}</div>${c&&c.issue?`<div class="small muted">↳ ${esc(c.issue)}${c.fix?" — fix: "+esc(c.fix):""}</div>`:""}</div>`; }
function gateCard(jid, g, d, vcheck){
  const editable = g.gate.startsWith("G2") && d.script;
  return `<div class="card" style="border-color:var(--warn)"><h2>Review needed: ${g.gate}</h2>
   <div class="row">${Object.entries(g.metrics).filter(([k,v])=>typeof v!=="object").map(([k,v])=>`<span class="pill">${k}: ${v}</span>`).join("")}</div>
   ${editable ? d.script.segments.map((s,i)=>`<div class="seg ${vcheck[i]?vcheck[i].verdict:""}"><span class="pill">${s.type}</span>
       <span class="small muted">${s.media} L${s.lines[0]}–${s.lines[1]}</span>
       ${s.type==="hero_clip"?`<div class="small muted">(original audio)</div>`:`<textarea data-seg="${i}">${esc(s.text)}</textarea>`}
       ${vcheck[i]&&vcheck[i].issue?`<div class="small">↳ ${esc(vcheck[i].issue)}${vcheck[i].fix?" — <i>fix:</i> "+esc(vcheck[i].fix):""}</div>`:""}</div>`).join("")
     : `<pre>${esc(g.markdown)}</pre>`}
   ${g.gate.startsWith("G3") && d.artifacts.includes("recap.mp4") ? `<video controls src="/api/jobs/${jid}/artifacts/recap.mp4"></video>`:""}
   <label>Notes (for "revise": what should change)</label><textarea id="g-notes"></textarea>
   <div class="row"><button onclick="decide('${jid}','${g.gate}','approve')">Approve${editable?" (with my edits)":""}</button>
     ${editable?`<button class="secondary" onclick="decide('${jid}','${g.gate}','revise')">Revise with notes</button>`:""}
     <button class="danger" onclick="decide('${jid}','${g.gate}','reject')">Reject</button></div></div>`;
}
async function decide(jid, gate, decision){
  const edits = {}; document.querySelectorAll("textarea[data-seg]").forEach(t=>{ if (t.value !== t.defaultValue) edits[t.dataset.seg] = t.value; });
  await api(`/api/jobs/${jid}/decide`, {method:"POST", body:{gate, decision, notes:$("#g-notes").value, edits}}); jobPage(jid);
}
async function sendMsg(jid){ await api(`/api/jobs/${jid}/send`, {method:"POST", body:{text:$("#j-msg").value}}); $("#j-msg").value=""; }

// ------------------------------------------------------------ Claude tasks
async function rerunJob(jid){ const r = await api(`/api/jobs/${jid}/rerun`, {method:"POST"}); location.hash = `#/job/${r.job}`; }
async function tasksPage(which){
  if (which && which!=="open" && which!=="all") return taskPage(which);
  const d = await api(`/api/tasks?status=${which}`);
  $("#app").innerHTML = `<div class="row"><h1>Claude tasks</h1><span class="spacer"></span>
     <a class="btn secondary" href="#/tasks/${which==="all"?"open":"all"}">${which==="all"?"open only":"show all"}</a></div>
   <div class="card small">All thinking is done by Claude through the workspace folder <code>${esc(d.workspace)}</code>.
     In the Claude desktop app, work in that folder and say <i>"do the storylens queue"</i>: Claude reads <code>CLAUDE.md</code> and
     <code>tasks/QUEUE.md</code>, and writes <code>answer.json</code> for each task. You can also copy a task into any Claude chat and paste the answer here.</div>
   ${d.reviews.length?`<div class="card"><h2>Reviews waiting for you</h2>${d.reviews.map(r=>`<div><a href="#/job/${r.job}">${esc(r.gate)} — ${esc(r.title)}</a></div>`).join("")}</div>`:""}
   <div class="card"><table><tr><th>task</th><th>status</th><th>what</th></tr>${d.tasks.slice().reverse().map(t=>`
     <tr class="click" onclick="location.hash='#/tasks/${t.id}'"><td class="small">${esc(t.id)}</td><td>${t.status}</td><td>${esc(t.summary)}</td></tr>`).join("")}</table>
     ${d.tasks.length?"":`<p class="muted">Nothing ${which==="open"?"open":"yet"}.</p>`}</div>`;
  poll(async()=>{ const n = await api(`/api/tasks?status=${which}`); if (n.tasks.length !== d.tasks.length || n.reviews.length !== d.reviews.length) tasksPage(which); }, 3000);
}
async function taskPage(id){
  const t = await api(`/api/tasks/${id}`);
  $("#app").innerHTML = `<div class="row"><h1>${esc(id)}</h1><span class="pill">${t.meta.status}</span><span class="spacer"></span>
     ${t.meta.job?`<a class="btn secondary" href="#/job/${t.meta.job}">job</a>`:""}<button class="secondary" onclick="navigator.clipboard.writeText(document.getElementById('task-md').textContent)">Copy task</button></div>
   ${t.errors?`<div class="card" style="border-color:var(--warn)"><pre>${esc(t.errors)}</pre></div>`:""}
   ${["open","stale"].includes(t.meta.status)?`<div class="card"><label>Answer (JSON) — normally Claude writes <code>answer.json</code> itself</label><textarea id="t-ans" style="min-height:140px"></textarea>
     <button onclick="answerTask('${id}')">Submit answer</button></div>`:""}
   <div class="card"><pre id="task-md" style="white-space:pre-wrap">${esc(t.task)}</pre></div>
   ${t.answer?`<div class="card"><h2>Answer</h2><pre>${esc(JSON.stringify(t.answer,null,1)).slice(0,60000)}</pre></div>`:""}`;
}
async function answerTask(id){ try { await api(`/api/tasks/${id}/answer`, {method:"POST", body:{answer:$("#t-ans").value}}); setTimeout(()=>taskPage(id), 2500); } catch(e){ alert(e.message) } }

// ------------------------------------------------------------ settings & help
async function settingsPage(){
  const s = STATUS.settings; const ins = await api("/api/instructions");
  const f = (k, label, opts) => `<label>${label}</label>${opts?`<select id="s-${k}">${opts.map(o=>`<option ${o==s[k]?"selected":""}>${o}</option>`).join("")}</select>`:`<input id="s-${k}" value="${esc(s[k])}" style="width:100%">`}`;
  $("#app").innerHTML = `<h1>Settings</h1><div class="card"><div class="kv">
   <span>workspace (share with Claude desktop)</span><span>${esc(STATUS.workspace)}</span><span>answers</span><span>${STATUS.answerer==="mock"?"offline heuristic (demo/tests)":"Claude, through tasks/ in the workspace"}</span>
   <span>ffmpeg</span><span>${STATUS.ffmpeg?"✓":"✗ install ffmpeg to analyze/render video"}</span><span>voices</span><span>kokoro ${STATUS.kokoro?"✓":"✗ (pip install storylens[voice])"} · system ${STATUS.pyttsx3?"✓":"✗"}</span>
   <span>subtitle re-sync (VAD)</span><span>${STATUS.vad?"✓":"✗ (pip install storylens[voice])"}</span></div></div>
   <div class="card">${f("autonomy","Default review mode",["gates","autopilot","auto"])}
   ${f("chunk_lines","Subtitle lines per understanding task (more = fewer, bigger tasks for Claude)")}${f("vision","Look at dialogue-free stretches (one image task per episode)",["off","gaps"])}
   ${f("review","Extra Claude review of every script",["false","true"])}
   ${f("tts","Voice engine",["auto","kokoro","system","none"])}${f("voice","Default voice")}
   <div style="margin-top:10px"><button onclick="saveSettings()">Save</button></div></div>
   <div class="card"><h2>Global instructions</h2><textarea id="g-ins" style="min-height:160px">${esc(ins.text)}</textarea><button class="secondary" onclick="saveGlobalIns()">Save</button></div>`;
}
async function saveSettings(){ const keys=["autonomy","chunk_lines","vision","review","tts","voice"]; const body={};
  keys.forEach(k=>body[k]=$("#s-"+k).value); body.review = body.review==="true"; await api("/api/settings",{method:"POST",body}); route(); }
async function saveGlobalIns(){ await api("/api/instructions",{method:"PUT",body:{text:$("#g-ins").value}}); alert("saved"); }
function helpPage(){
  $("#app").innerHTML = `<h1>How it works</h1><div class="card">
  <p><b>Capture wide once, project narrow many times.</b></p>
  <ol><li><b>Evidence</b> — subtitles (any language's English subs), re-synced to the audio's voice activity; shots; keyframes.</li>
  <li><b>Facts</b> — one pass writes scene cards <i>and</i> a ledger of what <i>every</i> character does, learns, feels, reveals.</li>
  <li><b>Structure</b> — a global pass ranks beats (P0 spine … P3 texture), threads, turning points, setup→payoff edges; every beat records who caused or revealed it.</li>
  <li><b>Lenses</b> — main story, a character's story (villains, side characters), trait compilations ("all the times Leo was a good friend"), storylines, what someone said about a topic, how a speaker builds ideas.</li>
  <li><b>Recap</b> — nested duration selection → script from the exact lines → automatic checks → your review → voice + render.</li></ol>
  <p>There is no API: every thinking step is a task file in <code>tasks/</code> that <b>Claude</b> (the desktop app, working in the workspace folder) answers.
  Claude can also ask for work by writing <code>requests/new/*.json</code>, and reads <code>CATALOG.md</code> to know what exists.
  Read <code>docs/METHODOLOGY.md</code> and <code>docs/AGENTIC.md</code> in the repository for the full details.</p></div>`;
}

// ------------------------------------------------------------ explore: cross-source search, lenses, recaps
async function explorePage(cid){
  const cols = await api("/api/collections"), titles = await api("/api/titles");
  const col = cols.find(c=>c.id===cid) || cols[0];
  const members = col.titles.includes("*") ? titles : titles.filter(t=>col.titles.includes(t.id));
  const speakers = [...new Set((await Promise.all(members.filter(t=>t.understanding_version).map(t=>api(`/api/titles/${t.id}`).then(d=>d.understanding.characters.map(c=>c.name)).catch(()=>[])))).flat())];
  const d = {collection: col.id, understanding: {characters: speakers.map(n=>({name:n})), bible: {threads: []}}};
  const lenses = await api(`/api/collections/${col.id}/lenses`);
  $("#app").innerHTML = `<div class="row"><h1>Explore</h1><span class="muted">search, lenses and recaps across many sources</span><span class="spacer"></span>
    <select id="x-col" onchange="location.hash='#/explore/'+this.value">${cols.map(c=>`<option value="${c.id}" ${c.id===col.id?"selected":""}>${esc(c.name)}</option>`).join("")}</select>
    <button class="secondary" onclick="newCollection()">+ Collection</button></div>
   <p class="small muted">${members.length} titles: ${members.map(t=>esc(t.name)+(t.understanding_version?"":" (not understood)")).join(", ")}</p>
   <div class="card"><h2>Search every source</h2><div class="row"><input id="x-q" style="flex:1" placeholder="e.g. meaning of life">
     <select id="x-sp"><option value="">any speaker</option>${speakers.map(s=>`<option>${esc(s)}</option>`).join("")}</select>
     <select id="x-level">${["title","episode","point","claim","line"].map(l=>`<option ${l==="claim"?"selected":""}>${l}</option>`).join("")}</select>
     <button onclick="xSearch('${col.id}')">Search</button><button class="secondary" onclick="api('/api/library/reindex',{method:'POST'}).then(()=>alert('reindexed'))">Reindex</button></div><div id="x-res"></div></div>
   <div class="card"><h2>Cross-source lens</h2>${lensForm(d)}<div style="margin-top:8px"><button onclick="xLens('${col.id}')">Build lens</button></div>
     <table style="margin-top:10px">${lenses.map(v=>`<tr class="click" onclick="xOpen('${col.id}','${v.id}')"><td>${esc(v.title)}</td><td>${v.kind}</td><td>${v.items} items</td></tr>`).join("")}</table></div>
   <div class="card"><h2>Recap across these sources</h2><p class="small muted">Uses the lens chosen above. "Clips only" makes a no-narrator supercut of the speakers' own words (lower thirds show source and speaker).</p>
     <div class="row"><select id="x-style">${[["clips","Clips only (no narrator)"],["compilation","Compilation"],["short_direct","Short & direct"],["detailed_full","Detailed"],["recap_channel","Recap channel"]].map(([k,v])=>`<option value="${k}">${v}</option>`).join("")}</select>
     <select id="x-dur">${[[60,"1 min"],[180,"3 min"],[300,"5 min"],[600,"10 min"],[1800,"30 min"],[0,"unlimited"]].map(([k,v])=>`<option value="${k}" ${k===180?"selected":""}>${v}</option>`).join("")}</select>
     <select id="x-auto"><option value="">review gates</option><option value="autopilot">autopilot</option><option value="auto">approve everything</option></select>
     <label style="display:inline"><input type="checkbox" id="x-render" checked> render</label><button onclick="xRecap('${col.id}')">Start</button></div></div>`;
  lensKind();
}
async function xSearch(cid){
  const lvl = $("#x-level").value;
  const r = await api(`/api/library/search?collection=${cid}&level=${lvl}&speaker=${encodeURIComponent($("#x-sp").value)}&q=${encodeURIComponent($("#x-q").value)}`);
  $("#x-res").innerHTML = (lvl==="title"||lvl==="episode") ? `<table>${r.map(g=>`<tr class="click" onclick="location.hash='#/title/${g.title}/facts'"><td><b>${esc(g.title_name)}</b> ${g.media||""}</td>
      <td>${g.hits} hits · ${g.claims} claims</td><td class="small">${g.examples.map(esc).join("<br>")}</td></tr>`).join("")}</table>`
    : `<table>${r.map(x=>`<tr><td class="small"><b>${esc(x.title_name)}</b><br>${esc(x.ref)}</td><td class="small">${esc(x.speaker||"")}</td><td>${esc(x.text)}</td>
      <td>${x.level!=="point"?`<button class="secondary" onclick="xLines('${x.title}','${x.media}','${x.ref}')">lines</button>`:""}</td></tr>`).join("")}</table>` || "<p class='muted'>no results</p>";
}
async function xLines(tid, media, ref){ const m = ref.match(/L(\d+)/); const l = m ? +m[1] : 0;
  if (m) return showLines(tid, media, l, l, 0);
  const f = (await api(`/api/titles/${tid}/facts?limit=5000`)).find(x=>x.id===ref); if (f) showLines(tid, f.media, f.lines[0], f.lines[1], f.t0); }
async function xLens(cid){ const r = await api(`/api/collections/${cid}/lens`, {method:"POST", body:{lens:lensValue(), force:true}}); location.hash = `#/job/${r.job}`; }
async function xOpen(cid, vid){ const v = await api(`/api/collections/${cid}/lenses/${vid}`);
  modal(`<h2>${esc(v.title)}</h2><p class="muted">${esc(v.summary)} · duplicates removed: ${v.duplicates_removed||0}</p>
   <table>${v.items.map(i=>`<tr><td>${tier(i.tier)}</td><td class="small"><b>${esc(i.title)}</b><br>${i.media.split("::").pop()} ${ts(i.t0)}</td>
     <td>${i.speaker?`<b>${esc(i.speaker)}${i.speaker_uncertain?"?":""}</b>: `:""}${esc(i.text)}</td><td>${i.salience}</td></tr>`).join("")}</table>`); }
async function xRecap(cid){ const body = {lens:lensValue(), style:$("#x-style").value, duration:+$("#x-dur").value, render:$("#x-render").checked, autonomy:$("#x-auto").value};
  const r = await api(`/api/collections/${cid}/recap`, {method:"POST", body}); location.hash = `#/job/${r.job}`; }
async function newCollection(){ const titles = await api("/api/titles");
  modal(`<h2>New collection</h2><label>Name</label><input id="c-name" style="width:100%"><label>Titles</label>
   ${titles.map(t=>`<div><label style="display:inline"><input type="checkbox" class="c-t" value="${t.id}"> ${esc(t.name)} <span class="muted small">${t.kind}</span></label></div>`).join("")}
   <button onclick="createCollection()">Create</button>`); }
async function createCollection(){ const ids=[...document.querySelectorAll(".c-t:checked")].map(x=>x.value);
  const c = await api("/api/collections",{method:"POST",body:{name:$("#c-name").value, titles:ids}}); closeModal(); location.hash = `#/explore/${c.id}`; }
