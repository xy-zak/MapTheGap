/* The app strip. app.py appends this to out/map.html when it serves it, and the
   setup page loads it for its build step. Nothing in map.js knows it exists: it adds
   one row above .bar and otherwise leaves the page alone. */
(function(){
'use strict';
const api=(path,body)=>fetch(path,body===undefined?{cache:'no-store'}:
  {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(r=>r.json().then(j=>{if(!r.ok)throw new Error(j.error||('HTTP '+r.status));return j;}));
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function dur(s){
  s=Math.max(0,Math.round(s));
  if(s<5)return 'a few seconds';
  if(s<60)return s+'s';
  const m=Math.floor(s/60),r=s%60;
  return m<60?(m+'m '+String(r).padStart(2,'0')+'s'):(Math.floor(m/60)+'h '+(m%60)+'m');
}

/* One strip, in one of two places. mode 'map' shows Zotero's state between builds;
   mode 'setup' shows only a build, and calls onDone when it lands. */
function Strip(host,mode,onDone){
  const row=document.createElement('div');row.className='appstrip';
  const drop=document.createElement('div');drop.className='appdrop';drop.hidden=true;
  host.appendChild(row);host.appendChild(drop);
  let status=null,run=null,dropFor=null,poll=null,watching=false,dismissed=false,stopped=false;

  function showDrop(kind,html){
    if(dropFor===kind){drop.hidden=true;dropFor=null;return;}
    dropFor=kind;drop.innerHTML=html;drop.hidden=false;
  }
  const SRC={local:'Zotero on this computer',web:'zotero.org'};
  function changesHtml(c){
    const sec=(h,l)=>l.length?`<h4>${h} · ${l.length}</h4><ul>${l.slice(0,60).map(i=>
      `<li>${esc(i.title||i.key)}</li>`).join('')}${l.length>60?`<li>… ${l.length-60} more</li>`:''}</ul>`:'';
    return sec('new',c.added)+sec('edited',c.edited)+sec('removed',c.removed)+
      (c.source==='local'
        ?`<div class="note">counted from Zotero on this computer at ${esc(c.checked)}, edits not yet synced included</div>`
        :`<div class="note">counted from zotero.org at ${esc(c.checked)} - an edit made in the Zotero app counts once Zotero has synced it</div>`);
  }
  /* The plain-words answer to "where is this coming from", behind the source item. */
  function srcHtml(s){
    const r=s.reading||{},m=s.map;
    let now;
    if(r.source==='local')now='<p><b>Zotero on this computer.</b> Zotero is open and lets other applications read it, '+
      'so the map reads it directly: an edit counts here within a minute, before Zotero has synced it, '+
      'and <i>update map</i> reads from here too.</p>';
    else if(!s.zotero_open)now='<p><b>zotero.org.</b> Zotero isn\'t open on this computer, so the map reads the copy '+
      'of your library that Zotero syncs online. Edits made on zotero.org, on another computer or by the Claude skills count straight away; '+
      'an edit made in the Zotero app counts once Zotero has synced it. Open Zotero to read it directly.</p>';
    else now=`<p><b>zotero.org,</b> although Zotero is open: ${esc(r.why)}. Until that is fixed, the map reads the copy `+
      'Zotero syncs online, and an edit made in the Zotero app counts once Zotero has synced it.</p>';
    return '<h4>reading your library from</h4>'+now+
      (m?`<h4>this map</h4><p>built ${esc(m.built)} from ${SRC[m.source]||esc(m.source)}. `+
        'Changes are counted against it from whichever of the two can be read, item by item, so switching between them loses nothing.</p>':'');
  }
  function logHtml(text){return `<pre>${esc(text||'(nothing yet)')}</pre>`;}

  function idle(){
    const s=status||{};
    const c=s.changes||{};
    const r=s.reading||{};
    const where=SRC[r.source]||'zotero.org';
    const z=r.source==='local'
      ?'<span class="dot on"></span>reading zotero app'
      :`<span class="dot ${s.zotero_open?'warn':'web'}"></span>reading zotero.org`;
    const why=r.source==='local'?'Zotero is open: the map reads it directly, unsynced edits included'
      :s.zotero_open?('Zotero is open, but '+r.why):'Zotero is closed: the map reads your synced library on zotero.org';
    let ch;
    if(c.state==='ok'&&c.count>0){
      const parts=[['new',c.added],['edited',c.edited],['removed',c.removed]]
        .filter(p=>p[1].length).map(p=>p[1].length+' '+p[0]);
      ch=`<span class="n">${c.count}</span> item${c.count===1?'':'s'} changed since this map was built`+
         ` <span class="dim">(${parts.join(' · ')})</span><button class="lnk" data-a="show">[show]</button>`;
    }else if(c.state==='ok')ch=`<span class="ok">map is up to date with ${SRC[c.source]}</span>`+
      (c.source==='web'?' <span class="dim">as of its last sync</span>':'');
    else if(c.state==='untracked')ch='update the map once to start tracking changes';
    else if(c.state==='error')ch=`<span class="err">couldn't check ${where} for changes: ${esc(c.error)}</span>`;
    else ch=`checking ${where} for changes…`;
    const hot=c.state==='ok'&&c.count>0;
    row.innerHTML=`<span class="it src${r.source!=='local'&&s.zotero_open?' warn':''}" title="${esc(why)}">${z}<button class="lnk" data-a="src">[?]</button></span>`+
      `<span class="it grow">${ch}</span>`+
      `<a class="bc" href="/setup" title="Zotero key and contact address">settings</a>`+
      `<button class="bc" data-a="quit" title="stop the app; the map on this page stays readable">quit</button>`+
      `<button class="bc${hot?' hot':''}" data-a="update" title="rebuild the map, reading the library from ${esc(where)}">[↻] update map</button>`;
    if(dropFor==='changes'){
      if(c.state==='ok'&&c.count)drop.innerHTML=changesHtml(c);else{drop.hidden=true;dropFor=null;}
    }else if(dropFor==='src')drop.innerHTML=srcHtml(s);
  }

  function running(r){
    const ind=r.total==null&&r.stage!=='render';
    const pct=Math.min(100,Math.round((r.fraction||0)*100));
    let eta;
    if(r.state==='running')eta=r.elapsed<1.5?'estimating…':('~'+dur(r.eta)+' left');
    const cnt=r.total!=null?`<span class="it cnt">${r.done||0}/${r.total}</span>`:'';
    if(r.state==='running'){
      row.innerHTML=`<span class="it stg">${esc(r.label)}</span>${cnt}`+
        `<span class="pbar${ind?' ind':''}"><i style="width:${pct}%"></i></span>`+
        `<span class="it eta">${eta}</span>`+
        `<button class="bc" data-a="log">[log]</button><button class="bc" data-a="cancel">[cancel]</button>`;
    }else if(r.state==='failed'){
      row.innerHTML=`<span class="it grow"><span class="err">update failed: ${esc(r.error||'see the log')}</span></span>`+
        `<button class="bc" data-a="log">[log]</button><button class="bc" data-a="dismiss">[dismiss]</button>`+
        `<button class="bc" data-a="update">[↻] retry</button>`;
    }else if(r.state==='cancelled'){
      row.innerHTML=`<span class="it grow">update cancelled - the map was left as it was</span>`+
        `<button class="bc" data-a="dismiss">[dismiss]</button><button class="bc" data-a="update">[↻] update map</button>`;
    }else if(r.state==='done'){
      row.innerHTML=`<span class="it grow"><span class="ok">map updated in ${dur(r.elapsed)}</span> - loading it…</span>`;
    }
  }

  function draw(){
    if(run&&(run.state==='running'||(!dismissed&&(run.state==='failed'||run.state==='cancelled'))))running(run);
    else if(mode==='map')idle();
    else row.innerHTML='';
  }

  /* fast while a build runs, slow otherwise, not at all in a background tab */
  function schedule(ms){clearTimeout(poll);poll=setTimeout(tick,ms);}
  function tick(){
    if(document.hidden||stopped)return;
    if(run&&run.state==='running'){
      api('/api/update'+(dropFor==='log'?'?log=1':'')).then(r=>{
        run=r;
        if(dropFor==='log')drop.innerHTML=logHtml(r.log);
        if(r.state==='done'&&watching){running(r);setTimeout(onDone,700);return;}
        draw();schedule(r.state==='running'?500:10000);
      }).catch(()=>schedule(2000));
    }else if(mode==='map'){
      api('/api/status').then(s=>{
        status=s;
        if(s.run.state==='running'){run=s.run;watching=true;dismissed=false;draw();schedule(500);return;}
        draw();schedule(10000);
      }).catch(()=>{row.innerHTML='<span class="it grow"><span class="err">lost the app server - is app.py still running?</span></span>';schedule(5000);});
    }
  }
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)tick();});

  row.addEventListener('click',e=>{
    const a=e.target.closest('[data-a]');if(!a)return;
    const act=a.dataset.a;
    if(act==='show')showDrop('changes',changesHtml(status.changes));
    else if(act==='src')showDrop('src',srcHtml(status||{}));
    else if(act==='log')api('/api/update?log=1').then(r=>showDrop('log',logHtml(r.log)));
    else if(act==='dismiss'){dismissed=true;drop.hidden=true;dropFor=null;draw();}
    else if(act==='cancel'){a.disabled=true;api('/api/update/cancel',{}).then(r=>{run=r;draw();});}
    else if(act==='update')start();
    else if(act==='quit')quit().then(()=>{
      stopped=true;clearTimeout(poll);drop.hidden=true;
      row.innerHTML='<span class="it grow">MapTheGap has stopped. The map stays readable here; '+
        'to update it again, start MapTheGap from its launcher.</span>';
    });
  });

  function start(){
    drop.hidden=true;dropFor=null;dismissed=false;watching=true;
    run={state:'running',label:'starting',elapsed:0,eta:0,fraction:0,total:null};draw();
    api('/api/update',{}).then(r=>{run=r;draw();schedule(400);})
      .catch(e=>{run={state:'failed',error:e.message};draw();});
  }
  tick();
  return {start};
}

/* Stop the server. Resolves either way: once it is down, there is nothing to answer. */
function quit(){return api('/api/quit',{}).catch(()=>{});}

window.MTG={Strip,api,esc,quit};

/* On the map, mount above the title bar: the app's controls sit outside the map they
   act on. A setup page mounts its own. */
const bar=document.querySelector('.wrap > .bar');
if(bar&&!document.body.dataset.page){
  const host=document.createElement('div');
  bar.before(host);
  Strip(host,'map',()=>location.reload());   /* the #timeline / #clustering hash survives */
}
})();
