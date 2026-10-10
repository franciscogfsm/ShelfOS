# Brief para Fable: corrigir falhas concretas sem tornar o modelo pesado

Mantém o backbone atual e começa pelas cabeças pequenas. Já temos um benchmark reproduzível de casos difíceis, com imagens e etiquetas revistas. Não precisamos de substituir tudo nem adicionar outro modelo grande à inferência.

## O que falha

No modelo full de produção, apenas **3/7 áreas com produto errado** foram identificadas como não conformes. No caso controlado `controlled_wrong_product`, área `6443_1`, uma caixa cheia de bananas substitui tomates: o modelo responde `full`, `compliant=True`, com probabilidade de conformidade de cerca de 0.86. É o exemplo prioritário. Ver `controlled/6443/wrong_product.png` e o recorte em `outputs/edgecases/crops/controlled_wrong_product/6443_1.jpg`.

Há outro caminho de erro: produto errado pode ser classificado como vazio e, por regra, isso força conformidade. Acontece em `existing_6462_41a9628f / 6462_9` e `existing_6591_c17d8229 / 6591_1`. A regra oficial de vazio conforme deve manter-se; corrigir a identificação incorreta de vazio, sem usar inconformidade para caixas realmente vazias.

O full acerta apenas **3/9 casos de stock reduzido**. Há erros nos dois sentidos: `controlled_depletion / 6443_13` tem stock reduzido mas é previsto full; várias áreas antigas com alguma fruta são previstas empty. Também há caixas cheias previstas half. A fronteira half/full precisa de validação humana; estas etiquetas são locais, não oficiais.

**Embalagens sem fruta passaram 5/5**. Evitar gastar o primeiro esforço numa falha que este conjunto não demonstrou. Ocultação por uma mão foi testada para conformidade, mas a quantidade escondida não tem etiqueta de stock fiável.

## Experiência já feita

Foram geradas oito variantes controladas: quatro testes na câmara 6443 e quatro exemplos de treino na 6468 (ananás vazio, reduzido, cheio e só embalagens). Refiz apenas a cabeça de stock, com peso 0.25 para os quatro exemplos de treino:

| Avaliação independente | Baseline | Candidate |
|---|---:|---:|
| Holdout real, 304 áreas | 442/608 | 450/608 |
| Teste sintético separado | 36/83 | 40/83 |

Ganho pequeno mas medido: +8 pontos reais e +4 sintéticos. Conformidade não mudou, porque essa cabeça não foi treinada. Checkpoints experimentais em `models/edgecases/`; produção não foi substituída. Só um split real e quatro exemplos sintéticos: não promover ainda.

## O que tentar a seguir, por ordem

1. **Negativos difíceis de produto errado.** Criar um conjunto TRAIN separado de caixas realmente ocupadas com produtos trocados, em várias câmaras do treino. Rever o que foi gerado. Testar uma cabeça pequena de conformidade que use as features existentes, o desvio face ao produto esperado e a diferença para os protótipos concorrentes. Medir se o prior da área está a dominar a evidência visual. Manter positivos com mãos, embalagens, variedades legítimas e caixas vazias para evitar novos falsos alarmes.
2. **Stock com informação espacial dos patches atuais.** Testar cobertura/contiguidade em grelha 2x2 ou 4x4, usando os mesmos embeddings, para separar algumas frutas grandes de uma caixa cheia e reduzir influência da caixa vizinha. Auditar os polígonos antes de concluir que a cabeça está errada: imagens antigas geradas podem deslocar os cestos. São hipóteses a testar, não melhorias já demonstradas.
3. **Treino sintético com controlo.** Começar com baixo peso, comparar ablações com/sem sintéticos e vários splits temporais reais. Uma imagem original e todas as suas variantes têm de ficar no mesmo split. Não treinar nos testes deste manifesto. Validar a fronteira half/full com mentores e acrescentar recortes reais das mesmas falhas.

Critério para aceitar: mais pontos pelas penalizações oficiais no holdout real e nos cenários difíceis independentes, sem piorar caixas vazias/embalagens nem aumentar materialmente a latência p95. Medir latência numa GPU sem outras tarefas; os tempos atuais têm ruído de concorrência. Reutilizar patches pode evitar outra passagem de visão, mas qualquer custo novo tem de ser medido.

## Comandos e revisão

```powershell
python tools/edgecases.py
python tools/edgecase_train.py
python tools/edgecases.py --models models/edgecases/edge_baseline.pkl models/edgecases/edge_candidate.pkl --out outputs/edgecase_training/comparison
```

Comparação visual com botão Failures: `outputs/edgecases/review.html`. Comparação do treino: `outputs/edgecase_training/comparison/review.html`. Manifesto e prompts estão nesta pasta. Os scores sintéticos são diagnósticos de um conjunto difícil selecionado; não representam a precisão em loja nem a avaliação oficial.
