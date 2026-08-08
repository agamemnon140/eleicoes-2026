'use strict';

// posição de cada UF no mapa estilizado (tile-grid), [coluna, linha] 1-indexado, grade de 7 colunas
const UF_GRID = {
  RR:[4,1], AP:[5,1],
  AM:[3,2], PA:[4,2], MA:[5,2], CE:[6,2], RN:[7,2],
  AC:[2,3], RO:[3,3], TO:[5,3], PI:[6,3], PB:[7,3],
  MT:[4,4], GO:[5,4], BA:[6,4], PE:[7,4],
  MS:[4,5], DF:[5,5], AL:[7,5],
  MG:[5,6], ES:[6,6], SE:[7,6],
  SP:[4,7], RJ:[5,7],
  PR:[4,8],
  SC:[4,9], RS:[3,9],
};
const COMP_COLOR = {governo:'#334155', presidente:'#0f766e', senado:'#b7791f', apoio:'#94a3b8'};
const BLOC_ORDER = ['Lula','Flávio','Caiado','Zema','Indefinido'];

let FC = null, PARTIES = null, PRES = null;
let tab = 'gov';
const filters = {uf:'ALL', bloc:'ALL', q:'', showOut:false};

const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const blocColor = b => (PARTIES?.blocs?.[b]?.color) || PARTIES?.default_bloc_color || '#94a3b8';
const blocLabel = b => (PARTIES?.blocs?.[b]?.label) || b || 'Indefinido';
const partyColor = p => (PARTIES?.parties?.[p]) || PARTIES?.default_party_color || '#64748b';

if ('serviceWorker' in navigator) {
  addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}

init();
async function init(){
  try{
    [FC, PARTIES, PRES] = await Promise.all([
      fetch('data/forecast.json').then(r=>r.json()),
      fetch('data/parties.json').then(r=>r.json()),
      fetch('data/president.json').then(r=>r.json()).catch(()=>null),
    ]);
  }catch(e){ $('#view').innerHTML = `<p class="loading">Não consegui carregar a previsão. Rode <code>python -m pipeline.build</code>.</p>`; return; }

  const d = new Date(FC.generated_at + 'T00:00:00');
  $('#subtitle').textContent = `Governador, Senado e Presidente — modelo de chapa executiva. Faltam ${FC.days_to_election} dias para o 1º turno (04/10/2026).`;
  $('#meta').textContent = `Atualizado em ${d.toLocaleDateString('pt-BR')} · fonte: ${FC.source} · os pesos do modelo refletem ${FC.days_to_election} dias até a eleição.`;

  $('#tabs').addEventListener('click', e => {
    const b = e.target.closest('button'); if(!b) return;
    tab = b.dataset.tab;
    document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('active', x===b));
    filters.uf='ALL'; filters.bloc='ALL'; filters.q=''; filters.showOut=false;
    render();
  });
  render();
}

function render(){
  const v = $('#view');
  if(tab==='pres'){ v.innerHTML = renderPresident(); return; }
  const office = tab==='gov' ? 'governor' : 'senate';
  v.innerHTML =
    mapPanel(office) +
    (office==='senate' ? nationalPanel() : '') +
    controlsBar(office) +
    `<div id="states">${statesList(office)}</div>`;
  wireControls(office);
  wireMap(office);
}

/* ---------- mapa ---------- */
function mapPanel(office){
  const tiles = Object.keys(FC.states).map(uf=>{
    const st = FC.states[uf]; const o = st[office];
    const [c,r] = UF_GRID[uf] || [1,1];
    const est = office==='governor' ? (o.estimate?`${o.estimate.name}`:'—')
              : (o.estimate.map(e=>e.name).join(' + ') || '—');
    return `<button class="tile ${o.stale?'stale':''}" style="grid-column:${c};grid-row:${r};background:${blocColor(o.bloc)}"
      data-uf="${uf}" data-est="${esc(st.estado)} — ${esc(est)}" aria-label="${esc(st.estado)}">
      ${uf}${o.estimate && (Array.isArray(o.estimate)?o.estimate.length:o.estimate)?'<span class="dot"></span>':''}</button>`;
  }).join('');
  // contagem por bloco
  const counts = {};
  Object.values(FC.states).forEach(st=>{const b=st[office].bloc; counts[b]=(counts[b]||0)+1;});
  const legend = BLOC_ORDER.filter(b=>counts[b]).map(b=>
    `<div class="lg"><span class="sw" style="background:${blocColor(b)}"></span>${esc(blocLabel(b))}<span class="count">${counts[b]}</span></div>`).join('');
  const title = office==='governor' ? 'Governadores estimados por estado' : 'Senado — bloco do 1º nome estimado';
  return `<section class="panel"><h2>${title}</h2>
    <p class="desc">Cada quadro é um estado, colorido pelo bloco do vencedor estimado. Toque para ir ao detalhe. Hachurado = pode estar desatualizado.</p>
    <div class="mapwrap"><div class="tilemap" role="group" aria-label="Mapa do Brasil">${tiles}</div>
      <div class="legend"><h3>Blocos (nº de estados)</h3>${legend}</div></div></section>`;
}
function wireMap(office){
  const tip = $('#tooltip');
  document.querySelectorAll('.tile').forEach(t=>{
    t.addEventListener('click', ()=>{ const el = document.getElementById('state-'+t.dataset.uf);
      if(el){ el.scrollIntoView({behavior:'smooth',block:'start'}); el.animate([{background:'#fff7e6'},{background:'transparent'}],{duration:1200}); } });
    t.addEventListener('pointermove', e=>{ tip.textContent = t.dataset.est; tip.classList.add('on');
      tip.style.left = Math.min(e.clientX+12, innerWidth-240)+'px'; tip.style.top=(e.clientY+14)+'px'; });
    t.addEventListener('pointerleave', ()=> tip.classList.remove('on'));
  });
}

/* ---------- consolidado nacional (senado) ---------- */
function nationalPanel(){
  const rows = FC.national;
  const max = Math.max(...rows.map(r=>r.sen2027), 1);
  const body = rows.filter(r=>r.sen2027>0||r.gov>0).map(r=>`
    <div class="natrow">
      <strong>${esc(r.party)}</strong>
      <b>${r.hold}</b><div class="bar"><i style="width:${100*r.hold/27}%;background:${partyColor(r.party)}"></i></div>
      <b>${r.newSen}</b><div class="bar b2 b2wrap"><i style="width:${100*r.newSen/54}%"></i></div>
      <b title="Senado 2027 (mantidos + novos)">${r.sen2027}</b><b title="governadores">${r.gov}</b>
    </div>`).join('');
  return `<section class="panel"><h2>Consolidado nacional do Senado em 2027</h2>
    <p class="desc">Mantém os 27 senadores com mandato até 2031 e soma os 54 novos estimados por este modelo.</p>
    <div class="natrow h"><div>Partido</div><div>Mant.</div><div></div><div>Novos</div><div class="b2h"></div><div>2027</div><div>Gov.</div></div>
    ${body}</section>`;
}

/* ---------- controles ---------- */
function controlsBar(office){
  const ufs = Object.keys(FC.states).sort((a,b)=>FC.states[a].estado.localeCompare(FC.states[b].estado,'pt-BR'));
  const opt = ufs.map(uf=>`<option value="${uf}" ${filters.uf===uf?'selected':''}>${esc(FC.states[uf].estado)}</option>`).join('');
  const blocs = BLOC_ORDER.map(b=>`<option value="${b}" ${filters.bloc===b?'selected':''}>${esc(blocLabel(b))}</option>`).join('');
  return `<div class="controls">
    <select id="f-uf"><option value="ALL">Todos os estados</option>${opt}</select>
    <select id="f-bloc"><option value="ALL">Todos os blocos</option>${blocs}</select>
    <input id="f-q" placeholder="Buscar candidato ou partido" value="${esc(filters.q)}">
    <label class="check"><input type="checkbox" id="f-out" ${filters.showOut?'checked':''}> mostrar retirados/não testados</label>
  </div>`;
}
function wireControls(office){
  $('#f-uf').onchange = e=>{ filters.uf=e.target.value; refresh(office); };
  $('#f-bloc').onchange = e=>{ filters.bloc=e.target.value; refresh(office); };
  $('#f-q').oninput = e=>{ filters.q=e.target.value.toLowerCase(); refresh(office); };
  $('#f-out').onchange = e=>{ filters.showOut=e.target.checked; refresh(office); };
}
function refresh(office){ $('#states').innerHTML = statesList(office); }

/* ---------- estados ---------- */
function candMatch(c){
  if(filters.bloc!=='ALL' && c.bloc!==filters.bloc) return false;
  if(!filters.showOut && !c.active) return false;
  if(filters.q && !(`${c.name} ${c.party}`.toLowerCase().includes(filters.q))) return false;
  return true;
}
function statesList(office){
  const ufs = Object.keys(FC.states).sort((a,b)=>FC.states[a].estado.localeCompare(FC.states[b].estado,'pt-BR'))
    .filter(uf=>filters.uf==='ALL'||filters.uf===uf);
  const out = ufs.map(uf=>stateCard(uf, office)).filter(Boolean).join('');
  return out || `<p class="loading">Nenhum resultado com esses filtros.</p>`;
}
function stateCard(uf, office){
  const st = FC.states[uf], o = st[office];
  const cands = o.candidates.filter(candMatch);
  if(!cands.length) return '';
  const label = office==='governor' ? 'Governador' : 'Senado · 2 vagas';
  return `<section class="state" id="state-${uf}">
    <div class="state-head"><h2>${esc(st.estado)} · ${label}</h2></div>
    ${estimateBox(uf, office)}
    ${office==='senate' ? competeBand(o) : ''}
    <div class="cards">${cands.map(c=>candRow(c, office)).join('')}</div>
  </section>`;
}
function estimateBox(uf, office){
  const o = FC.states[uf][office];
  const who = office==='governor'
    ? (o.estimate ? `<span class="blocchip" style="background:${blocColor(o.estimate.bloc)}">${esc(blocLabel(o.estimate.bloc))}</span> <strong>${esc(o.estimate.name)}</strong> <span class="badge" style="background:${partyColor(o.estimate.party)}">${esc(o.estimate.party)}</span>` : '—')
    : o.estimate.map(e=>`<span class="blocchip" style="background:${blocColor(e.bloc)}">${esc(e.party)}</span> <strong>${esc(e.name)}</strong>`).join(' &nbsp;+&nbsp; ');
  const w = office==='governor'
    ? `pesos: governador ${(o.weights.gov*100|0)}% · presidente ${(o.weights.pres*100|0)}%`
    : `pesos: Senado ${(o.weights.senado*100|0)}% · gov. ${(o.weights.governo*100|0)}% · pres. ${(o.weights.presidente*100|0)}% · apoio ${(o.weights.apoio*100|0)}%`;
  return `<div class="estimate">
    <div><strong>★ ${office==='governor'?'Governador estimado':'Senadores estimados'}</strong>
      <div class="who">${who}</div><div class="meta2">${w}${o.stale?' · <span class="pill stale">pode estar desatualizado</span>':''}</div></div>
    <div class="certainty"><span class="muted">certeza</span><b>${esc(o.certainty||'—')}</b>${o.may_change?`<div class="muted">${o.may_change}% podem mudar</div>`:''}</div>
  </div>`;
}
function competeBand(o){
  const polled = o.candidates.filter(c=>c.active && typeof c.pct==='number').sort((a,b)=>b.pct-a.pct).slice(0,4);
  if(polled.length<2) return '';
  return `<div class="compete"><b>Pesquisa do Senado — faixa competitiva</b>
    <div class="chips">${polled.map(c=>`<span class="chip">${esc(c.name)} · ${esc(c.pctDisplay)}</span>`).join('')}</div></div>`;
}
function candRow(c, office){
  const comps = c.components || {};
  const compBar = Object.keys(COMP_COLOR).filter(k=>comps[k]>0)
    .map(k=>`<i style="flex:${comps[k]};background:${COMP_COLOR[k]}" title="${k}: ${comps[k]}"></i>`).join('');
  const pctBar = typeof c.pct==='number' ? `<div class="pollbar"><i style="width:${Math.min(100,c.pct)}%"></i></div>` : '';
  const est = c.estimated ? `<span class="won">★ estimado · ${esc(c.certainty_preview||FC.states[c.uf]?.[office]?.certainty||'')}</span>` : '';
  const apoio = c.apoio_verificado
    ? `<span class="win-badge">${esc(c.apoio)}</span>`
    : (c.apoio ? esc(c.apoio) : 'apoio não verificado');
  const src = c.fonte ? ` · <a class="src" href="${esc(c.fonte)}" target="_blank" rel="noopener">pesquisa ↗</a>` : '';
  return `<div class="cand ${c.estimated?'est':''} ${c.active?'':'out'}">
    <div>
      <div class="name">${esc(c.name)} <span class="badge" style="background:${partyColor(c.party)}">${esc(c.party)}</span>
        <span class="blocchip" style="background:${blocColor(c.bloc)}">${esc(blocLabel(c.bloc))}</span></div>
      <div class="meta2">${apoio} · ${esc(c.instituto||'')} ${esc(c.campo||'')}${src}</div>
      ${est?`<div style="margin-top:4px">${est}</div>`:''}
    </div>
    <div class="pollbox"><div class="pct">${esc(c.pctDisplay||'—')}</div>${pctBar}</div>
    <div class="scorebox"><div class="score">${Math.round(c.score)}<small>índice</small></div><div class="comp">${compBar}</div></div>
  </div>`;
}

/* ---------- presidente ---------- */
function renderPresident(){
  const lean = (PRES && PRES.pres_lean) || {};
  const ufs = Object.keys(lean).sort((a,b)=>(FC.states[a]?.estado||a).localeCompare(FC.states[b]?.estado||b,'pt-BR'));
  const cards = ufs.map(uf=>{
    const l = lean[uf]; const segs = ['Lula','Flávio','Caiado','Zema'].filter(b=>l[b])
      .map(b=>`<span style="flex:${l[b]};background:${blocColor(b)}" title="${b}: ${l[b]}%"></span>`).join('');
    return `<div class="pl"><b>${esc(FC.states[uf]?.estado||uf)}</b>
      <div class="track">${segs}</div>
      <div class="meta2">Lula ${l.Lula??'—'}% · Flávio ${l['Flávio']??'—'}% <span class="muted">(${esc(l.basis||'')})</span></div></div>`;
  }).join('');
  return `<section class="panel note"><h2 style="margin-top:0">Disputa presidencial — agregado nacional</h2>
    <p class="desc" style="margin:0">O agregado nacional (poll-of-polls, 1º e 2º turno) será preenchido automaticamente pelo coletor do agregador (president.py). Por enquanto, veja abaixo a inclinação presidencial por estado, que alimenta os modelos de governador e senado.</p></section>
  <section class="panel"><h2>Inclinação presidencial por estado</h2>
    <p class="desc">Barra proporcional ao 2º turno estimado por estado (pesquisa estadual quando há; senão proxy de 2022).</p>
    <div class="pres-lean">${cards}</div></section>`;
}
