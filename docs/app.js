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
const COMP_LABEL = {governo:'Governador', presidente:'Presidente', senado:'Pesquisa Senado', apoio:'Apoio/chapa'};
const BLOC_ORDER = ['Lula','Flávio','Caiado','Zema','Indefinido'];

let FC = null, PARTIES = null, PRES = null;
let tab = 'gov';
let colorMode = 'bloco';               // 'bloco' | 'partido'
let partyFocus = null;                 // partido em foco (drill-down)
const openCards = new Set();           // detalhes abertos (uf|cargo|nome)
const filters = {uf:'ALL', bloc:'ALL', q:'', showOut:false};

const $ = (s, r=document) => r.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));
const blocColor = b => (PARTIES?.blocs?.[b]?.color) || PARTIES?.default_bloc_color || '#94a3b8';
const blocLabel = b => (PARTIES?.blocs?.[b]?.label) || b || 'Indefinido';
const partyColor = p => (PARTIES?.parties?.[p]) || PARTIES?.default_party_color || '#64748b';
const num = x => (typeof x === 'number');
const fpct = x => num(x) ? String(x).replace('.', ',') + '%' : '—';

const office = () => tab === 'gov' ? 'governor' : 'senate';
const winnerParty = (st, off) => off === 'governor'
  ? (st.governor.estimate?.party) : (st.senate.estimate[0]?.party);
const estColor = e => colorMode === 'bloco' ? blocColor(e.bloc) : partyColor(e.party);
// fundo do quadro: governador = 1 cor; senado = dividido pelos 2 senadores estimados
function tileBg(st, off){
  if(off === 'governor'){ const e = st.governor.estimate; return e ? estColor(e) : blocColor('Indefinido'); }
  const es = st.senate.estimate;
  if(es.length >= 2) return `linear-gradient(135deg, ${estColor(es[0])} 0 50%, ${estColor(es[1])} 50% 100%)`;
  return es.length === 1 ? estColor(es[0]) : blocColor('Indefinido');
}
// estado "vence" para um partido? (governador OU alguma vaga de senado)
const govWins = (st, p) => st.governor.estimate?.party === p;
const senWins = (st, p) => st.senate.estimate.some(e => e.party === p);

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
  }catch(e){ $('#view').innerHTML = `<p class="loading">Não consegui carregar a previsão. Rode <code>py -m pipeline.build</code>.</p>`; return; }

  const d = new Date(FC.generated_at + 'T00:00:00');
  $('#subtitle').textContent = `Governador, Senado e Presidente — modelo de chapa executiva. Faltam ${FC.days_to_election} dias para o 1º turno (04/10/2026).`;
  $('#meta').textContent = `Atualizado em ${d.toLocaleDateString('pt-BR')} · fonte: ${FC.source} · os pesos do modelo refletem ${FC.days_to_election} dias até a eleição.`;

  $('#tabs').addEventListener('click', e => {
    const b = e.target.closest('button'); if(!b) return;
    tab = b.dataset.tab;
    document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('active', x===b));
    filters.uf='ALL'; filters.bloc='ALL'; filters.q=''; filters.showOut=false; openCards.clear(); partyFocus=null;
    render();
  });
  render();
}

function render(){
  const v = $('#view');
  if(tab==='pres'){ v.innerHTML = renderPresident(); return; }
  const off = office();
  v.innerHTML =
    (partyFocus ? partyFocusPanel() : '') +
    mapPanel(off) +
    (colorMode==='partido' ? partyPanel(off) : '') +
    (off==='senate' ? nationalPanel() : '') +
    controlsBar() +
    `<div id="states">${statesList(off)}</div>`;
  wireControls();
  wireMap(off);
  wireParty();
  wireDetails();
}
function partyFocusPanel(){
  const p = partyFocus;
  const govs = Object.keys(FC.states).filter(uf=>govWins(FC.states[uf], p))
    .sort((a,b)=>FC.states[a].estado.localeCompare(FC.states[b].estado,'pt-BR'));
  const sens = [];
  Object.keys(FC.states).forEach(uf=>FC.states[uf].senate.estimate.forEach(e=>{ if(e.party===p) sens.push({uf, name:e.name}); }));
  sens.sort((a,b)=>FC.states[a.uf].estado.localeCompare(FC.states[b.uf].estado,'pt-BR'));
  const chip = (uf,label)=>`<button class="stchip" data-uf="${uf}">${esc(label||FC.states[uf].estado)}</button>`;
  return `<section class="panel focus" style="border-left:5px solid ${partyColor(p)}">
    <div class="panel-top"><h2><span class="badge" style="background:${partyColor(p)}">${esc(p)}</span> onde o modelo prevê vitória</h2>
      <button class="clearfocus" id="clearFocus">limpar ✕</button></div>
    <div class="focusgrid">
      <div><b>Governador (${govs.length})</b><div class="chips2">${govs.map(uf=>chip(uf)).join('') || '<span class="muted">nenhum</span>'}</div></div>
      <div><b>Senado (${sens.length} vaga${sens.length!==1?'s':''})</b><div class="chips2">${sens.map(s=>chip(s.uf, `${s.name} · ${s.uf}`)).join('') || '<span class="muted">nenhuma</span>'}</div></div>
    </div></section>`;
}
function wireParty(){
  document.querySelectorAll('[data-party]').forEach(b=>b.onclick=()=>{
    const p=b.dataset.party; partyFocus = (partyFocus===p ? null : p); render();
  });
  const cf = $('#clearFocus'); if(cf) cf.onclick = ()=>{ partyFocus=null; render(); };
  document.querySelectorAll('.stchip').forEach(b=>b.onclick=()=>{
    filters.uf=b.dataset.uf; render();
    const el=$('#states'); if(el) el.scrollIntoView({behavior:'smooth',block:'start'});
  });
}

/* ---------- mapa ---------- */
function tooltipFor(st, off){
  const o = st[off];
  const est = off==='governor' ? (o.estimate?[o.estimate]:[]) : o.estimate;
  const lines = est.filter(Boolean).map(e=>{
    const c = o.candidates.find(x=>x.name===e.name);
    return `${e.name} (${e.party}) — ${c?esc(c.pctDisplay):'—'} · índice ${Math.round(e.score)}`;
  });
  return `${st.estado} · ${off==='governor'?'Governador':'Senado'}\n` + (lines.join('\n') || '—');
}
function mapPanel(off){
  const tiles = Object.keys(FC.states).map(uf=>{
    const st = FC.states[uf], o = st[off];
    const [c,r] = UF_GRID[uf] || [1,1];
    const has = off==='governor' ? !!o.estimate : o.estimate.length;
    const wins = off==='governor' ? govWins(st,partyFocus) : senWins(st,partyFocus);
    const focus = partyFocus ? (wins?'hit':'dim') : '';
    return `<button class="tile ${o.stale?'stale':''} ${filters.uf===uf?'sel':''} ${focus}" style="grid-column:${c};grid-row:${r};background:${tileBg(st,off)}"
      data-uf="${uf}" data-tip="${esc(tooltipFor(st,off))}" aria-label="${esc(st.estado)}">
      ${uf}${has?'<span class="dot"></span>':''}</button>`;
  }).join('');
  const legend = colorMode==='bloco' ? blocLegend(off) : partyLegend(off);
  const title = off==='governor' ? 'Governador estimado por estado' : 'Senado — os 2 senadores estimados por estado';
  return `<section class="panel"><div class="panel-top"><h2>${title}</h2>
      <div class="toggle" id="colorToggle">
        <button data-m="bloco" class="${colorMode==='bloco'?'active':''}">Cor por bloco</button>
        <button data-m="partido" class="${colorMode==='partido'?'active':''}">Cor por partido</button>
      </div></div>
    <p class="desc">Toque num estado para ver só ele; passe o mouse para os percentuais. Hachurado = pode estar desatualizado.</p>
    <div class="mapwrap"><div class="tilemap" role="group" aria-label="Mapa do Brasil">${tiles}</div>
      <div class="legend">${legend}</div></div></section>`;
}
function blocLegend(off){
  const counts = {};
  Object.values(FC.states).forEach(st=>{const b=st[off].bloc; counts[b]=(counts[b]||0)+1;});
  const items = BLOC_ORDER.filter(b=>counts[b]).map(b=>
    `<div class="lg"><span class="sw" style="background:${blocColor(b)}"></span>${esc(blocLabel(b))}<span class="count">${counts[b]}</span></div>`).join('');
  return `<h3>Blocos (nº de estados)</h3>${items}`;
}
function partyLegend(off){
  const counts = {};
  Object.values(FC.states).forEach(st=>{const p=winnerParty(st,off); if(p) counts[p]=(counts[p]||0)+1;});
  const items = Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([p,n])=>
    `<button class="lg lgbtn ${partyFocus===p?'on':''}" data-party="${esc(p)}"><span class="sw" style="background:${partyColor(p)}"></span>${esc(p)}<span class="count">${n}</span></button>`).join('');
  return `<h3>Partidos — clique para ver onde vence</h3>${items}`;
}
function wireMap(off){
  const tip = $('#tooltip');
  document.querySelectorAll('#colorToggle button').forEach(b=>b.onclick=()=>{colorMode=b.dataset.m; render();});
  document.querySelectorAll('.tile').forEach(t=>{
    t.addEventListener('click', ()=>{ filters.uf = (filters.uf===t.dataset.uf ? 'ALL' : t.dataset.uf); render();
      const el=$('#states'); if(el) el.scrollIntoView({behavior:'smooth',block:'start'}); });
    t.addEventListener('pointermove', e=>{ tip.textContent = t.dataset.tip; tip.classList.add('on');
      tip.style.left = Math.min(e.clientX+12, innerWidth-250)+'px'; tip.style.top=(e.clientY+14)+'px'; });
    t.addEventListener('pointerleave', ()=> tip.classList.remove('on'));
  });
}

/* ---------- consolidado por partido ---------- */
function partyPanel(off){
  const counts = {};
  if(off==='governor') Object.values(FC.states).forEach(st=>{const p=st.governor.estimate?.party; if(p) counts[p]=(counts[p]||0)+1;});
  else Object.values(FC.states).forEach(st=>st.senate.estimate.forEach(e=>{counts[e.party]=(counts[e.party]||0)+1;}));
  const total = off==='governor' ? 27 : 54;
  const max = Math.max(...Object.values(counts), 1);
  const rows = Object.entries(counts).sort((a,b)=>b[1]-a[1]).map(([p,n])=>`
    <button class="ppbar ${partyFocus===p?'on':''}" data-party="${esc(p)}"><span class="ppname"><span class="sw" style="background:${partyColor(p)}"></span>${esc(p)}</span>
      <div class="bar"><i style="width:${100*n/max}%;background:${partyColor(p)}"></i></div><b>${n}</b></button>`).join('');
  const label = off==='governor' ? 'Governadores estimados por partido' : 'Cadeiras novas do Senado por partido (2 por estado)';
  return `<section class="panel"><h2>${label}</h2><p class="desc">Clique num partido para ver onde ele vence (${total} no total).</p>${rows}</section>`;
}

/* ---------- consolidado nacional (senado) ---------- */
function nationalPanel(){
  const rows = FC.national.filter(r=>r.sen2027>0||r.gov>0);
  const body = rows.map(r=>`
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
function controlsBar(){
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
function wireControls(){
  $('#f-uf').onchange = e=>{ filters.uf=e.target.value; refresh(); };
  $('#f-bloc').onchange = e=>{ filters.bloc=e.target.value; refresh(); };
  $('#f-q').oninput = e=>{ filters.q=e.target.value.toLowerCase(); refresh(); };
  $('#f-out').onchange = e=>{ filters.showOut=e.target.checked; refresh(); };
}
function refresh(){ $('#states').innerHTML = statesList(office()); wireDetails(); }

/* ---------- estados ---------- */
function candMatch(c){
  if(filters.bloc!=='ALL' && c.bloc!==filters.bloc) return false;
  if(!filters.showOut && !c.active) return false;
  if(filters.q && !(`${c.name} ${c.party}`.toLowerCase().includes(filters.q))) return false;
  return true;
}
function statesList(off){
  const ufs = Object.keys(FC.states).sort((a,b)=>FC.states[a].estado.localeCompare(FC.states[b].estado,'pt-BR'))
    .filter(uf=>filters.uf==='ALL'||filters.uf===uf);
  const out = ufs.map(uf=>stateCard(uf, off)).filter(Boolean).join('');
  return out || `<p class="loading">Nenhum resultado com esses filtros.</p>`;
}
function stateCard(uf, off){
  const st = FC.states[uf], o = st[off];
  const cands = o.candidates.filter(candMatch);
  if(!cands.length) return '';
  const label = off==='governor' ? 'Governador' : 'Senado · 2 vagas';
  return `<section class="state" id="state-${uf}">
    <div class="state-head"><h2>${esc(st.estado)} · ${label}</h2></div>
    ${estimateBox(uf, off)}
    ${off==='senate' ? competeBand(o) : ''}
    <div class="cards">${cands.map(c=>candRow(c, off)).join('')}</div>
  </section>`;
}
function estimateBox(uf, off){
  const o = FC.states[uf][off];
  const who = off==='governor'
    ? (o.estimate ? `<span class="blocchip" style="background:${blocColor(o.estimate.bloc)}">${esc(blocLabel(o.estimate.bloc))}</span> <strong>${esc(o.estimate.name)}</strong> <span class="badge" style="background:${partyColor(o.estimate.party)}">${esc(o.estimate.party)}</span>` : '—')
    : o.estimate.map(e=>`<span class="blocchip" style="background:${blocColor(e.bloc)}">${esc(e.party)}</span> <strong>${esc(e.name)}</strong>`).join(' &nbsp;+&nbsp; ');
  const w = off==='governor'
    ? `pesos: governador ${(o.weights.gov*100|0)}% · presidente ${(o.weights.pres*100|0)}%`
    : `pesos: Senado ${(o.weights.senado*100|0)}% · gov. ${(o.weights.governo*100|0)}% · pres. ${(o.weights.presidente*100|0)}% · apoio ${(o.weights.apoio*100|0)}%`;
  return `<div class="estimate">
    <div><strong>★ ${off==='governor'?'Governador estimado':'Senadores estimados'}</strong>
      <div class="who">${who}</div><div class="meta2">${w}${o.stale?' · <span class="pill stale">pode estar desatualizado</span>':''}</div></div>
    <div class="certainty"><span class="muted">certeza</span><b>${esc(o.certainty||'—')}</b>${o.may_change?`<div class="muted">${o.may_change}% podem mudar</div>`:''}</div>
  </div>`;
}
function competeBand(o){
  const polled = o.candidates.filter(c=>c.active && num(c.pct)).sort((a,b)=>b.pct-a.pct).slice(0,4);
  if(polled.length<2) return '';
  return `<div class="compete"><b>Pesquisa do Senado — faixa competitiva</b>
    <div class="chips">${polled.map(c=>`<span class="chip">${esc(c.name)} · ${esc(c.pctDisplay)}</span>`).join('')}</div></div>`;
}
function candRow(c, off){
  const comps = c.components || {};
  const compBar = Object.keys(COMP_COLOR).filter(k=>comps[k]>0)
    .map(k=>`<i style="flex:${comps[k]};background:${COMP_COLOR[k]}" title="${COMP_LABEL[k]}: ${comps[k]}"></i>`).join('');
  const pctBar = num(c.pct) ? `<div class="pollbar"><i style="width:${Math.min(100,c.pct)}%"></i></div>` : '';
  const est = c.estimated ? `<span class="won">★ estimado · ${esc(c.certainty_preview||'')}</span>` : '';
  const apoio = c.apoio_verificado ? `<span class="win-badge">${esc(c.apoio)}</span>` : (c.apoio ? esc(c.apoio) : 'apoio não verificado');
  const src = c.fonte ? ` · <a class="src" href="${esc(c.fonte)}" target="_blank" rel="noopener">pesquisa ↗</a>` : '';
  const key = `${c.uf}|${c.cargo}|${c.name}`;
  const open = openCards.has(key);
  return `<div class="cand ${c.estimated?'est':''} ${c.active?'':'out'} ${open?'open':''}" data-key="${esc(key)}">
    <div class="cand-main">
      <div class="name">${esc(c.name)} <span class="badge" style="background:${partyColor(c.party)}">${esc(c.party)}</span>
        <span class="blocchip" style="background:${blocColor(c.bloc)}">${esc(blocLabel(c.bloc))}</span></div>
      <div class="meta2">${apoio} · ${esc(c.instituto||'')} ${esc(c.campo||'')}${src}</div>
      ${est?`<div style="margin-top:4px">${est}</div>`:''}
    </div>
    <div class="pollbox"><div class="pct">${esc(c.pctDisplay||'—')}</div>${pctBar}</div>
    <div class="scorebox"><div class="score">${Math.round(c.score)}<small>índice</small></div><div class="comp">${compBar}</div>
      <button class="det-toggle" data-key="${esc(key)}">${open?'ocultar':'como foi calculado ▾'}</button></div>
    <div class="cand-detail">${open?factorDetail(c, off):''}</div>
  </div>`;
}
function factorDetail(c, off){
  const m = c.model; if(!m) return '<div class="muted">Sem detalhamento (candidato sem índice).</div>';
  const sc=m.scores, cp=c.components, w=m.weights, inp=m.inputs;
  const line = (label, input, key, note) =>
    `<div class="frow"><div class="fl"><b>${label}</b> <span class="fi">${input}</span>${note?`<div class="fnote">${note}</div>`:''}</div>
      <div class="fc">S ${Math.round(sc[key]??0)} × ${Math.round((w[key==='governo'?'governo':key]??w[key])*100)}% = <b>${(cp[key]??0).toFixed(1)}</b></div></div>`;
  let rows;
  if(off==='governor'){
    rows = [
      line('Pesquisa do governador', inp.gov_pct!=null?fpct(inp.gov_pct):'sem pesquisa', 'governo'),
      line('Presidente no estado', `${esc(blocLabel(inp.pres_bloc))} ${inp.pres_pct!=null?fpct(inp.pres_pct):'—'}`, 'presidente',
           'Usa o % REAL do bloco (não 0/1): 5pp de vantagem entram proporcionalmente.'),
    ];
  } else {
    rows = [
      line('Governador da chapa', `${esc(inp.gov_ticket||'—')}${inp.gov_pct!=null?' · '+fpct(inp.gov_pct):''}`, 'governo'),
      line('Presidente no estado', `${esc(blocLabel(inp.pres_bloc))} ${inp.pres_pct!=null?fpct(inp.pres_pct):'—'}`, 'presidente',
           'Usa o % REAL do bloco (não 0/1): 5pp de vantagem entram proporcionalmente.'),
      line('Pesquisa do Senado', `normalizada em ${Math.round(inp.sen_norm||0)}/100 (líder do estado = 100)`, 'senado'),
      line('Apoio / chapa', esc(inp.endorsement||'—'), 'apoio'),
    ];
  }
  return `<div class="detail-inner">${rows.join('')}
    <div class="frow ftot"><div class="fl"><b>Índice</b></div><div class="fc"><b>${Math.round(c.score)}</b> (0–100, para ordenar — não é probabilidade)</div></div></div>`;
}
function wireDetails(){
  document.querySelectorAll('.det-toggle').forEach(b=>b.onclick=(e)=>{
    e.stopPropagation();
    const key=b.dataset.key;
    if(openCards.has(key)) openCards.delete(key); else openCards.add(key);
    refresh();
  });
}

/* ---------- presidente ---------- */
function trendArrow(trend, bloc){
  if(!trend || trend[bloc]==null) return '';
  const d = trend[bloc];
  if(Math.abs(d) < 0.3) return ' <span class="muted" title="estável">→</span>';
  return d>0 ? ` <span style="color:#166534" title="subindo">▲${d}</span>`
             : ` <span style="color:#9f1239" title="caindo">▼${Math.abs(d)}</span>`;
}
function renderPresident(){
  const nat = PRES && PRES.national;
  let head;
  if(nat && nat.first_round && nat.first_round.length){
    const fr = nat.first_round, max = Math.max(...fr.map(c=>c.avg), 1);
    const bars = fr.map(c=>`<div class="prow">
      <span class="pname"><span class="badge" style="background:${partyColor(c.party)}">${esc(c.party)}</span> ${esc(c.name)}</span>
      <div class="bar"><i style="width:${100*c.avg/max}%;background:${blocColor(c.bloc)}"></i></div>
      <b>${c.avg}%${trendArrow(nat.trend, c.bloc)}</b></div>`).join('');
    const ro = nat.runoff || {};
    const roHtml = (ro['Lula']!=null && ro['Flávio']!=null) ? `
      <div class="runoff"><div class="rlabel">2º turno (média): <b>${ro['Lula']>=ro['Flávio']?'Lula':'Flávio'} lidera por ${Math.abs(ro['Lula']-ro['Flávio']).toFixed(1)} pp</b></div>
        <div class="rbar"><span style="flex:${ro['Lula']};background:${blocColor('Lula')}">Lula ${ro['Lula']}%</span><span style="flex:${ro['Flávio']};background:${blocColor('Flávio')}">${ro['Flávio']}% Flávio</span></div></div>` : '';
    head = `<section class="panel"><h2 style="margin:0 0 4px">Presidente — agregado nacional (poll-of-polls)</h2>
      <p class="desc">Média de ${nat.polls} pesquisas recentes (${esc((nat.institutos||[]).join(', '))}). Mais recente: ${esc(nat.latest_date||'—')}. Setas = tendência na janela.</p>
      <div class="pres1t">${bars}</div>${roHtml}</section>`;
  } else {
    head = `<section class="panel note"><h2 style="margin-top:0">Presidente — agregado nacional</h2>
      <p class="desc" style="margin:0">Nenhuma pesquisa presidencial coletada nesta rodada (rode <code>py -m pipeline.collect</code>).</p></section>`;
  }
  const lean = (PRES && PRES.pres_lean) || {};
  const ufs = Object.keys(lean).sort((a,b)=>(FC.states[a]?.estado||a).localeCompare(FC.states[b]?.estado||b,'pt-BR'));
  const cards = ufs.map(uf=>{
    const l = lean[uf]; const segs = ['Lula','Flávio','Caiado','Zema'].filter(b=>l[b])
      .map(b=>`<span style="flex:${l[b]};background:${blocColor(b)}" title="${b}: ${l[b]}%"></span>`).join('');
    return `<div class="pl"><b>${esc(FC.states[uf]?.estado||uf)}</b>
      <div class="track">${segs}</div>
      <div class="meta2">Lula ${l.Lula??'—'}% · Flávio ${l['Flávio']??'—'}% <span class="muted">(${esc(l.basis||'')})</span></div></div>`;
  }).join('');
  return head + `<section class="panel"><h2>Inclinação presidencial por estado</h2>
    <p class="desc">Alimenta os modelos de governador e senado (sempre com o % real). Pesquisa estadual quando há; senão proxy de 2022.</p>
    <div class="pres-lean">${cards}</div></section>`;
}
