# Eleições 2026 — previsão (presidente · governadores · senadores)

Site estático/PWA que projeta, por estado, o **governador** e as **2 vagas de Senado**, além de um
**agregado nacional presidencial**. Um pipeline em Python coleta as pesquisas mais recentes, recalcula os
modelos e emite JSON que o site lê. Uma automação semanal (GitHub Actions) roda até o 1º turno
(**04/10/2026**) e republica sozinha.

## Como funciona o modelo

Índice 0-100 para **ordenar** candidatos (não é probabilidade calibrada). Componentes:

```
S = reliability · min(100, pct / 0,6)     # governador e presidente (satura em 60%)
S_sen  = pesquisa do Senado normalizada (líder do estado = 100)
S_apoio = {explícito:100, chapa/aliança:90, inferido:45, não verificado:0}
score  = Σ pesoᵢ · Sᵢ
```

Os **pesos variam no tempo** (curva côncava — pesquisas ficam mais confiáveis perto da eleição):

- **Governador:** pesquisa do governador domina; influência presidencial cai de **0,20 → 0,03** (teto 0,25).
- **Senado:** peso da pesquisa própria cresce **0,15 → 0,50** (teto rígido 0,55), modulado pra baixo por
  volatilidade ("pode mudar o voto"). O resto vai pra chapa (governador + presidente + apoio).

Pesos ancorados na literatura (Jennings & Wlezien 2018; Erikson & Wlezien; Borges & Lloyd 2016)
e nas viradas de Senado de 2018/2022.

**Backtest (`pipeline/backtest/`, `py -m pipeline.backtest.run`):** nos casos documentados de erro
de pesquisa (PR/MG/SP 2018, SP/PR 2022), o modelo ponderado por chapa fica **comparável à pesquisa
pura**, não a supera — essas viradas foram puxadas por volatilidade tardia (indeciso decidindo no
fim), que um sinal estrutural não prevê. Conclusão honesta: o índice serve para **ordenar** (é bom
onde a pesquisa é fraca/precoce), mas **não é um corretor de erro de pesquisa**; por isso o teto do
Senado é mantido **moderado (~0,50)** — nem 1,0 (pesquisa pura) nem baixo demais. A amostra do
backtest é pequena e enviesada (casos notórios); uma calibração definitiva exigiria raspar todos os
pleitos de 2018/2022.

**Momentum (movimento de última hora):** adicionar um termo de momentum (rebaixar quem cai, valorizar
quem sobe nas pesquisas recentes) recupera as viradas documentadas (2/8 → 7/8). Confirma a *direção*
(a literatura mostra que indecisos/terceira via decidem nas últimas 2 semanas), mas o teste é
**in-sample** (as trajetórias refletem o resultado conhecido) e parte do momentum é ruído/reversão.
Por isso o momentum entra como termo **pequeno e time-gated** (ativo só nos últimos ~14 dias),
calculado a partir da **série real** de snapshots que o coletor acumula — dormente a 56 dias da
eleição. Validação out-of-sample exige o scrape histórico completo (viável: a pt.wiki tem as séries).

## Estrutura

```
data/polls/  snapshots de pesquisas (entradas do modelo)
reference/   roster.yaml (candidatos·partido·bloco·apoio), parties.yaml (cores)
pipeline/    Python — sources/ (coleta), schedule.py, model.py, president.py, validate.py, build.py, backtest/, tests/
docs/        site estático publicado no GitHub Pages (index.html, app.js, styles.css, data/, PWA)
assets/      logo.svg / icon.svg
.github/workflows/update.yml   cron semanal ATIVO: coleta → recalcula → publica
```

Publicado via **GitHub Pages** servindo a pasta `docs/` da branch `main` — cada push de dados republica.

## Rodar localmente (Windows)

```sh
py -m venv .venv
.venv/Scripts/python -m pip install -r pipeline/requirements.txt
.venv/Scripts/python -m pytest          # testes do modelo/cronograma
.venv/Scripts/python -m pipeline.build  # gera docs/data/forecast.json e docs/data/president.json
py -m http.server -d docs 8000          # abre o site em http://localhost:8000
```
