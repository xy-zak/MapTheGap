
/* ============================ clustering mode ============================
   Position is an OUTPUT here, not an input. Citations are strong springs,
   vocabulary overlap is a weak one, every node repels every other, and the
   arrangement that survives is the library's own structure.

   Two rules keep it honest, both of them load-bearing:
     - vocabulary links are physics but NOT ink, so proximity can say "same
       language" while the absence of a line says "no citation bridge". A tight
       cluster with no lines in it is the most informative shape on the page.
     - a node with no link of either kind is NOT simulated. Gravity alone would
       drift it to the middle and it would read as belonging there, so it goes to
       a gutter where its position is declared meaningless.
   ====================================================================== */
const FR=D.force, FRAD=FR.rad, FCOM=FR.com;
const GUT_H=FR.gutter.length?74:0, FGH=FR.h+GUT_H;
const P={};
FR.sim.forEach(k=>{P[k]={x:FR.seed[k][0],y:FR.seed[k][1],vx:0,vy:0,fx:0,fy:0};});
let MODE='timeline', COLOR='role', settled=false, settling=false;
/* On the page a label appears only for the clusters covering the selected source:
   five at once competed with each other and with the nodes beneath them. A saved
   figure has no selection and nobody to click, so the export raises this and every
   cluster names itself. See exportSVG(). */
let LABEL_ALL=false;
/* The spring-to-repulsion balance: springs scale by BAL, repulsion by 1/BAL, so it
   is a ratio rather than an absolute strength — the only form that survives the
   canvas fit. It was a slider once; it is a constant now, and force.py owns it. */
const BAL=FR.p.balance;
/* Smallest community that gets a drawn outline. force.py owns the number so the
   hull count and the '<n> clusters' readout below can never disagree. */
const HMIN=FR.hullmin;

const gH=el('g',{});svg.insertBefore(gH,gT);      /* hulls, behind every link */
const gU=el('g',{display:'none'});svg.appendChild(gU);
const gL=el('g',{});svg.appendChild(gL);          /* hull labels, above everything */

/* ---- the simulation. Velocity Verlet with a cooling schedule, all pairs:
   90 nodes is 4005 pairs a tick, so no quadtree is worth the code. No RNG is
   used anywhere, and both the node list and the link lists arrive pre-sorted
   from Python, so the result is bit-identical on every run and every reload. ---- */
function simStep(alpha){
  const S=FR.sim,n=S.length,p=FR.p;
  for(let i=0;i<n;i++){
    const a=S[i],pa=P[a];
    for(let j=i+1;j<n;j++){
      const b=S[j],pb=P[b];
      let dx=pb.x-pa.x,dy=pb.y-pa.y,d2=dx*dx+dy*dy;
      if(d2<1e-6){dx=0.7;dy=0.31;d2=0.6;}              /* deterministic nudge */
      const d=Math.sqrt(d2),f=p.repel/BAL*alpha*(1+0.09*(FRAD[a]+FRAD[b]))/d2;
      const ux=dx/d,uy=dy/d;
      pa.vx+=f*ux;pa.vy+=f*uy;pb.vx-=f*ux;pb.vy-=f*uy;
    }
  }
  /* bias by 1/min(degree): without it a hub's many springs drag it around far
     more than any single neighbour, and the hub ends up placed by its degree
     rather than by who it cites.

     The cost, worth knowing when reading the map: this normalises a node's TOTAL
     spring budget to roughly one link's worth, so four vocabulary links pull about
     as hard as one. A low-degree source with no citations is therefore held very
     loosely and can settle outside its own community outline. That is the layout
     being honest about weak evidence, not a bug — but it does mean "it has four
     dashed lines" is not a reason to expect it to sit tight. */
  const spring=(a,b,s,L)=>{
    const pa=P[a],pb=P[b];if(!pa||!pb)return;
    const dx=pb.x-pa.x,dy=pb.y-pa.y,d=Math.hypot(dx,dy)||0.01;
    const bias=1/Math.max(1,Math.min(FR.deg[a],FR.deg[b]));
    const f=(d-L)/d*s*alpha*bias,fx=dx*f,fy=dy*f;
    pa.vx+=fx;pa.vy+=fy;pb.vx-=fx;pb.vy-=fy;
  };
  /* BAL scales both spring types together, never one against the other: the ratio
     between a citation and a shared word is the whole claim the layout makes.
     Every vocabulary link pulls with the same p.vocstr — half a citation.

     p.voclen is the length the spring WANTS, not a ceiling: past it the spring
     pulls the pair together, inside it the spring pushes them apart. It was once
     ten times the citation length, which quietly turned most of the dashed links
     into repulsion; force.py records that. Keep it near the citation length. */
  FR.cit.forEach(e=>spring(e[0],e[1],p.citstr*BAL,p.citlen+FRAD[e[0]]+FRAD[e[1]]));
  FR.voc.forEach(e=>spring(e[0],e[1],p.vocstr*BAL,p.voclen));
  let cx=0,cy=0;S.forEach(k=>{cx+=P[k].x;cy+=P[k].y;});cx/=n;cy/=n;
  S.forEach(k=>{const q=P[k];
    q.vx+=(cx-q.x)*p.grav*alpha;q.vy+=(cy-q.y)*p.grav*alpha;
    q.vx*=p.decay;q.vy*=p.decay;
    /* Speed ceiling. A spring-dominated setting otherwise feeds itself and the
       whole layout flies apart — measured at 18 million px across before this
       existed. It also tightens the default layout rather than merely rescuing
       the extremes. */
    const sp=Math.hypot(q.vx,q.vy);
    if(sp>p.vmax){q.vx=q.vx/sp*p.vmax;q.vy=q.vy/sp*p.vmax;}
    q.x+=q.vx;q.y+=q.vy;});
}

/* Physics runs in arbitrary units and the result is fitted to the canvas after.
   Decoupling the two means the force constants control how the layout FEELS —
   how tightly a cluster holds — while the fit controls how much of the page it
   uses. Tuning one no longer disturbs the other. */
function fitAndCollide(){
  const S=FR.sim,px=FR.pad[0],py=FR.pad[1];
  let x0=1e9,x1=-1e9,y0=1e9,y1=-1e9;
  S.forEach(k=>{const q=P[k];
    if(q.x<x0)x0=q.x;if(q.x>x1)x1=q.x;if(q.y<y0)y0=q.y;if(q.y>y1)y1=q.y;});
  const s=Math.min((FR.w-2*px)/Math.max(1,x1-x0),(FR.h-2*py)/Math.max(1,y1-y0));
  const ox=(FR.w-(x1-x0)*s)/2,oy=(FR.h-(y1-y0)*s)/2;
  S.forEach(k=>{const q=P[k];q.fx=(q.x-x0)*s+ox;q.fy=(q.y-y0)*s+oy;});
  for(let it=0;it<14;it++)
    for(let i=0;i<S.length;i++)for(let j=i+1;j<S.length;j++){
      const a=S[i],b=S[j],pa=P[a],pb=P[b];
      const dx=pb.fx-pa.fx,dy=pb.fy-pa.fy;
      const r=FRAD[a]+FRAD[b]+FR.p.collide,d=Math.hypot(dx,dy)||0.01;
      if(d<r){const sh=(r-d)/d*0.5;
        pa.fx-=dx*sh;pa.fy-=dy*sh;pb.fx+=dx*sh;pb.fy+=dy*sh;}
    }
}

/* The whole simulation runs SYNCHRONOUSLY, and only the journey is animated.
   It was originally spread ten ticks per animation frame, which was a mistake:
   500 ticks then needed 50 frames to exist at all, so anything that throttles
   requestAnimationFrame — a background tab, and headless Chrome, where it fires
   about eleven times — left the layout stranded part-cooled with `settled` still
   false. All 500 ticks are ~2M pair operations and finish in about a tenth of a
   second, so there is nothing to spread. Computing up front means the real layout
   exists before a single frame is drawn, and it no longer depends on frame timing
   at all — which makes it more reproducible, not less.

   The animation is then a plain interpolation toward the finished positions, and
   its progress is measured in MILLISECONDS rather than frames. A tab that grants
   one frame a second still arrives: the first callback sees the full duration
   elapsed and jumps straight to the end. */
function computeLayout(){
  FR.sim.forEach(k=>{const q=P[k];
    q.x=FR.seed[k][0];q.y=FR.seed[k][1];q.vx=0;q.vy=0;});
  let alpha=1;const adec=1-Math.pow(0.001,1/FR.p.ticks);
  for(let t=0;t<FR.p.ticks;t++){alpha+=(0-alpha)*adec;simStep(alpha);}
  fitAndCollide();
}

function settle(){
  if(settling)return;
  settling=true;
  const sx={},sy={};
  if(settled){                       /* re-settle: glide from the layout on screen */
    FR.sim.forEach(k=>{sx[k]=P[k].fx;sy[k]=P[k].fy;});
  }else{                             /* first entry: start from the fitted seed */
    FR.sim.forEach(k=>{const q=P[k];q.x=FR.seed[k][0];q.y=FR.seed[k][1];});
    fitAndCollide();
    FR.sim.forEach(k=>{sx[k]=P[k].fx;sy[k]=P[k].fy;});
  }
  computeLayout();
  const tx={},ty={};
  FR.sim.forEach(k=>{tx[k]=P[k].fx;ty[k]=P[k].fy;});
  settled=true;                      /* true once the positions are REAL */
  const clock=()=>(window.performance&&performance.now?performance.now():Date.now());
  const t0=clock(),DUR=620;
  let fin=false;
  const finish=()=>{
    if(fin)return;
    fin=true;
    FR.sim.forEach(k=>{P[k].fx=tx[k];P[k].fy=ty[k];});
    settling=false;
    if(MODE==='cluster'){drawCluster();apply();}
  };
  const frame=()=>{
    if(fin)return;
    const u=Math.min(1,(clock()-t0)/DUR);
    const e=u<0.5?2*u*u:1-Math.pow(-2*u+2,2)/2;
    FR.sim.forEach(k=>{
      P[k].fx=sx[k]+(tx[k]-sx[k])*e;P[k].fy=sy[k]+(ty[k]-sy[k])*e;});
    if(MODE==='cluster')drawCluster();
    if(u<1){requestAnimationFrame(frame);return;}
    finish();
  };
  requestAnimationFrame(frame);
  /* requestAnimationFrame is a courtesy, not a guarantee: it is throttled in a
     background tab and in headless Chrome it stops outright after a handful of
     frames. A timer finishes the job regardless, so the layout can never be left
     stranded mid-interpolation with `settling` stuck true — which would also block
     the next re-settle, since that guards on it. Both paths are idempotent. */
  setTimeout(finish,DUR+150);
}

function hull(pts){
  const Q=pts.slice().sort((a,b)=>a[0]-b[0]||a[1]-b[1]);
  const cr=(o,a,b)=>(a[0]-o[0])*(b[1]-o[1])-(a[1]-o[1])*(b[0]-o[0]);
  const lo=[],up=[];
  for(const p of Q){while(lo.length>=2&&cr(lo[lo.length-2],lo[lo.length-1],p)<=0)lo.pop();lo.push(p);}
  for(let i=Q.length-1;i>=0;i--){const p=Q[i];
    while(up.length>=2&&cr(up[up.length-2],up[up.length-1],p)<=0)up.pop();up.push(p);}
  lo.pop();up.pop();return lo.concat(up);
}

/* A community of two has no polygon: the convex hull of two points is a line
   segment, and three collinear members collapse the same way. Such a hull draws as
   a hairline that encloses nothing and cannot be hit-tested, so before HULL_MIN
   came down to 2 these communities were simply skipped.

   The fix is to hull points sampled ON EACH MEMBER'S CIRCLE rather than their
   centres, which yields a real lozenge around the pair and is guaranteed to contain
   the node fills. It is only reached when the plain hull has degenerated, so every
   outline that already existed is unchanged — this is an added case, not a new
   policy for the hulls that were already being drawn. */
function ringHull(keys){
  const pts=[];
  keys.forEach(k=>{
    if(!P[k])return;
    const r=(FRAD[k]||4)+7;
    for(let i=0;i<12;i++){
      const a=i/12*Math.PI*2;
      pts.push([P[k].fx+Math.cos(a)*r,P[k].fy+Math.sin(a)*r]);
    }
  });
  return hull(pts);
}

/* Point in polygon by ray casting. This decides which clusters a source sits in
   VISUALLY, which is a different question from which community Louvain assigned
   it to. The hulls genuinely overlap wherever communities interleave, so a node
   can fall inside three of them at once, and a reader pointing at it wants all
   three names rather than only the one recorded in the data. */
function inPoly(x,y,poly){
  let inside=false;
  for(let i=0,j=poly.length-1;i<poly.length;j=i++){
    const xi=poly[i][0],yi=poly[i][1],xj=poly[j][0],yj=poly[j][1];
    if(((yi>y)!==(yj>y))&&(x<(xj-xi)*(y-yi)/(yj-yi)+xi))inside=!inside;
  }
  return inside;
}

/* Hulls are the INDEPENDENT check on the layout, not decoration. They outline
   Louvain communities computed from the weighted graph without reference to any
   geometry, so a hull that comes out long and tangled means the physics and the
   maths disagree and that blob should not be believed.

   Every community of FR.hullmin members or more gets an outline. That threshold was
   3, on the argument that a ring around a pair states nothing; it is 2 now, because
   a pair the maths made its own community is a claim worth seeing, and an unringed
   pair was indistinguishable from two sources that were never grouped at all.
   A two-member hull has no area of its own, so ringHull() supplies one.

   Three passes, because the outlines must all exist before anything can be tested
   against them: build every polygon, work out which ones cover the selection, then
   draw and label. */
function hulls(){
  while(gH.firstChild)gH.removeChild(gH.firstChild);
  while(gL.firstChild)gL.removeChild(gL.firstChild);
  if(MODE!=='cluster')return;

  /* ---- pass 1: the outlines ---- */
  const polys=[];
  FR.clusters.forEach(c=>{
    if(c.size<HMIN)return;
    const mem=c.members.filter(k=>byKey[k]&&vis(byKey[k])&&P[k]);
    if(mem.length<HMIN)return;
    /* A convex hull over every member is dragged into a huge lozenge by the two
       or three that sit far out, and on this library those lozenges cover each
       other and read as one shapeless overlap. So the hull covers the community
       CORE — members within 1.6x the median distance from its centroid — and the
       label says how many of the members that is. An outlying member is still on
       the canvas, still the same colour, and still in the cluster; it is just not
       allowed to define the boundary. */
    let mx=0,my=0;mem.forEach(k=>{mx+=P[k].fx;my+=P[k].fy;});mx/=mem.length;my/=mem.length;
    const ds=mem.map(k=>Math.hypot(P[k].fx-mx,P[k].fy-my)).sort((a,b)=>a-b);
    const med=ds[Math.floor(ds.length/2)]||1;
    const core=mem.filter(k=>Math.hypot(P[k].fx-mx,P[k].fy-my)<=Math.max(1.6*med,40));
    /* The core trim only makes sense once there are enough members for an outlier to
       be meaningful. Below 3 every member defines the shape. */
    const use=core.length>=3?core:mem;
    let h=hull(use.map(k=>[P[k].fx,P[k].fy]));
    if(h.length<3)h=ringHull(use);     /* a pair, or collinear members */
    if(h.length<3)return;
    let cx=0,cy=0;h.forEach(q=>{cx+=q[0];cy+=q[1];});cx/=h.length;cy/=h.length;
    const ex=h.map(q=>{const dx=q[0]-cx,dy=q[1]-cy,d=Math.hypot(dx,dy)||1;
      return [q[0]+dx/d*16,q[1]+dy/d*16];});
    polys.push({c:c,ex:ex,cx:cx,cy:cy,use:use.length});
  });

  /* ---- pass 2: which hulls cover the selected source ---- */
  const on={};
  if(selected!=null){
    /* Its own community is always named, even when the source is one of the
       outliers excluded from that hull's core and so falls outside the outline.
       It is still a member, and saying so is more use than staying silent. */
    if(FCOM[selected]!=null)on[FCOM[selected]]=1;
    const q=P[selected];
    if(q)polys.forEach(pl=>{if(inPoly(q.fx,q.fy,pl.ex))on[pl.c.id]=1;});
  }

  /* ---- pass 3: draw, then label every covering hull ---- */
  const lab=[];
  polys.forEach(pl=>{
    const ex=pl.ex,mid=(a,b)=>[(a[0]+b[0])/2,(a[1]+b[1])/2];
    const st=mid(ex[ex.length-1],ex[0]);
    let d='M'+st[0].toFixed(1)+','+st[1].toFixed(1);
    for(let i=0;i<ex.length;i++){
      const v=ex[i],m=mid(v,ex[(i+1)%ex.length]);
      d+=' Q'+v[0].toFixed(1)+','+v[1].toFixed(1)+' '+m[0].toFixed(1)+','+m[1].toFixed(1);
    }
    const isOn=!!on[pl.c.id];
    gH.appendChild(el('path',{d:d+' Z',class:'hull'+(isOn?' on':'')}));
    if(!isOn&&!LABEL_ALL)return;
    /* The label is pushed OUTWARD, away from the middle of the graph, and joined to
       its outline by a leader. Sitting it just above the hull put it on top of the
       very nodes a reader was looking at; out here it has empty canvas to land on,
       and the leader keeps the association explicit rather than implied by
       proximity. Direction is from the canvas centre through the hull's centroid,
       so labels fan out instead of stacking. */
    let dx=pl.cx-FR.w/2, dy=pl.cy-FR.h/2;
    let dl=Math.hypot(dx,dy);
    if(dl<1){dx=0;dy=-1;dl=1;}          /* a hull dead centre has no outward way */
    dx/=dl;dy/=dl;
    /* where the leader meets the outline: the boundary vertex furthest out along
       that direction */
    let anc=pl.ex[0],best=-1e9;
    pl.ex.forEach(v=>{const s2=(v[0]-pl.cx)*dx+(v[1]-pl.cy)*dy;
      if(s2>best){best=s2;anc=v;}});
    const g=el('g',{});
    const t=el('text',{x:0,y:0,class:'hulllbl','text-anchor':'middle',
      'dominant-baseline':'middle'});
    t.textContent=pl.c.label.toUpperCase()+'  ['+pl.use+(pl.use<pl.c.size?'/'+pl.c.size:'')+']';
    g.appendChild(t);gL.appendChild(g);
    const bb=t.getBBox();               /* measured, not estimated from glyph widths */
    const w=bb.width+18,h=bb.height+10;
    lab.push({g:g,t:t,bb:bb,w:w,h:h,anc:anc,
      px:Math.max(w/2+6,Math.min(FR.w-w/2-6,anc[0]+dx*44)),
      /* Clamp to the GRAPH area, not the full canvas: below FR.h is the gutter
         strip, and a label parked down there sits on its caption. */
      cy:Math.max(h/2+6,Math.min(FR.h-h/2-6,anc[1]+dy*44))});
  });

  /* Several labels can be up at once, so any that still collide after being fanned
     outward are pushed apart. They only ever move down, and each is re-checked
     against everything already placed until it stops moving. The leader is drawn
     afterwards, so it follows the label to wherever it ended up. */
  lab.sort((a,b)=>a.cy-b.cy||a.px-b.px);
  lab.forEach((L,i)=>{
    for(let pass=0;pass<lab.length;pass++){
      let moved=false;
      for(let j=0;j<i;j++){
        const M=lab[j];
        if(Math.abs(L.cy-M.cy)<(L.h+M.h)/2+5&&Math.abs(L.px-M.px)<(L.w+M.w)/2+8){
          L.cy=M.cy+(L.h+M.h)/2+5;moved=true;
        }
      }
      if(!moved)break;
    }
    L.cy=Math.min(FR.h-L.h/2-6,Math.max(L.h/2+6,L.cy));
    L.g.setAttribute('transform','translate('+L.px.toFixed(1)+','+L.cy.toFixed(1)+')');
    /* Leader first, box second: the box then paints over the leader's last few
       pixels, so the line appears to stop at the label's edge without anyone
       having to intersect a rectangle. */
    L.g.insertBefore(el('line',{x1:(L.anc[0]-L.px).toFixed(1),y1:(L.anc[1]-L.cy).toFixed(1),
      x2:'0',y2:'0',class:'hullline'}),L.t);
    L.g.insertBefore(el('rect',{x:(L.bb.x-9).toFixed(1),y:(L.bb.y-5).toFixed(1),
      width:L.w.toFixed(1),height:L.h.toFixed(1),class:'hullbox'}),L.t);
  });
}

function drawCluster(){
  D.nodes.forEach(n=>{
    const q=P[n.key];
    if(q){n._x=q.fx;n._y=q.fy;}
    else{const i=FR.gutter.indexOf(n.key);
      n._x=FR.pad[0]+40+i*130;n._y=FR.h+GUT_H*0.62;}
    n._c.setAttribute('cx',n._x);n._c.setAttribute('cy',n._y);
    n._c.setAttribute('display','');
    n._b.setAttribute('display','none');
  });
  paths();hulls();
}

/* Node fill carries role in both modes, exactly as the timeline does, so a
   source keeps its identity across a mode switch. Colour-by-year is the opt-in
   alternative, and it exists because the force layout throws the year axis away:
   a sequential single-hue ramp puts lineage back inside each cluster. */
/* Which fixed decade bin a year falls in, or -1 for a source with no year
   recorded. Those get a neutral grey rather than being folded into the oldest
   bin, which would have quietly asserted a date the library does not have. */
function yearBin(y){
  if(!y)return -1;
  const B=FR.year_bins;
  for(let i=0;i<B.length;i++)
    if((B[i].lo==null||y>=B[i].lo)&&(B[i].hi==null||y<=B[i].hi))return i;
  return -1;
}

function paint(){
  const R=FR.year_ramp;
  D.nodes.forEach(n=>{
    let c=RAW[n.role];
    if(COLOR==='year'&&MODE==='cluster'){
      const b=yearBin(n.year);
      c=b<0?'#6B5E73':R[b];
    }
    n._c.setAttribute('fill',c);n._c.setAttribute('stroke',c);
    n._b.setAttribute('fill',c);
  });
  const yr=COLOR==='year'&&MODE==='cluster';
  const sw=document.getElementById('ykey');
  if(sw)sw.style.display=yr?'':'none';
  /* the legend has to agree with what the circles are actually showing */
  const cbw=document.getElementById('cbw');
  if(cbw)cbw.textContent=yr?'the year':'the role';
}

/* gutter furniture: built once, shown only in clustering mode */
if(FR.gutter.length){
  gU.appendChild(el('line',{x1:FR.pad[0],y1:FR.h+10,x2:FR.w-FR.pad[0],y2:FR.h+10,class:'gutrule'}));
  const t=el('text',{x:FR.pad[0],y:FR.h+27,class:'gutlbl'});
  t.textContent='NO CITATION AND NO VOCABULARY LINK \u2014 NOT SIMULATED, POSITION MEANS NOTHING ['+FR.gutter.length+']';
  gU.appendChild(t);
}

/* Vocabulary links are drawn in both modes now, but thinner and fainter in
   clustering, where there are citation lines competing for the same space. */
function styleVoc(){
  const w=MODE==='cluster'?0.55:0.8, o=MODE==='cluster'?0.30:0.55;
  gT.querySelectorAll('path').forEach(p=>{
    p.setAttribute('stroke','#6B5E73');
    p.setAttribute('stroke-width',w);p.setAttribute('opacity',o);
  });
}

function setMode(m){
  if(MODE===m)return;
  MODE=m;document.body.dataset.mode=m;
  document.querySelectorAll('.msw').forEach(b=>
    b.setAttribute('aria-pressed',b.dataset.m===m?'true':'false'));
  if(m==='cluster'){
    svg.setAttribute('viewBox','0 0 '+FR.w+' '+FGH);
    svg.setAttribute('width',FR.w);svg.setAttribute('height',FGH);
    gB.setAttribute('display','none');gG.setAttribute('display','none');
    gU.setAttribute('display','');
    if(!settled)settle();else drawCluster();
  }else{
    gB.setAttribute('display','');gG.setAttribute('display','');
    gU.setAttribute('display','none');
    while(gH.firstChild)gH.removeChild(gH.firstChild);
    while(gL.firstChild)gL.removeChild(gL.firstChild);
    relayout();
  }
  styleVoc();paint();placeSize();apply();
  if(selected)sel(selected);
  /* the mode belongs in the URL: a reader who sends someone the link means the
     view they were looking at, not whichever one happens to be the default */
  if(history.replaceState)history.replaceState(null,'','#'+(m==='cluster'?'clustering':'timeline'));
}

document.querySelectorAll('.msw').forEach(b=>
  b.addEventListener('click',()=>setMode(b.dataset.m)));
document.getElementById('resettle').addEventListener('click',()=>{
  settled=false;while(gH.firstChild)gH.removeChild(gH.firstChild);settle();});
document.getElementById('cby').addEventListener('click',e=>{
  COLOR=COLOR==='role'?'year':'role';
  e.currentTarget.textContent='colour: '+COLOR;paint();});

document.getElementById('ccn').textContent=
  FR.clusters.filter(c=>c.size>=HMIN).length+' clusters \u00b7 '+FR.sim.length+' simulated \u00b7 '
  +FR.gutter.length+' unlinked';
