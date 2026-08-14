# Eleições 2026 — previsão (presidente · governadores · senadores)

Site estático/PWA que projeta, por estado, o **governador** e as **2 vagas de Senado**, além de um
**agregado nacional presidencial**. Um pipeline em Python coleta as pesquisas mais recentes, recalcula os
modelos e emite JSON que o site lê. Uma automação **diária** (GitHub Actions) roda até o 1º turno
(**04/10/2026**) e republica sozinha.

## Base das pesquisas: tudo em votos válidos

Institutos publicam em bases diferentes — uns sobre o **total de entrevistados** (branco/nulo e indeciso
dentro da conta), outros já sobre os **votos válidos**. Somar as duas mistura escalas: 45% de totais com
10% de indeciso é 50% de válidos. Cada pesquisa coletada guarda a base em que foi publicada, a soma dos
candidatos e o branco/nulo/indeciso, e o modelo trabalha sobre `pct_valid = % ÷ soma dos candidatos`.
O site mostra os dois números (publicado e válidos) e a tabela completa da conta quando você isola um estado.

No Senado a conversão vale como **share das menções válidas**: alguns institutos publicam só o "1º voto"
(soma ~90) e outros o "1º e 2º voto" (soma ~150) — dividir pela soma põe as duas na mesma escala. O
`sen_norm` (líder do estado = 100) é calculado sobre essa base.

**Cenários não se misturam.** 1º turno, 2º turno e espontânea são perguntas diferentes; a chave da média
móvel inclui o cenário. Listas de rejeição ("em quem não votaria") são descartadas — somam >100.

**Instituto é quem fez a pesquisa, não quem publicou.** A Gazeta do Povo é veículo; creditar tudo a ela
fundiria Datafolha e Paraná Pesquisas na mesma série. O instituto sai do slug da matéria
(`pipeline/sources/gazeta.py: pollster_from`).

## Governador: a eleição tem dois turnos

Ordenar pelo 1º turno e coroar o líder é o erro clássico — quem lidera com 40% em campo dividido perde o
2º turno com frequência. `model.governor_race` decide como a eleição decide:

1. líder com **≥ 50% dos válidos** → eleito no 1º turno;
2. senão, os dois primeiros vão ao 2º turno e, havendo **pesquisa daquele par**, é ela que decide;
3. sem pesquisa do duelo, o índice (chapa + presidente) desempata.

Na rodada de 14/08/2026: 10 estados decididos no 1º turno, 10 por pesquisa de 2º turno (em **PA e TO** o
líder do 1º turno perde o duelo), 3 por índice sem duelo e 4 sem pesquisa comparável.

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
calculado a partir da **série real** de snapshots que o coletor acumula — dormente a 56 dias da eleição.

**Validação out-of-sample (2018):** o scraper histórico (`pipeline/backtest/scrape_history.py` +
`backtest_oos.py`) raspa a série de pesquisas ao Senado da Wikipedia PT (grid p/ rowspans) e os
**eleitos** (top-2 por votos na tabela de resultado), cobrindo **14 estados**. Com o momentum **REAL**
(pesquisa final − de ~3 semanas antes, sem hindsight), a acurácia sobe de **17/28 (pesquisa pura) para
20/28** (61% → 71%) com peso de momentum **0,5–1,5**, e volta a cair em 2,0 (overfit). Ou seja, o
momentum **melhora a previsão out-of-sample** — e o pico confirma manter o peso **pequeno (~1,0**, o
default de produção). Amostra limitada aos estados com pesquisa+resultado tabulados na Wikipedia; uma
validação ainda mais ampla usaria a base oficial do TSE.

## Atualização diária e mudanças de candidatura

O cron roda **todo dia às 09:00 BRT**: sincroniza candidaturas → coleta pesquisas → recalcula → publica.
Duas datas passaram a ser distintas no `forecast.json`, porque com cadência diária elas se descolam:

- `generated_at` — a **rodada** (manda nos pesos, que mudam todo dia até 04/10);
- `polls_date` — até quando vão as **pesquisas** do snapshot.

Quando um dia não traz nada novo, o `collect` **não grava snapshot** (compara uma assinatura dos campos
materiais), então `data/polls/` continua sendo uma série de mudanças reais, não 50 cópias iguais.

**`reference/roster.yaml` é a fonte única de candidaturas.** Para registrar uma mudança (troca de cargo,
desistência, novo nome) basta editar o YAML — nada de mexer em snapshot na mão:

```sh
py -m pipeline.roster_sync --dry-run   # relata o que mudaria
py -m pipeline.roster_sync             # aplica ao snapshot e grava a rodada de hoje
py -m pipeline.build                   # republica
```

O `roster_sync` (`pipeline/roster_sync.py`) faz o snapshot obedecer ao roster: quem está no roster e não
no snapshot vira registro novo; quem sumiu do roster fica `active: false` (some da estimativa, mas o
histórico de pesquisas continua); partido/bloco/apoio vêm do roster. Troca de cargo cai nos dois casos e
é reportada. Ele ainda **funde duplicatas** ("Angelo"/"Ângelo" — o fantasma sem pesquisa pontuava pelo
apoio e podia entrar no top-2), **limpa `gov_ticket`** apontando para governador que saiu da disputa, e
**para o pipeline** se o roster tiver nome duplicado. É passo próprio no workflow, sem rede: uma edição
de candidatura entra no ar mesmo com os scrapers fora do ar.

Limite conhecido: quem troca de cargo chega ao novo cargo **sem pesquisa** e o índice não tem prior para
isso — fica no fim da lista até sair a primeira pesquisa do novo pleito.

### Campo político (esquerda x direita)

Duas populações, dois critérios:

- **54 em disputa** — entram pelo **bloco declarado da candidatura** (quem o candidato apoia para
  presidente), curado candidato a candidato em `roster.yaml`.
- **27 que ficam** (mandato até 2031) — não têm candidatura. Classificar por partido erra: o mesmo
  partido tem senador do campo Lula e do campo oposto. Cada um é classificado individualmente em
  `roster.holdovers` com `criterio` + `basis`: **verificado** (cargo formal que define o campo —
  ministro/vice de Lula ou de Bolsonaro), **atuação** (posição pública consistente, quando o partido
  classificaria errado) ou **partido** (inferência, o elo mais fraco).

Hoje são 8 verificados, 6 por atuação e 13 por partido. A tabela inteira, com o critério de cada um,
fica aberta na aba Senado — o que é inferência aparece marcado como inferência.

### Conferência contra o TSE

`pipeline/tse_check.py` baixa os [dados abertos do TSE](https://dadosabertos.tse.jus.br/dataset/candidatos-2026)
(`consulta_cand_2026.zip`, ~3 MB, regerado todo dia) e compara o registro **oficial** de candidatura com o
roster. É a única fonte autoritativa de quem de fato pediu registro — imprensa e Wikipedia atrasam e
divergem, ainda mais na semana do prazo (**15/08/2026, 19h**).

```sh
py -m pipeline.tse_check           # A) registrado no TSE e fora do roster; B) roster sem registro
py -m pipeline.tse_check --todos   # inclui partidos fora de reference/parties.yaml
```

Ele **não aplica nada** — o roster é curado (só candidatura competitiva entra, senão o índice enche de nome
com 0 pesquisa). Roda como passo do cron e o log da Action vira a lista do que revisar. Antes do prazo,
"no roster e sem registro no TSE" quase sempre é registro ainda não protocolado; **depois do prazo**, é
candidatura que não existe.

## Estrutura

```
data/polls/  snapshots de pesquisas (entradas do modelo)
reference/   roster.yaml (candidatos·partido·bloco·apoio) — FONTE ÚNICA de candidaturas; parties.yaml (cores)
pipeline/    Python — sources/ (coleta), roster_sync.py, schedule.py, model.py, president.py, validate.py, build.py, backtest/, tests/
docs/        site estático publicado no GitHub Pages (index.html, app.js, styles.css, data/, PWA)
assets/      logo.svg / icon.svg
.github/workflows/update.yml   cron DIÁRIO ATIVO: roster → coleta → recalcula → publica
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
