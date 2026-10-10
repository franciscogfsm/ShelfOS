# ShelfOS: como funciona o modelo (para o pitch deck)

Tudo o que está aqui foi tirado do código e dos ficheiros do projeto a 10 Out 2026.
Os números de resultados são medidos contra as nossas próprias etiquetas, não contra a
validação oficial, e têm de ser ditos assim no pitch.

## Numa frase

O ShelfOS não treina uma rede neuronal. Usa um modelo de visão já treinado e congelado
(DINOv3) para "ver" cada área da prateleira, e por cima treina classificadores pequenos
com um dia real da loja, etiquetado por nós à mão.

## O fluxo (para o diagrama)

```
Foto da câmara de teto + planograma
        │
        ▼
1. Recorte      cada área do planograma é endireitada para um quadrado de 224 px
        │
        ▼
2. Visão        DINOv3 ViT-B + ViT-L, congelados (sem fine-tuning)
        │       1 imagem = cerca de 12 áreas = 1 passagem pelo modelo
        ├──────────────────┬──────────────────────┐
        ▼                  ▼                      ▼
3. Ocupação        4. Memória da prateleira   6. Produto
   que parte da       compara com a mesma        compara com o protótipo do
   área tem           área quando estava         produto esperado e com os
   produto e que      cheia e quando             outros 93 produtos
   parte é caixa      estava vazia
        │                  │                      │
        └────────┬─────────┘                      │
                 ▼                                ▼
5. Nível de stock                         Produto certo ou errado
   vazio / meio / cheio                   (e com o que se parece)
                 │                                │
                 └───────────────┬────────────────┘
                                 ▼
              predictions.json (formato oficial) + lista de tarefas na app
```

## Com que dados foi treinado

| O quê | Quanto |
| --- | --- |
| Câmaras | 14 (fixas, de teto) |
| Fotos do dia de referência | 181 |
| Áreas do planograma | 153 |
| Recortes etiquetados | 1950 |
| Produtos diferentes | 94 |

- Os dados são só os do desafio: um dia real da secção de Frutas e Legumes.
- O dataset veio sem etiquetas. Fizemo-las nós: uma primeira passagem feita com IA
  (Claude, a olho, sobre tiras de imagens) e depois corrigida por pessoas da equipa com
  uma ferramenta de etiquetagem que construímos. As 38 áreas em que os revisores
  discordaram foram resolvidas uma a uma.
- A parte de visão (DINOv3) vem pré-treinada pela Meta e não foi alterada.

## O que é treinado por nós

| Peça | Tipo | Para quê |
| --- | --- | --- |
| Ocupação | classificador linear por patch (grelha 14x14) | separar produto de caixa, tabuleiro, cartão |
| Memória | comparação patch a patch com o histórico da mesma área | medir quanto mudou, mesmo sem conhecer o produto |
| Stock | gradient-boosted trees | decidir vazio / meio / cheio |
| Produto | um protótipo por produto | decidir se está lá o produto certo |

O treino completo demora cerca de um minuto numa GPU de portátil (RTX 4050).

## Duas ideias que valem um slide

1. **A câmara não se mexe.** Como a mesma área aparece sempre no mesmo sítio, comparamos
   cada foto com a mesma área cheia e vazia. É isto que faz funcionar as fotos do fim do
   dia.
2. **Decide a pensar na pontuação.** Errar por cima custa 3 pontos e por baixo custa 2.
   O modelo escolhe o nível com a melhor pontuação esperada, por isso uma prateleira na
   dúvida é dada como "meio" e não como "cheio".

## Imagens geradas por IA: sim, mas só para testar

- **O modelo que entregamos foi treinado só com fotos reais.** Nenhuma imagem gerada por
  IA entra no treino.
- Geramos imagens com IA para o atacar: produto errado na caixa, quase vazio, mãos e
  carrinhos à frente, embalagens diferentes. O plano cobre 16 cenários em 6 câmaras;
  há 119 imagens na ferramenta de revisão.
- Testámos treinar com alguns recortes sintéticos. O ganho foi pequeno e não ficou
  provado, por isso não foi para produção.
- Estes testes mostraram onde o modelo é fraco (produto errado e prateleiras quase
  vazias). Não usem números destes testes como "precisão": são casos escolhidos para
  serem difíceis.

## Casos difíceis que a app aguenta

- Ficheiros soltos sem pasta: a câmara é reconhecida pela própria imagem.
- Zip com ou sem pasta, com lixo do macOS: aberto e limpo.
- Outra resolução, PNG, preto e branco: convertido e analisado.
- Imagem corrompida: todas as áreas são respondidas na mesma, a partir do último estado
  conhecido, e ficam assinaladas (uma área em falta custa 5 pontos).
- Imagem na pasta da câmara errada: aviso com a câmara com que se parece.
- Áreas parcialmente fora da imagem: a parte de fora é ignorada.
- Mão ou carrinho à frente: não conta como produto.

## Onde há IA generativa na app

Só no assistente de conversa (ShelfOS AI, Gemini via OpenRouter). Recebe as respostas do
modelo em texto e explica-as. Não vê as fotos e não decide nenhuma resposta: as
previsões entregues vêm todas do modelo de visão.

## Números que podem dizer

- Velocidade medida: cerca de 1 s por imagem no modelo completo e 0,4 s no leve (GPU de
  portátil, medição com ruído).
- Tudo corre localmente: `python run.py`, sem nuvem para as previsões.
- Validação interna da tarde de 10 Out, contra as nossas etiquetas (README): 91,8% de
  stock certo e 99,0% de produto certo nas duas últimas fotos de cada câmara (304 áreas).
  O classificador de stock mudou depois disso; voltar a correr `python tools/cv.py` antes
  de pôr um número no slide.

## O que não dizer

- Não dizer "precisão de X%" sem acrescentar "nas nossas etiquetas". A pontuação oficial
  só existe quando os organizadores correrem a validação escondida.
- Não dizer que treinámos uma rede neuronal nem que fizemos fine-tuning.
- Não dizer que o modelo foi treinado com dados sintéticos.
