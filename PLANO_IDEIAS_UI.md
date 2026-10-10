# Plano — 4 ideias de UI para nos destacarmos

Base: o que já está no repo (`web/` Next.js 16, `shelfos/` motor + servidor, README de 10 out). Cada ideia é feita, testada e fechada antes de começar a seguinte.

## Antes de tudo: o que estas ideias valem

- **Pontos oficiais: zero.** A pontuação só olha para `planogram_compliant` e `stock_value`. A UI/UX (1–5) só desempata.
- **Condição para começar:** o motor está estável (CV no README: 82,9 % e 88,4 % do máximo). Se houver trabalho de pontuação em aberto, esse tem prioridade.
- **Orçamento total: ~7 h**, de preferência uma só pessoa (o resto da equipa continua no motor).
- **Se faltar tempo, cortar por esta ordem:** 4 → 1 → 3. A ideia 2 é a que mais vale.

### Regra de segurança para as 4 ideias (não negociável)

Tudo vive em `web/`. **Nada em `shelfos/`, `run.py` ou `tools/` que toque nas previsões.** Antes de cada merge:

```bash
# 1. As previsões têm de ficar idênticas, byte a byte
python run.py --images data/images --out /tmp/antes.json    # no commit anterior
python run.py --images data/images --out /tmp/depois.json   # no commit novo
cmp /tmp/antes.json /tmp/depois.json && echo "previsões intactas"
git diff --stat main -- shelfos/ run.py                     # tem de vir vazio

# 2. A UI compila
cd web && npm run lint && npm run build
```

### Ordem proposta (diferente da do colega, e porquê)

| # | Ideia | Custo | Porquê nesta posição |
|---|---|---|---|
| 1.º | Planograma fantasma | ~2 h | Responde diretamente ao critério do brief ("quão clara e rapidamente o staff vê o que fazer"). Só frontend, risco baixo. |
| 2.º | "Se fizeres isto" | ~1,5 h | Barato; dá a estrutura de "tarefas agrupadas" que o briefing falado vai ler. |
| 3.º | Previsão de rutura | ~3 h | A mais impressionante, mas a mais arriscada (poucos dados por área, ver abaixo). Tem de ser validada antes de ir para o palco. |
| 4.º | Briefing falado | ~1 h | Depende das tarefas da ideia 2. Bonito, mas o mais fácil de cortar. |

---

## Ideia A — Planograma fantasma (fazer 1.º)

**O que o staff vê:** num slot vazio ou com o produto errado, aparece por cima, semitransparente, o aspeto que esse slot tinha quando estava cheio e correto.

**Porque é barato:** as câmaras são fixas, por isso uma frame antiga da mesma câmara alinha-se pixel a pixel com a atual. **Não é preciso warp nenhum**: basta desenhar a frame de referência recortada pelo quadrilátero da área (`clipPath` SVG). Coordenadas negativas não são problema: o SVG corta no `viewBox`.

**Ficheiros**
- `web/app/lib.ts` — nova função pura `referenceFrame(cam, areaId): Frame | null`:
  só frames de referência (`origin !== "run"`), status `ok`, `source !== "memory"`; escolhe a de maior `probs[2] − (obstruction ?? 0)` (mais cheia e menos tapada).
- `web/app/components.tsx` — em `FrameView`, para áreas `empty`/`wrong`: `<clipPath>` com `points(a.quad)` + `<image href={frameSrc(ref)} opacity≈0.5>` por baixo do contorno colorido. Botão "Mostrar planograma" (ligado por defeito) e, no `AreaDetail`, o mesmo fantasma no recorte.
- Fallback se a área nunca esteve `ok` no dia: ilustração do produto (`ProductImage`, já existe) centrada no quadrilátero, com a etiqueta "esperado: <produto>".

**Passos**
1. `referenceFrame` + memoização por câmara (`useMemo`), para não recalcular a cada render.
2. Desenhar o fantasma só em `FrameView` (vista grande, não `compact`).
3. Toggle + fantasma no `AreaDetail`.
4. Verificar à mão: 1 área vazia, 1 com produto errado, 1 área com coordenadas negativas (câmara 6383, prateleira de cima), 1 área sem frame `ok` (fallback).

**Pronto quando:** numa área vazia vê-se o produto esperado alinhado com a prateleira, sem "saltos"; a página continua fluida com as 14 câmaras.

**Riscos:** pré-carregar a imagem de referência duplica downloads (mitigar: só carregar quando a área tem problema); a frame de referência pode ter luz diferente (aceitável, é só uma pista visual).

---

## Ideia B — "Se fizeres isto" (fazer 2.º)

**O que o staff vê:** "Loja 81 % em forma · fazer as 3 primeiras tarefas → 84 %". Cada tarefa mostra o seu ganho.

**Métrica:** **reutilizar** a que já existe na análise ("Share of areas full and in place" = áreas `ok` / total). Assim o número é o mesmo em todos os ecrãs e é defensável. Nada de métricas novas inventadas.

**Correção de honestidade ao exemplo do colega:** com 152 áreas, cada área resolvida vale ≈ +0,7 pp. "3 tarefas → de 81 % para 94 %" só é possível ao nível de uma câmara, nunca da loja. No palco usamos os números reais.

**Problema a resolver:** se cada área vale o mesmo, "ordenar por impacto" dá exatamente a ordem atual. O que torna isto útil é **agrupar por viagem**: uma tarefa = um produto + uma ação ("Repor Banana — 3 slots, +2,0 pp"), porque o repositor vai ao armazém uma vez por produto.

**Ficheiros**
- `web/app/lib.ts` — `storeHealth(store, ts)` e `trips(tasks)`: agrupa `Task[]` por `(productId, status)`; ganho = nº de áreas do grupo / total de áreas.
- `web/app/page.tsx` — barra no topo com a nota atual e a nota "depois das próximas N"; ganho em cada tarefa.

**Ordenação:** mantém-se a regra do projeto (vazio → produto errado → meio). Dentro do mesmo estado: grupos maiores primeiro. Depois da ideia C, desempatar pela velocidade de venda (o que vende mais depressa primeiro).

**Simplificação assumida:** uma tarefa feita = áreas passam a `ok`. Uma área "errada e a meio" corrigida ficaria `low`; ignoramos e dizemo-lo se perguntarem.

**Pronto quando:** a soma dos ganhos de todas as tarefas leva a nota a 100 %; os números batem certo com o gráfico "Compliant" da análise no mesmo instante.

---

## Ideia C — Previsão de rutura (fazer 3.º, só se A e B estiverem fechadas)

**O que o staff vê:** num slot "Low": "≈ esvazia por volta das 16h45". E uma secção "Vai esvaziar na próxima hora" com os slots a repor **antes** de ficarem vazios.

**Limite dos dados (decide tudo):** cada câmara tem **12–14 capturas por dia, uma a cada ~65–70 min, das ~06h às ~19h40**. Entre "cheio" e "vazio" uma área tem muitas vezes só 2–3 pontos. A previsão vai ter erro de ±1 h na melhor das hipóteses e vai faltar em muitos slots. Mostramos o horário arredondado a 15 min com "≈" e nunca inventamos uma previsão sem dados.

**Algoritmo (simples e explicável ao júri)**
1. Sinal de enchimento por frame: `fill = 0,5·P(half) + 1·P(full)` (vem das probabilidades calibradas que já temos). Variante a testar depois, uma mudança de cada vez: `occ`.
2. Segmento atual: frames desde a última reposição (subida de `fill` > 0,25 entre capturas seguidas). Excluir frames com `obstruction > 0,3` ou `source === "memory"`.
3. Se há ≥ 3 pontos e a reta (mínimos quadrados) desce: hora prevista = quando a reta cruza `θ_empty`.
4. Só mostrar se a previsão cai nas próximas 8 h; caso contrário "estável".
5. `MIN_POINTS`, `RESTOCK_JUMP`, `θ_empty`, `MAX_HORIZON` como constantes no topo do ficheiro, nunca espalhadas no código.

**Ficheiros**
- `web/app/forecast.ts` — função pura `forecast(cam, areaId, ts)`, só com `import type` de `./lib` (para poder ser corrida fora do Next).
- `web/app/components.tsx` / `page.tsx` — chip "≈ 16h45" nas tarefas `low` e no `AreaDetail`; secção "Vai esvaziar em breve".
- `tools/forecast_backtest.ts` — **validação obrigatória antes de ir para o palco:** para cada área e cada instante *t* do dia, prever usando só frames ≤ *t*, e comparar com a primeira frame realmente vazia. Reporta: nº de previsões, erro mediano (min), % dentro de ±60 min.
  Correr com `node --experimental-strip-types tools/forecast_backtest.ts` (Node ≥ 22.6). **A confirmar** na máquina de quem fizer; alternativa: `npx tsx`.

**Critério de decisão (fixar antes de ver o resultado):**
- erro mediano ≤ 60 min e ≥ 15 previsões → mostrar a hora e usar o número no pitch;
- pior que isso → trocar para **ritmo de venda** sem extrapolar ("desceu de cheio a meio em 2 h") ou cortar.

**Pergunta em aberto Q6 (uso de frames vizinhas):** esta ideia usa frames anteriores, mas **só na UI**. Nunca pode entrar em `predictions.json` enquanto Q6 não tiver resposta. A regra de segurança acima (`cmp` das previsões) garante isto.

**No pitch, evitar** a frase "todos os outros só mostram o que já correu mal": não sabemos o que as outras equipas fazem.

---

## Ideia D — Briefing falado (fazer 4.º, a primeira a cortar)

**O que o staff ouve:** um botão "Ouvir resumo" lê, em ~20 s: "3 slots vazios, 2 com produto errado. Primeiro: repor Banana, câmara 6215, 3 slots…" (as 5 primeiras viagens da ideia B).

**Tecnologia:** Web Speech API do browser (`window.speechSynthesis` + `SpeechSynthesisUtterance`). Sem dependências, sem rede. As vozes carregam de forma assíncrona (`getVoices()` + evento `voiceschanged`).

**Decisão para a equipa — língua:** a UI está em inglês, mas os nomes dos produtos são portugueses ("Banana", "Laranja", "Couve Flor") e uma voz inglesa pronuncia-os mal. Proposta: briefing em pt-PT (é o staff do Continente em Leiria). **Precisa de OK.**

**Ficheiros**
- `web/app/briefing.ts` — `briefingText(trips)` (texto puro, testável) + `speak(text)`.
- `web/app/page.tsx` — botão Ouvir/Parar no cabeçalho.

**Regras:** se não houver nenhuma voz `pt` no browser, o botão não aparece (nada de funcionalidades partidas na demo). Botão Parar sempre visível enquanto fala.

**Riscos:** a qualidade e a existência de vozes variam por SO e browser (Chrome em Linux pode não ter nenhuma). **Testar no portátil e no browser exatos da demo.** Numa sala barulhenta pode nem se ouvir: ter a demo pronta sem som.

---

## Resumo do que cada ideia toca

| Ideia | Ficheiros novos | Ficheiros alterados | Toca nas previsões? |
|---|---|---|---|
| A Fantasma | — | `lib.ts`, `components.tsx` | Não |
| B Impacto | — | `lib.ts`, `page.tsx` | Não |
| C Rutura | `forecast.ts`, `tools/forecast_backtest.ts` | `components.tsx`, `page.tsx` | Não (Q6) |
| D Falado | `briefing.ts` | `page.tsx` | Não |
