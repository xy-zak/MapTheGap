const D=JSON.parse(document.getElementById('data').textContent);
const ROLES=['foundational','additional','contrarian','satellite'];
const RC={foundational:'var(--found)',additional:'var(--add)',contrarian:'var(--contra)',satellite:'var(--sat)'};
const HL={out:'#e6604f',inc:'#6fdc8c',voc:'#FAFCFB'};   /* none of these is a role colour */
const RAW={foundational:'#87a9b0',additional:'#b19be2',contrarian:'#c38b7b',satellite:'#6B5E73'};
const byKey={};D.nodes.forEach(n=>byKey[n.key]=n);
const on=Object.fromEntries(ROLES.map(r=>[r,true]));
let q='';
/* one predicate drives nodes and both edge layers, so a hidden endpoint can never
   leave a dangling line */
const hay={};
D.nodes.forEach(n=>{hay[n.key]=[n.title,n.creators.join(' '),n.year,n.date,n.doi||'',
  n.itemType,n.tags.join(' '),n.abstract].join(' · ').toLowerCase();});
const match=n=>!q||hay[n.key].includes(q);
let tmax=D.nodes.length;                 /* replay cutoff: show ranks 1..tmax */
const vis=n=>on[n.role]&&match(n)&&n.rank<=tmax;
const NS='http://www.w3.org/2000/svg';
const el=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const svg=document.getElementById('svg');
/* Both views are laid out at D.w and drawn at the width the page gives them, CW.
   The timeline stretches only its year scale, X(): nodes move apart and never
   together, so lanes packed collision-free at D.w stay that way, and text and circles
   keep their size. Clustering fits its layout to CW instead (FR.w). Below D.w nothing
   shrinks - the drawing keeps D.w and the scroller scrolls, as it always has. */
const SCR=document.querySelector('.scroller');
const TX0=D.ticks[0].x, TX1=D.ticks[D.ticks.length-1].x;
let CW=D.w, XK=1;
const X=x=>TX0+(x-TX0)*XK;
function measure(){
  CW=Math.max(D.w,Math.floor(SCR?SCR.clientWidth:0));
  XK=(CW-(D.w-TX1)-TX0)/(TX1-TX0);
}
measure();
svg.setAttribute('viewBox',`0 0 ${CW} ${D.h}`);
svg.setAttribute('width',CW);svg.setAttribute('height',D.h);

const L=D.layout;
const gB=el('g',{});svg.appendChild(gB);          /* band grounds + labels */
const gG=el('g',{});svg.appendChild(gG);          /* decade gridlines */

/* Which facet bands the map. Each facet keeps its own collapsed state, so switching
   away and back does not throw away what the reader opened. Only gB is rebuilt —
   the node, edge and vocabulary layers are facet-independent and are never touched,
   which is what keeps a selection and a filter alive across a switch. */
let BAND=D.band_default, SEC=[], secOf={}, collapsed={};
const collapsedBy={};
Object.keys(D.bands).forEach(f=>{
  collapsedBy[f]={};
  D.bands[f].sections.forEach(s=>collapsedBy[f][s.name]=true);  /* overview, not detail */
});
function buildBands(){
  SEC=D.bands[BAND].sections;
  collapsed=collapsedBy[BAND];
  secOf={};SEC.forEach(s=>secOf[s.name]=s);
  while(gB.firstChild)gB.removeChild(gB.firstChild);
  SEC.forEach((s,i)=>{
    s._bg=el('rect',{x:0,width:D.w,fill:'#161314',opacity:i%2===0?.75:0});
    s._lbl=el('text',{x:6,class:'seclbl'});
    s._note=el('text',{x:6,class:'secnote'});
    s._hit=el('rect',{x:0,width:D.w,height:22,class:'sechit',fill:'transparent'});
    s._hit.addEventListener('click',()=>{collapsed[s.name]=!collapsed[s.name];relayout();});
    s._lbl.addEventListener('click',()=>{collapsed[s.name]=!collapsed[s.name];relayout();});
    gB.appendChild(s._bg);gB.appendChild(s._lbl);gB.appendChild(s._note);gB.appendChild(s._hit);
  });
  const A=D.bands[BAND].assign;
  D.nodes.forEach(n=>{const a=A[n.key];n.section=a[0];n.lane=a[1];});
}
D.ticks.forEach(t=>{
  const brk=Math.abs(t.x-D.breakx)<0.5;
  t._line=el('line',{x1:t.x,y1:D.axis_top+4,x2:t.x,stroke:brk?'#584e51':'#2b2529',
    'stroke-width':brk?1.6:1,opacity:brk?.9:.85});
  gG.appendChild(t._line);
  t._lab=el('text',{x:t.x,y:D.axis_top-4,class:'tick'+(t.major?' major':''),'text-anchor':'middle'});
  t._lab.textContent=t.year;gG.appendChild(t._lab);
});

/* vocabulary layer sits beneath citations: dashed so it never reads as "A cited B" */
const gT=el('g',{});svg.appendChild(gT);
D.tag_edges.forEach(e=>{
  const s=byKey[e.a],t=byKey[e.b];if(!s||!t)return;
  const p=el('path',{fill:'none',stroke:'#6B5E73','stroke-width':0.8,'stroke-dasharray':'2 3',opacity:.55});
  p.dataset.a=e.a;p.dataset.b=e.b;p.dataset.shared=e.shared.join(' | ');
  gT.appendChild(p);
});

const gE=el('g',{});svg.appendChild(gE);
D.edges.forEach(e=>{
  const s=byKey[e.source],t=byKey[e.target];if(!s||!t)return;
  const p=el('path',{fill:'none',stroke:'#b0a3a0','stroke-width':0.8,opacity:.8});
  p.dataset.s=e.source;p.dataset.t=e.target;gE.appendChild(p);
});

const gN=el('g',{});svg.appendChild(gN);
D.nodes.forEach(n=>{
  const g=el('g',{class:'node',tabindex:0,role:'button'});
  g.dataset.k=n.key;g.dataset.role=n.role;
  n._c=el('circle',{cx:n.x,r:n.r,fill:RAW[n.role],'fill-opacity':.75,
    stroke:RAW[n.role],'stroke-width':1});
  /* collapsed form: a thin horizontal bar, width still carrying citation count */
  const bw=Math.max(3,n.r*1.8);
  n._b=el('rect',{x:n.x-bw/2,width:bw,height:6,fill:RAW[n.role],'fill-opacity':.85});
  const ttl=el('title',{});ttl.textContent=`${n.creators[0]||'?'} ${n.year||''} — ${n.title}`;
  g.appendChild(n._c);g.appendChild(n._b);g.appendChild(ttl);
  g.addEventListener('click',()=>sel(n.key));
  g.addEventListener('keydown',ev=>{if(ev.key==='Enter'||ev.key===' '){ev.preventDefault();sel(n.key);}});
  gN.appendChild(g);
});

/* ---- circle size ----
   Size normally carries the global citation count, which is what makes the famous
   works findable at a glance — and also what makes a book nobody has indexed look
   trivial. Uniform drops it: every source becomes the same dot, so position and
   colour are all that is left to read. Both views share the switch and the state.

   This is a DRAWING change only. No position moves and the simulation is not
   re-run, so the layout stays the one that was settled and measured; the physics
   keeps using its own radii either way.

   10 is the median radius the map already draws, and it is measured to be safe
   rather than guessed: the closest pair of nodes is 21.7px apart in the timeline
   (the same to within 0.1px across all three banding facets) and 38.6px in
   clustering, so a uniform 10 introduces no overlap in any view. Anything above
   ~10.8 starts colliding in the timeline, which is the binding constraint. */
let UNIFORM=false;
const URAD=10;
const rad=n=>UNIFORM?URAD:n.r;
const barW=n=>Math.max(3,rad(n)*1.8);
function applySizes(){
  D.nodes.forEach(n=>{
    n._c.setAttribute('r',rad(n));
    const w=barW(n);
    n._b.setAttribute('width',w);
    if(n._x!=null)n._b.setAttribute('x',n._x-w/2);
  });
  /* the legend has to agree with what the circles are actually showing */
  const sz=document.getElementById('szw');
  if(sz)sz.textContent=UNIFORM?'are all one size':'size is the global citation count';
}
/* The size switch belongs to both views, so rather than a row of its own it lives in
   whichever mode's control row is showing — beside the banding in the timeline,
   beside colour in clustering. Moved, not duplicated: one element, one state, and
   no pair of labels that can drift apart. Each row keeps its switches in one centred
   group, and the size switch joins the end of it. */
function placeSize(){
  document.getElementById(MODE==='cluster'?'clsw':'tlsw').appendChild(document.getElementById('sizesw'));
}
/* A two-way switch drawn like the view switch: pressing the side that is not lit
   lights it and reports its value. Its own class, .tsw - every .msw is bound to the
   view switch. */
function segSwitch(id,pick){
  const g=document.getElementById(id),bs=[...g.querySelectorAll('.tsw')];
  bs.forEach(b=>b.addEventListener('click',()=>{
    if(b.getAttribute('aria-pressed')==='true')return;
    bs.forEach(o=>o.setAttribute('aria-pressed',String(o===b)));
    pick(b.dataset.v);}));
}
segSwitch('sizesw',v=>{UNIFORM=v==='uniform';applySizes();});

/* vertical layout lives here, not in the payload, because collapsing a band moves
   every band below it */
function relayout(){
  if(MODE==='cluster')return;          /* clustering owns the geometry there */
  let y=L.top;
  SEC.forEach(s=>{
    const open=!collapsed[s.name];
    const h=open?s.lanes*L.lane_h:L.collapsed_h;
    const top=y+L.label_h;
    s._top=top;s._h=h;s._open=open;
    s._bg.setAttribute('y',top-6);s._bg.setAttribute('height',h+12);s._bg.setAttribute('width',CW);
    s._hit.setAttribute('width',CW);
    s._lbl.setAttribute('y',y+16);
    s._lbl.textContent=(open?'▾ ':'▸ ')+s.name;
    s._note.setAttribute('y',y+16);
    s._note.setAttribute('x',6+(s.name.length+2)*8.4+12);
    s._note.textContent=(open?'':s.count+' sources collapsed · click to expand');
    s._hit.setAttribute('y',y+2);
    y=top+h+L.gap;
  });
  const shut=SEC.filter(s=>collapsed[s.name]).length;
  const bcn=document.getElementById('bcn');
  if(bcn)bcn.textContent=shut===0?'all '+SEC.length+' sections open'
        :(shut===SEC.length?'all '+SEC.length+' sections collapsed':(SEC.length-shut)+' of '+SEC.length+' open');
  const H=y+10;
  svg.setAttribute('viewBox',`0 0 ${CW} ${H}`);svg.setAttribute('width',CW);svg.setAttribute('height',H);
  D.ticks.forEach(t=>{const x=X(t.x);t._line.setAttribute('x1',x);t._line.setAttribute('x2',x);
    t._line.setAttribute('y2',H-6);t._lab.setAttribute('x',x);});
  D.nodes.forEach(n=>{
    const s=secOf[n.section];
    /* _x is the position the link layers read. Here it is the year scale; in
       clustering mode the simulation overwrites it, which is the whole of the
       difference between the two views. */
    n._x=X(n.x);
    n._y = s._open ? s._top+(n.lane+0.5)*L.lane_h : s._top+L.collapsed_h/2;
    n._c.setAttribute('cx',n._x);
    n._c.setAttribute('cy',n._y);n._c.setAttribute('display',s._open?'':'none');
    n._b.setAttribute('x',n._x-barW(n)/2);
    n._b.setAttribute('y',n._y-3);n._b.setAttribute('display',s._open?'none':'');
  });
  paths();
}

/* Both modes draw the same two link layers from the same DOM paths, so only the
   geometry is per-mode. The timeline bows its edges to separate ones that would
   otherwise overlap along a lane; clustering draws straight, trimmed to the
   circle edge so an arrowhead has somewhere to sit. */
function paths(){
  const tl=MODE!=='cluster';
  [[gE,'s','t'],[gT,'a','b']].forEach(([layer,ka,kb])=>{
    layer.querySelectorAll('path').forEach(p=>{
      const a=byKey[p.dataset[ka]],b=byKey[p.dataset[kb]];
      if(!a||!b)return;
      if(tl){
        const dy=Math.abs(a._y-b._y),dx=Math.abs(a._x-b._x);
        const mx=(a._x+b._x)/2,my=(a._y+b._y)/2-(dy>60?0:Math.min(40,dx*0.16+12));
        p.setAttribute('d',`M${a._x},${a._y} Q${mx},${my} ${b._x},${b._y}`);
      }else{
        /* centre to centre: the nodes are painted after the links and cover the
           ends, so a trimmed line only added a gap without adding information */
        p.setAttribute('d','M'+a._x.toFixed(1)+','+a._y.toFixed(1)
          +' L'+b._x.toFixed(1)+','+b._y.toFixed(1));
      }
    });
  });
}

/* ---- role visibility toggles ---- */
const counts={};ROLES.forEach(r=>counts[r]=D.nodes.filter(n=>n.role===r).length);
const F=document.getElementById('filters');
ROLES.forEach(r=>{
  const b=document.createElement('button');
  b.className='fl';b.id='fl-'+r;b.style.setProperty('--c',RAW[r]);
  b.setAttribute('aria-pressed','true');
  b.innerHTML=`<span class="box">[x]</span>${r}<span class="n">${counts[r]}</span>`;
  b.addEventListener('click',()=>{on[r]=!on[r];
    b.setAttribute('aria-pressed',on[r]?'true':'false');
    b.querySelector('.box').textContent=on[r]?'[x]':'[ ]';
    apply();});
  F.appendChild(b);
});
/* ---- banding facet ---- */
const BF=document.getElementById('bandfacet');
Object.keys(D.bands).forEach(f=>{
  const b=document.createElement('button');
  b.className='tsw';b.dataset.f=f;
  b.innerHTML=esc(f)+' <span class="tn">'+D.bands[f].sections.length+'</span>';
  b.title=D.bands[f].sections.length+' bands';
  b.setAttribute('aria-pressed',f===BAND?'true':'false');
  b.addEventListener('click',()=>{
    if(BAND===f)return;
    BAND=f;
    BF.querySelectorAll('.tsw').forEach(x=>x.setAttribute('aria-pressed',x.dataset.f===f?'true':'false'));
    buildBands();relayout();apply();
  });
  BF.appendChild(b);
});

document.getElementById('thr').textContent=`· foundational = cited ≥ ${D.meta.threshold.foundational_in_degree}× within this library`;

function apply(){
  let vn=0;                       /* counter, NOT the vis() predicate */
  gN.querySelectorAll('.node').forEach(g=>{
    const show=vis(byKey[g.dataset.k]);
    g.classList.toggle('hidden',!show);
    if(show)vn++;
  });
  let ve=0;
  gE.querySelectorAll('path').forEach(p=>{
    const show=vis(byKey[p.dataset.s])&&vis(byKey[p.dataset.t]);
    p.classList.toggle('hidden',!show);
    if(show)ve++;
  });
  let vt=0,vd=0;
  gT.querySelectorAll('path').forEach(p=>{
    const live=vis(byKey[p.dataset.a])&&vis(byKey[p.dataset.b]);
    if(live)vt++;
    p.classList.toggle('hidden',!live);
    if(live)vd++;
  });
  if(MODE==='cluster')hulls();
  document.getElementById('status').innerHTML=
    (MODE==='cluster'
      ? `<span>SHOWING ${vn}/${D.nodes.length} SOURCES &nbsp;·&nbsp; ${ve}/${D.edges.length} CITATIONS &nbsp;·&nbsp; ${vd}/${D.tag_edges.length} VOCABULARY DRAWN</span>`
      : `<span>SHOWING ${vn}/${D.nodes.length} SOURCES &nbsp;·&nbsp; ${ve}/${D.edges.length} CITATIONS &nbsp;·&nbsp; ${vt}/${D.tag_edges.length} VOCABULARY</span>`)+
    `<span>${tmax<D.nodes.length?'REPLAY '+tmax+'/'+D.nodes.length:(q?'FILTER: /'+q.toUpperCase():(ROLES.filter(r=>!on[r]).length?'HIDDEN: '+ROLES.filter(r=>!on[r]).join(', ').toUpperCase():'ALL VISIBLE'))}</span>`;
}

/* The selection lives in one variable so that clearing it is a no-op when nothing
   is selected, and so the placeholder is restored from the same string the page
   ships with rather than a second copy of it. */
const PLACEHOLDER='<p class="ph"><span class="bl">&nbsp;</span> select a node &mdash; abstract, tags and citation links appear here</p>';
let selected=null;

function deselect(){
  if(!selected)return;
  selected=null;
  gE.querySelectorAll('path').forEach(p=>{
    p.setAttribute('opacity',.8);p.setAttribute('stroke-width',0.8);p.setAttribute('stroke','#b0a3a0');
  });
  styleVoc();
  document.getElementById('panel').innerHTML=PLACEHOLDER;
  apply();
}

/* Walk up to the svg looking for a class, rather than Element.closest, because the
   ancestor chain here is SVG and the node itself is the <g> while the click target
   is the circle or bar inside it. */
function within(el,cls){
  for(let e=el;e&&e!==svg;e=e.parentNode) if(e.classList&&e.classList.contains(cls))return true;
  return false;
}

/* Clicking the canvas anywhere that is not a node clears the selection. Band labels
   and their hit strips are excluded: collapsing a band should not throw away what
   the reader had selected. */
svg.addEventListener('click',ev=>{
  const t=ev.target;
  if(within(t,'node')||within(t,'seclbl')||within(t,'sechit'))return;
  deselect();
});

function sel(key){
  const n=byKey[key];if(!n)return;
  selected=key;
  apply();                     /* may need to surface this node's vocabulary */
  gE.querySelectorAll('path').forEach(p=>{
    const hot=p.dataset.s===key||p.dataset.t===key;
    p.setAttribute('opacity',hot?1:.12);
    p.setAttribute('stroke-width',hot?1.9:0.8);
    /* Direction is carried by colour alone — red for what this cites, green for
       what cites it — in both modes. Arrowheads on top of that were redundant. */
    p.setAttribute('stroke',hot?(p.dataset.s===key?HL.out:HL.inc):'#b0a3a0');
  });
  gT.querySelectorAll('path').forEach(p=>{
    const hot=p.dataset.a===key||p.dataset.b===key;
    p.setAttribute('opacity',hot?.95:.1);
    p.setAttribute('stroke',hot?HL.voc:'#6B5E73');
    p.setAttribute('stroke-width',hot?1.9:0.8);
  });
  const kin=D.tag_edges.filter(e=>e.a===key||e.b===key)
    .map(e=>({m:byKey[e.a===key?e.b:e.a],j:e.j,sh:e.shared})).filter(z=>z.m&&vis(z.m));
  const out=D.edges.filter(e=>e.source===key).map(e=>byKey[e.target]).filter(m=>m&&vis(m));
  const inn=D.edges.filter(e=>e.target===key).map(e=>byKey[e.source]).filter(m=>m&&vis(m));
  const lab=m=>`${m.creators[0]||'?'} ${m.year||''}  ${m.title.slice(0,46)}`;
  document.getElementById('panel').innerHTML=`
   <h2>${esc(n.title)}</h2>
   <p class="cite">${esc(n.creators.join(', '))||'—'} · ${esc(n.date||'n.d.')} · ${n.itemType}${n.doi?' · '+esc(n.doi):''}<br>
     ${n.cited_by==null?'citations unknown':n.cited_by+' global citations'} · cited ${n.in_degree}× here · cites ${n.out_degree} here</p>
   <div class="chips">
     <span class="chip role" style="color:${RAW[n.role]}">role: ${n.role}${n.role_source==='judged'?' *judged':''}</span>
     ${n.tags.map(t=>`<span class="chip">${esc(t)}</span>`).join('')}
   </div>
   ${n.unresolved?`<p class="cite" style="color:${RAW.contrarian}">unresolved: ${esc(n.unresolved)}</p>`:''}
   <p class="ab">${n.abstract?esc(n.abstract):'no abstract recorded'}</p>
   <div class="links links3">
     <div><h3>SHARED VOCABULARY [${kin.length}]</h3><ul>${kin.sort((x,y)=>y.j-x.j).map(z=>`<li data-k="${z.m.key}" title="${esc(z.sh.join(' | '))}">${esc(lab(z.m))}</li>`).join('')||'<li style="cursor:default">&mdash;</li>'}</ul></div>
     <div><h3>CITES, IN LIBRARY [${out.length}]</h3><ul>${out.map(m=>`<li data-k="${m.key}">${esc(lab(m))}</li>`).join('')||'<li style="cursor:default">—</li>'}</ul></div>
     <div><h3>CITED BY, IN LIBRARY [${inn.length}]</h3><ul>${inn.map(m=>`<li data-k="${m.key}">${esc(lab(m))}</li>`).join('')||'<li style="cursor:default">—</li>'}</ul></div>
   </div>`;
  document.getElementById('panel').querySelectorAll('li[data-k]').forEach(li=>li.addEventListener('click',()=>sel(li.dataset.k)));
}
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}
const QI=document.getElementById('q'),QC=document.getElementById('qc');
QI.addEventListener('input',()=>{q=QI.value.trim().toLowerCase();QC.hidden=!q;apply();});
QI.addEventListener('keydown',e=>{if(e.key==='Escape'){QI.value='';q='';QC.hidden=true;apply();}});
QC.addEventListener('click',()=>{QI.value='';q='';QC.hidden=true;apply();QI.focus();});
/* Escape clears the selection, except while the search box has focus, where it
   already clears the query instead. */
document.addEventListener('keydown',ev=>{
  if(ev.key==='Escape'&&ev.target!==QI)deselect();
  /* "/" focuses the search, as the box's key hint says, unless something is being typed */
  if(ev.key==='/'&&!ev.ctrlKey&&!ev.metaKey&&!/^(INPUT|TEXTAREA|SELECT)$/.test(ev.target.tagName)){
    ev.preventDefault();QI.focus();}
});
/* The key is folded away by default, so the map starts nearer the top. Whether a
   reader keeps it open is remembered in this browser only, and storage that throws
   (a private window, a sandboxed preview) just means it starts folded. */
(()=>{const kb=document.getElementById('keyb'),lg=document.getElementById('legend');
  const show=open=>{lg.hidden=!open;kb.setAttribute('aria-expanded',String(open));
    kb.textContent=(open?'[−]':'[+]')+' key';};
  let open=false;try{open=localStorage.getItem('mtg.key')==='open';}catch(e){}
  show(open);
  kb.addEventListener('click',()=>{const o=lg.hidden;show(o);
    try{localStorage.setItem('mtg.key',o?'open':'closed');}catch(e){}});})();
q=QI.value.trim().toLowerCase();QC.hidden=!q;   /* value survives a republish */
document.getElementById('expall').addEventListener('click',()=>{SEC.forEach(s=>collapsed[s.name]=false);relayout();});
document.getElementById('colall').addEventListener('click',()=>{SEC.forEach(s=>collapsed[s.name]=true);relayout();});
const SC=document.getElementById('scrub'),SCN=document.getElementById('scn'),PLAY=document.getElementById('play');
const byRank={};D.nodes.forEach(n=>byRank[n.rank]=n);
SC.max=D.nodes.length;
function scrubTo(v,fromInput){
  tmax=Math.max(1,Math.min(D.nodes.length,v));
  if(!fromInput)SC.value=tmax;
  const n=byRank[tmax];
  SCN.textContent=String(tmax).padStart(String(D.nodes.length).length,'0')+'/'+D.nodes.length+(n?'  ·  '+(n.date_added||'').slice(0,10)+'  '+(n.creators[0]||'?')+' '+(n.year||''):'');
  apply();
}
SC.addEventListener('input',()=>scrubTo(Number(SC.value),true));
let timer=null;
function stop(){clearInterval(timer);timer=null;PLAY.innerHTML='[▶] play';}
PLAY.addEventListener('click',()=>{
  if(timer){stop();return;}
  if(tmax>=D.nodes.length)scrubTo(1);
  PLAY.innerHTML='[■] stop';
  timer=setInterval(()=>{
    if(tmax>=D.nodes.length){stop();return;}
    scrubTo(tmax+1);
  },180);
});
SC.value=D.nodes.length;
__FJS__

/* ======================== export the graph as an SVG ========================
   What comes out is the drawing as it stands: the current mode, the current
   filters, the replay cutoff, which bands are collapsed, and the selected
   source with its red/green/black links and its named hulls. The clone is taken
   from the live DOM, so there is no second copy of the geometry to drift.

   Two deliberate differences from the page, and only two:

     - NO BACKGROUND. The page's near-black comes from body and .scroller, never
       from the svg, so the export simply omits both and inherits whatever it is
       dropped onto.
     - The NEUTRAL scale is inverted, so what the page draws in white it draws in
       black: the text, the rules, the band stripes, the plain citation grey and
       the white a selected source's vocabulary links turn.

   Every SEMANTIC colour is left exactly as it is. The role palette, the year
   ramp and the red/green direction pair were each measured, and a figure whose
   colours disagree with the map it was read off is worse than a dark figure.
   Only the neutrals move; if one ever needs to, it moves in EXP_INK below and
   nowhere else. */
const EXP_INK={
  '#fafcfb':'#000000',   /* --fg      selected vocabulary link: the white -> black */
  '#cfd3cd':'#2f2c2b',   /* --dim     decade ticks */
  '#584e51':'#6f6764',   /* --dimmer  minor ticks, band notes, the era-break rule */
  '#2b2529':'#d7d2cf',   /* --line    decade gridlines, gutter rule */
  '#161314':'#ebe8e6',   /* alternating band ground */
  '#121011':'#ffffff',   /* --panel   hull label box */
  '#b59790':'#8a655c',   /* --accent  hulls, band + hull labels, leader lines */
  '#b0a3a0':'#6b5f5c'    /* unselected citation links */
};
/* The page styles these by class from its stylesheet, which a standalone file
   does not get, so the export carries its own copy with the values already
   resolved. Same rules, light neutrals. */
const EXP_CSS=`
text{font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.seclbl{font-size:11px;letter-spacing:.17em;fill:#8a655c;font-weight:700}
.secnote{font-size:10.5px;fill:#6f6764;letter-spacing:.04em}
.tick{font-size:10px;fill:#6f6764}
.tick.major{fill:#2f2c2b}
__FXCSS__`;

/* A figure gets a key, because there is no legend above it and no panel beside it.
   It states what the CIRCLES are actually coloured by — role normally, the year ramp
   when colour-by-year is on, since a role key over year-coloured circles would simply
   be wrong — and it lists only the values present in the drawing, so a filtered-out
   role has nothing to explain.

   Built in the live svg so every label can be MEASURED with getBBox rather than
   guessed from glyph widths, exactly as the hull labels are; it is cloned with the
   rest and then taken back out. Font is set by attribute, not class, so the width
   measured here is the width the export renders. Nothing repaints in between. */
const KEYH=32;
function buildKey(){
  const g=el('g',{id:'exkey'});
  svg.appendChild(g);
  const yr=(COLOR==='year'&&MODE==='cluster');
  let items;
  if(yr){
    const used=new Set(D.nodes.filter(vis).map(n=>yearBin(n.year)));
    items=FR.year_bins.map((b,i)=>({c:FR.year_ramp[i],t:b.label,i:i})).filter(z=>used.has(z.i));
    if(used.has(-1))items.push({c:'#6B5E73',t:'no year'});
  }else{
    items=ROLES.filter(r=>D.nodes.some(n=>n.role===r&&vis(n))).map(r=>({c:RAW[r],t:r}));
  }
  let x=6;
  items.forEach(it=>{
    g.appendChild(el('circle',{cx:x+6,cy:16,r:6,fill:it.c,'fill-opacity':.75,stroke:it.c}));
    const t=el('text',{x:x+19,y:16,fill:'#2f2c2b','font-size':'10.5px','font-weight':'700',
      'letter-spacing':'.14em','dominant-baseline':'middle',
      'font-family':'"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'});
    t.textContent=it.t.toUpperCase();
    g.appendChild(t);
    x+=19+t.getBBox().width+22;
  });
  return g;
}

function exportSVG(){
  /* every cluster names itself in a figure; put the page back the way it was after */
  const wasAll=LABEL_ALL;
  LABEL_ALL=true;hulls();
  const key=buildKey();
  const c=svg.cloneNode(true);
  key.remove();
  LABEL_ALL=wasAll;hulls();
  c.setAttribute('xmlns',NS);
  c.setAttribute('xmlns:xlink','http://www.w3.org/1999/xlink');
  c.setAttribute('version','1.1');
  /* Whatever the page is not drawing right now is DROPPED rather than carried as
     display:none, so the file is the picture and nothing behind it: the other
     mode's furniture, the filtered-out sources, the collapsed bars, and the
     invisible strips that only exist to catch a click. */
  c.querySelectorAll('.hidden,[display="none"],.sechit').forEach(e=>e.remove());
  c.querySelectorAll('*').forEach(e=>{
    ['fill','stroke'].forEach(a=>{
      if(!e.hasAttribute(a))return;
      const v=EXP_INK[e.getAttribute(a).trim().toLowerCase()];
      if(v)e.setAttribute(a,v);
    });
    /* the page clears display by setting it empty, which is not a legal SVG
       value; outside a browser it is a renderer's guess, so remove it */
    if(e.getAttribute('display')==='')e.removeAttribute('display');
    [...e.attributes].forEach(a=>{
      if(a.name.startsWith('data-')||a.name==='tabindex')e.removeAttribute(a.name);
    });
  });
  /* A saved figure cannot be clicked, so the band notes drop the instruction and
     keep the fact. The root's id goes too: two exported maps inlined into one
     document would otherwise collide. */
  c.querySelectorAll('.secnote').forEach(e=>{
    e.textContent=e.textContent.replace(/\s*\u00b7\s*click to expand$/,'');
  });
  c.removeAttribute('id');
  c.setAttribute('aria-label',MODE==='cluster'
    ? 'Citation clusters across the library'
    : 'Citation timeline across the library');
  /* The key sits above the drawing rather than on it, so everything else shifts
     down by its height and the viewBox grows to match. */
  const kc=c.querySelector('#exkey');
  const body=el('g',{transform:'translate(0,'+KEYH+')'});
  [...c.childNodes].forEach(n=>{if(n!==kc)body.appendChild(n);});
  c.appendChild(body);c.appendChild(kc);
  kc.removeAttribute('id');
  const vb=c.getAttribute('viewBox').split(/[\s,]+/).map(Number);
  c.setAttribute('viewBox','0 0 '+vb[2]+' '+(vb[3]+KEYH));
  c.setAttribute('height',vb[3]+KEYH);
  const st=document.createElementNS(NS,'style');
  st.textContent=EXP_CSS;
  c.insertBefore(st,c.firstChild);
  const d=el('desc',{});
  d.textContent='Zotero citation map — '+MODE+' view, '
    +c.querySelectorAll('.node').length+' sources, exported '+new Date().toISOString().slice(0,16).replace('T',' ');
  c.insertBefore(d,st);
  return '<?xml version="1.0" encoding="UTF-8"?>\n'
    +new XMLSerializer().serializeToString(c)+'\n';
}

function expName(){
  const d=new Date(),p=n=>String(n).padStart(2,'0');
  return 'citation-map-'+(MODE==='cluster'?'clustering':'timeline')+'-'
    +d.getFullYear()+p(d.getMonth()+1)+p(d.getDate())+'-'+p(d.getHours())+p(d.getMinutes())+'.svg';
}
document.getElementById('expsvg').addEventListener('click',()=>{
  const s=exportSVG(),name=expName();
  try{
    const u=URL.createObjectURL(new Blob([s],{type:'image/svg+xml;charset=utf-8'}));
    const a=document.createElement('a');a.href=u;a.download=name;
    document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(u),4000);
  }catch(err){}
});
/* A sandboxed frame can refuse a download silently, with no error to catch, so
   the clipboard is a second route rather than a fallback. Neither reports back:
   the button's own :active flash is the whole of the feedback, and a line of
   filename-and-size beside it was noise the reader had to keep re-reading past. */
document.getElementById('expcopy').addEventListener('click',async()=>{
  const s=exportSVG();
  try{await navigator.clipboard.writeText(s);}
  catch(err){
    const ta=document.createElement('textarea');
    ta.value=s;ta.style.cssText='position:fixed;left:-9999px;top:0';
    document.body.appendChild(ta);ta.select();
    try{document.execCommand('copy');}catch(e2){}
    ta.remove();
  }
});

/* the year key is a sequential legend, built from the same ramp the nodes use */
(()=>{const yk=document.getElementById('ykeyb');if(!yk)return;
  yk.innerHTML=FR.year_bins.map((b,i)=>'<span style="display:inline-flex;align-items:center;gap:5px;margin-right:11px">'
    +'<span style="width:11px;height:11px;background:'+FR.year_ramp[i]+';display:inline-block"></span>'
    +b.label+'</span>').join('');})();

document.body.dataset.mode='timeline';
buildBands();
relayout();
applySizes();
placeSize();
styleVoc();
paint();
scrubTo(D.nodes.length);
if(/cluster/i.test(location.hash||''))setMode('cluster');
/* A two-second replay of the library's growth, so the map reads as building itself
   back up: once after the app has rebuilt it, and on every change of view. Timed by
   the clock, on a timer rather than animation frames - a hidden tab gets no frames,
   and would be left showing half the library - so it always finishes, and is dropped
   the moment the reader takes the slider or the play button. Skipped for readers who
   ask for reduced motion. */
let buildF=null;
function buildUp(ms){
  if(window.matchMedia&&matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  stop();clearTimeout(buildF);
  const N=D.nodes.length,t0=performance.now();
  scrubTo(1);
  const step=()=>{
    const f=Math.min(1,(performance.now()-t0)/ms),k=Math.max(1,Math.round((1-Math.pow(1-f,2))*N));
    if(k!==tmax)scrubTo(k);
    buildF=f<1?setTimeout(step,30):null;
  };
  buildF=setTimeout(step,30);
}
const endBuild=()=>{clearTimeout(buildF);buildF=null;};
SC.addEventListener('input',endBuild);
PLAY.addEventListener('click',endBuild);   /* after play's own handler, so play carries on from here */
let shownMode=document.body.dataset.mode;
document.querySelectorAll('.msw').forEach(b=>b.addEventListener('click',()=>{
  if(document.body.dataset.mode!==shownMode){shownMode=document.body.dataset.mode;buildUp(2000);}}));
/* app.js leaves this flag behind when an update has just rewritten the map */
try{if(sessionStorage.getItem('mtg.rebuilt')){sessionStorage.removeItem('mtg.rebuilt');buildUp(2000);}}catch(e){}

/* A new width re-fits both views. The timeline re-reads X(); clustering re-fits the
   physics it already ran, which is quick and deterministic, so nothing is simulated
   again. Mid-transition it waits: the glide's own finish draws the result. The
   scroller is watched rather than the window, because the page's own scrollbar
   arriving narrows it without any window resize. Its width never depends on the
   drawing inside it, so redrawing cannot feed back into another resize. */
let rsz=null;
const refit=()=>{clearTimeout(rsz);rsz=setTimeout(()=>{
  const was=CW;measure();if(CW===was)return;
  FR.w=CW;
  if(settled&&!settling)fitAndCollide();
  if(MODE==='cluster'){
    svg.setAttribute('viewBox','0 0 '+FR.w+' '+FGH);svg.setAttribute('width',FR.w);
    if(!settling){drawCluster();apply();}
  }else relayout();
  if(selected)sel(selected);
},120);};
if(window.ResizeObserver&&SCR)new ResizeObserver(refit).observe(SCR);else addEventListener('resize',refit);
