/* Public poll catalog and descriptive charts. Scores remain a separate model. */
let RESEARCH = null;
let researchFilters = {office:'ALL', uf:'ALL', turn:'ALL', status:'ALL', query:''};
const researchNumber = v => v == null ? '—' : Number(v).toLocaleString('pt-BR', {maximumFractionDigits:1});
const researchDate = v => v ? (/^\d{4}-\d{2}-\d{2}$/.test(v) ? v.split('-').reverse().join('/') : esc(v)) : 'não informado';
function researchLink(url, label){
  try { const u = new URL(url); if(!['https:', 'http:'].includes(u.protocol)) return esc(label); }
  catch { return esc(label); }
  return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)} ↗</a>`;
}
function researchHealth(o){
  const r = o.research;
  if(!r) return '';
  const missing = [...r.missing_candidates, ...r.unmapped_candidates];
  return `<div class="research-health ${r.stale?'research-warning':''}">
    <b>${r.fallback?'Sem agregado comparável do Plano Político':`${r.polls} pesquisas · ${r.institutes.length} institutos`}</b>
    <span>Último campo: ${researchDate(r.latest_field)}${r.age_days!=null?` · há ${r.age_days} dias`:''}${r.stale?' · dados antigos ou insuficientes':''}</span>
    <details><summary>Cobertura e limitações</summary>
      <p>${r.institutes.length?esc(r.institutes.join(', ')):'Base anterior preservada como referência.'}</p>
      ${r.vote_format?`<p>Formato: ${esc(r.vote_format)}.</p>`:''}
      <p>${r.excluded} cenários com inconsistências, fora do cálculo.</p>
      ${missing.length?`<p>Sem correspondência completa entre cenário e candidaturas: ${missing.map(esc).join(', ')}. Ausência de pesquisa não significa zero voto.</p>`:''}
      ${r.estimated_base?'<p>Há conversão aproximada herdada da base anterior.</p>':''}
      ${o.race?`<p>${r.has_runoff?`Há pesquisa do duelo usado no modelo. Último campo: ${researchDate(r.runoff_latest_field)}.`:'Não há pesquisa do duelo usado no modelo; consulte o critério da estimativa.'}</p>`:''}
    </details></div>`;
}
function researchChart(agg, title, polls=[]){
  if(!agg?.history?.length) return '';
  const entries = Object.entries(agg.shares).filter(([n])=>!['Outros','Indecisos'].includes(n)).sort((a,b)=>b[1]-a[1]).slice(0,4);
  const colors = ['#0e7490','#b45309','#7c3aed','#be185d'];
  const W=720,H=260,L=40,R=18,T=12,B=30;
  const dates = agg.history.map(p=>Date.parse(p.date));
  const start = Math.min(...dates), end = Math.max(...dates);
  const x = d=>L+(Date.parse(d)-start)/Math.max(86400000,end-start)*(W-L-R);
  const y = v=>T+(100-Math.max(0,Math.min(100,v)))/100*(H-T-B);
  const grid = [0,25,50,75,100].map(v=>`<line x1="${L}" x2="${W-R}" y1="${y(v)}" y2="${y(v)}" stroke="#e2e8f0"/><text x="${L-6}" y="${y(v)+4}" text-anchor="end">${v}</text>`).join('');
  const paths = entries.map(([name], i)=>{
    const points = agg.history.filter(p=>p.shares[name]!=null);
    const band = points.filter(p=>p.intervals?.[name]);
    const area = band.length>1?`<polygon points="${band.map(p=>`${x(p.date)},${y(p.intervals[name][0])}`).concat([...band].reverse().map(p=>`${x(p.date)},${y(p.intervals[name][1])}`)).join(' ')}" fill="${colors[i]}" opacity=".12"/>`:'';
    const line = `<polyline fill="none" stroke="${colors[i]}" stroke-width="2.5" points="${points.map(p=>`${x(p.date)},${y(p.shares[name])}`).join(' ')}"/>`;
    const dots = polls.filter(p=>p.eligible && p.scenario_key===agg.scenario_key && p.valid_shares[name]!=null && Date.parse(p.field_end)>=start && Date.parse(p.field_end)<=end)
      .map(p=>`<circle cx="${x(p.field_end)}" cy="${y(p.valid_shares[name])}" r="3.5" fill="${colors[i]}" opacity=".6" tabindex="0"><title>${esc(name)} · ${researchNumber(p.valid_shares[name])}% · ${esc(p.pollster)} · ${researchDate(p.field_end)}</title></circle>`).join('');
    return area+line+dots;
  }).join('');
  return `<section class="research-chart"><h3>${esc(title)}</h3>
    <div class="research-legend">${entries.map(([n,v],i)=>`<span><i style="background:${colors[i]}"></i>${esc(n)} ${researchNumber(v)}%</span>`).join('')}</div>
    <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(title)}: médias em votos válidos, escala de zero a cem por cento"><title>${esc(title)}</title>${grid}${paths}
      <text x="${L}" y="${H-5}">${researchDate(agg.history[0].date)}</text><text x="${W-R}" y="${H-5}" text-anchor="end">${researchDate(agg.history.at(-1).date)}</text></svg>
    <p class="chart-reading" role="status">Selecione um ponto para consultar a pesquisa.</p>
    <p class="desc">Linhas: médias de pesquisas comparáveis. Pontos: pesquisas individuais (toque ou foco para detalhes). Faixas: dispersão de 90% por reamostragem de institutos, disponível com pelo menos 3 institutos. Não é intervalo de previsão da eleição. A composição de institutos pode variar ao longo do gráfico.</p>
    <details><summary>Valores do gráfico em tabela</summary><div class="logwrap"><table class="logtbl"><thead><tr><th>Data</th>${entries.map(([n])=>`<th>${esc(n)}</th>`).join('')}</tr></thead><tbody>${agg.history.map(p=>`<tr><td>${researchDate(p.date)}</td>${entries.map(([n])=>`<td>${researchNumber(p.shares[n])}%</td>`).join('')}</tr>`).join('')}</tbody></table></div></details>
  </section>`;
}
for(const event of ['click','focusin']) document.addEventListener(event,e=>{
  const point=e.target.closest?.('.research-chart circle');
  if(point) point.closest('.research-chart').querySelector('.chart-reading').textContent=point.querySelector('title').textContent;
});
function researchStateChart(uf, off){
  if(!RESEARCH) return '';
  const cargo=off==='governor'?'Governo':'Senado';
  return researchChart(RESEARCH.races[`${uf}:${cargo}`], 'Evolução das pesquisas — votos válidos', RESEARCH.polls.filter(p=>p.uf===uf&&p.cargo===cargo&&p.scenario==='1º turno'));
}
function researchPresPanel(){
  const nat=PRES?.national, agg=nat?.research;
  if(!agg) return '';
  const trend = [7,14].map(days=>{
    const rows=Object.entries(agg.trends[String(days)] || {}).filter(([n])=>!['Outros','Indecisos'].includes(n));
    return `<div><b>Variação em ${days} dias</b>${rows.length?`<ul>${rows.map(([name,t])=>`<li>${esc(name)}: ${t.delta>0?'+':''}${researchNumber(t.delta)} p.p. (${t.institutes} institutos em comum)</li>`).join('')}</ul>`:'<p>Dados comparáveis insuficientes.</p>'}</div>`;
  }).join('');
  return `<section class="panel"><h2>Tendência presidencial</h2><div class="research-trends">${trend}</div>
    <p class="desc">Compara médias dos mesmos institutos e do mesmo cenário em duas datas. Exige novas observações em ao menos dois institutos; cada instituto tem o mesmo peso na variação. Diferenças fixas entre institutos não viram crescimento eleitoral.</p>
    ${researchChart(agg,'Presidente — últimos 60 dias',(RESEARCH?.polls||[]).filter(p=>p.uf==='BR'&&p.cargo==='Presidente'&&p.scenario==='1º turno'))}</section>`;
}
function researchComparison(uf,off){
  const actual=RAW.states[uf][off], current=FC.states[uf][off];
  const names=o=>off==='governor'?[o.estimate?.name].filter(Boolean):o.estimate.map(c=>c.name);
  const cargo=off==='governor'?'Governo':'Senado';
  const agg=RESEARCH?.races[`${uf}:${cargo}`];
  if(!agg) return '';
  const leaders=Object.entries(agg.shares).filter(([n])=>!['Outros','Indecisos'].includes(n)).sort((a,b)=>b[1]-a[1]).slice(0,off==='governor'?1:2);
  return `<div class="research-comparison"><div><b>Pesquisas · 1º turno</b><span>${leaders.map(([n,v])=>`${esc(n)} ${researchNumber(v)}%`).join(' · ')||'Sem agregado'}</span></div>
    <div><b>Estimativa do modelo</b><span>${names(actual).map(esc).join(' + ')||'Indisponível'}</span></div>
    <div><b>Cenário simulado</b><span>${simActive()?names(current).map(esc).join(' + '):'Ative o simulador para comparar'}</span></div></div>`;
}
function researchCatalog(){
  if(!RESEARCH) return '<p>Catálogo indisponível.</p>';
  const c=RESEARCH.counts, f=researchFilters;
  const option=(v,label,current)=>`<option value="${esc(v)}" ${v===current?'selected':''}>${esc(label)}</option>`;
  const rows=RESEARCH.polls.filter(p=>(f.office==='ALL'||p.cargo===f.office)&&(f.uf==='ALL'||p.uf===f.uf)&&
    (f.turn==='ALL'||p.scenario===f.turn)&&
    (f.status==='ALL'||(f.status==='used'?p.in_aggregate:f.status==='excluded'?!p.eligible:p.eligible&&!p.in_aggregate))&&
    (!f.query||`${p.registro} ${p.pollster} ${Object.keys(p.shares).join(' ')}`.toLocaleLowerCase('pt-BR').includes(f.query.toLocaleLowerCase('pt-BR'))))
    .sort((a,b)=>(b.field_end||'').localeCompare(a.field_end||''));
  return `<section class="panel"><h2>Base de pesquisas</h2>
    <p>${c.registrations} registros TSE · ${c.scenarios} cenários · ${c.excluded} cenários fora dos cálculos por inconsistência ou retirada da fonte.</p>
    <p class="desc">Coleta: ${researchLink('https://planopolitico.com.br/agregador/','Plano Político')}. Os percentuais abaixo são os disponibilizados pelo agregador; no Senado já vêm normalizados. Uma pesquisa pode conter vários cenários, cargos e turnos.</p>
    <details><summary>Fontes, atualização e metodologia</summary>
      ${Object.entries(RESEARCH.sources).map(([name,s])=>`<p>${researchLink(s.url||'',name)}: ${s.status==='ok'?'consulta concluída':'falha de coleta — usando histórico'} · fonte atualizada em ${researchDate(s.updated_at)} · consultada em ${researchDate(s.checked_at)}</p>`).join('')}
      <p>Janela de 30 dias em relação à última pesquisa do cenário; meia-vida de 14 dias. O peso total de cada instituto é limitado ao de sua pesquisa mais recente. Não usamos uma nota histórica de qualidade ou correção de viés sem validação própria.</p>
      <p>Agregamos um mesmo conjunto de candidatos por turno e formato de voto. A conversão usa a soma dos candidatos, incluindo “Outros”, dentro de cada pesquisa. Ausências permanecem ausências. Dados acima de 14 dias recebem aviso.</p>
      <p>${esc(RESEARCH.method.interval)}</p></details>
    <div class="research-filters">
      <label>Cargo<select id="research-office">${['ALL','Presidente','Governo','Senado'].map(v=>option(v,v==='ALL'?'Todos':v,f.office)).join('')}</select></label>
      <label>Abrangência<select id="research-uf">${['ALL','BR',...Object.keys(RAW.states).sort()].map(v=>option(v,v==='ALL'?'Todas':v==='BR'?'Brasil':v,f.uf)).join('')}</select></label>
      <label>Turno<select id="research-turn">${['ALL','1º turno','2º turno'].map(v=>option(v,v==='ALL'?'Todos':v,f.turn)).join('')}</select></label>
      <label>Situação<select id="research-status">${[['ALL','Todas'],['used','Usadas no agregado de 1º turno'],['excluded','Com inconsistência / retiradas'],['archive','Outros cenários e histórico']].map(([v,l])=>option(v,l,f.status)).join('')}</select></label>
      <label>Instituto, registro ou candidato<input id="research-query" value="${esc(f.query)}" type="search"></label>
    </div><p>${rows.length} cenários encontrados. Exibindo até 100; refine os filtros para consultar os demais.</p>
    <div class="research-catalog">${rows.slice(0,100).map(p=>`<details class="research-poll"><summary><b>${esc(p.pollster)}</b> · ${p.uf} · ${esc(p.cargo)} · ${esc(p.scenario)} · ${researchDate(p.field_end)} <span class="pill ${p.eligible?'':'stale'}">${p.in_aggregate?'usada no 1º turno':p.eligible?'histórico / outro cenário':'fora do cálculo'}</span></summary>
      <p><b>${esc(p.registro||'Registro não informado')}</b> · campo ${researchDate(p.field_start)} a ${researchDate(p.field_end)} · divulgação ${researchDate(p.published_at)} · amostra ${esc(p.sample_size??'não informada')} · ${esc(p.method||'método não informado')}</p>
      <p>${researchLink(p.url,'Fonte original')} · ${researchLink(p.source_url,'Página do Plano Político')} · base ${esc(p.base)} · ${esc(p.vote_format)}</p>
      ${p.issues.length?`<p class="research-warning">${p.issues.map(esc).join('; ')}</p>`:''}
      <div class="logwrap"><table class="logtbl"><thead><tr><th>Candidato / resposta</th><th>Disponibilizado pela fonte</th><th>Votos válidos usados</th></tr></thead><tbody>${Object.entries(p.shares).map(([n,v])=>`<tr><td>${esc(n)}</td><td>${v==null?'não medido':researchNumber(v)+'%'}</td><td>${p.valid_shares[n]==null?'—':researchNumber(p.valid_shares[n])+'%'}</td></tr>`).join('')}</tbody></table></div></details>`).join('')||'<p>Nenhuma pesquisa corresponde aos filtros.</p>'}</div></section>`;
}
function researchChanges(){
  const c=RESEARCH?.changes;
  if(!c?.date) return '';
  return `<details class="upbanner"><summary>O que mudou na base · ${researchDate(c.date)}</summary><p>${c.added} cenários adicionados · ${c.revised} revisados.</p><p>${esc(c.note)}</p>${c.methodology?'<p>Metodologia pesquisas-2: cenários separados, peso limitado por instituto, tendência com institutos em comum e idade dos dados por disputa. Alterações do modelo de ordenação continuam separadas da coleta.</p>':''}</details>`;
}
function wireResearchCatalog(){
  for(const [id,key] of [['office','office'],['uf','uf'],['turn','turn'],['status','status']]){
    document.getElementById(`research-${id}`)?.addEventListener('change',e=>{researchFilters[key]=e.target.value; render(); saveResearchLocation();});
  }
  document.getElementById('research-query')?.addEventListener('change',e=>{researchFilters.query=e.target.value;render();saveResearchLocation();});
}
function saveResearchLocation(){
  const q=new URLSearchParams(); q.set('aba',tab);
  if(filters.uf!=='ALL') q.set('uf',filters.uf);
  if(tab==='ma'){q.set('media_uf',maFilter.uf);q.set('media_cargo',maFilter.cargo);}
  if(tab==='log') for(const [k,v] of Object.entries(researchFilters)) if(v && v!=='ALL') q.set(`pesquisa_${k}`,v);
  for(const k of ['pres','gov','sen']) if(sim[k]) q.set(k,String(sim[k]));
  history.replaceState(null,'',`${location.pathname}?${q}`);
}
function restoreResearchLocation(){
  const q=new URLSearchParams(location.search);
  if(['gov','sen','pres','log','ma'].includes(q.get('aba'))) tab=q.get('aba');
  if(RAW.states[q.get('uf')]) filters.uf=q.get('uf');
  if(RAW.states[q.get('media_uf')]) maFilter.uf=q.get('media_uf');
  if(['Governo','Senado'].includes(q.get('media_cargo'))) maFilter.cargo=q.get('media_cargo');
  for(const k of ['pres','gov','sen']) {const v=Number(q.get(k)); if(Number.isFinite(v)) sim[k]=Math.max(-10,Math.min(10,v));}
  for(const k of Object.keys(researchFilters)) if(q.has(`pesquisa_${k}`)) researchFilters[k]=q.get(`pesquisa_${k}`);
  document.querySelectorAll('#tabs button').forEach(b=>{b.classList.toggle('active',b.dataset.tab===tab);b.setAttribute('aria-selected',String(b.dataset.tab===tab));});
}
