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

Números calibrados por **backtest 2018/2022** e ancorados na literatura (Jennings & Wlezien 2018;
Erikson & Wlezien; Borges & Lloyd 2016). Ver `.claude/plans` / histórico para as fontes.

## Estrutura

```
data/        forecast.json, president.json e snapshots de pesquisas
reference/   roster.yaml (candidatos·partido·bloco·apoio), parties.yaml (cores)
pipeline/    Python — sources/ (coleta), schedule.py, model.py, president.py, validate.py, build.py, backtest/, tests/
web/         site estático (index.html, app.js, styles.css, brazil-map.svg, PWA)
assets/      logo.svg
.github/workflows/update.yml   # cron semanal
```

## Rodar localmente (Windows)

```sh
py -m venv .venv
.venv/Scripts/python -m pip install -r pipeline/requirements.txt
.venv/Scripts/python -m pytest          # testes do modelo/cronograma
.venv/Scripts/python -m pipeline.build  # gera data/forecast.json e data/president.json
py -m http.server -d web 8000           # abre o site em http://localhost:8000
```
