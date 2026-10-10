# Labeler

Ferramenta para rever labels à mão. Não faz parte do programa final: tudo o que é de rotulagem vive nesta pasta. Só usa Python standard, nada para instalar.

```bash
python3 labeler/app.py --name rodrigo     # câmaras 6215 … 6386 (7 primeiras)
python3 labeler/app.py --name francisco   # câmaras 6443 … 6781 (7 últimas)
```
Abre http://localhost:8765 no browser. Cada nome só vê as suas 7 câmaras (definido em `TEAM` no `app.py`). Outro nome vê todas; `--cameras 6215,6371` ou `--cameras all` força outras.

Na primeira vez extrai as imagens do zip para `labeler/data/` (ignorado pelo git). Cada área já vem pré-preenchida com `labels/silver_labels.txt`; só corriges o que está mal.

## Como usar
Cada ecrã = uma área do planograma ao longo do dia inteiro (12–14 fotos). Em cima, a foto escolhida com a área a azul e um zoom. Em baixo, uma tira com todas as horas.

| Tecla | Ação |
| --- | --- |
| `←` `→` | escolher a foto |
| `1` `2` `3` (ou `E` `H` `F`) | vazio / meio / cheio, avança para a foto seguinte |
| `4` | tapado / não dá para ver |
| `5` `6` `7` | produto certo / outro produto (ou `X`) / produto desconhecido |
| `U` | incerto |
| `Shift` + qualquer uma acima | aplica a esta foto **e a todas as seguintes** |
| `Enter` | área confirmada → próxima por rever |
| `Backspace` | área anterior |

São as mesmas teclas 1–7 da antiga `tools/label_review.py`. Também dá para fazer tudo com o rato.

## Regras de stock (iguais para os dois!)
Escolhe o nível **mais próximo** de quanto da área está ocupado com produto:

| Ocupado | Label |
| --- | --- |
| menos de ~25% (só uns poucos itens, 80–90% vazio) | **vazio** |
| ~25% a ~75% | **meio** |
| mais de ~75% (parece acabado de repor) | **cheio** |

Dá a tua melhor estimativa honesta. **Não puxes o stock para baixo aqui**: isso é feito depois, na decisão do modelo. Ainda não sabemos como a Sensei definiu os limites (pergunta Q5 aos mentores); se responderem, muda-se aqui.

## Ficheiros (cada pessoa tem os seus, sem conflitos no git)
- `labels/<nome>.json`: o teu progresso (podes fechar e voltar quando quiseres).
- `output/<nome>_annotations.json`: **output no formato oficial exato**, com as 1.962 áreas (as não revistas ficam com o pré-preenchimento).
- `output/<nome>_annotations_reviewed.json`: só as áreas que confirmaste com `Enter`.
- `docs/`: regras para o LLM / decisão final.

## Juntar e passar para o modelo
```bash
python3 labeler/app.py --merge rodrigo francisco   # -> output/merged_annotations.json
python3 labeler/app.py --apply rodrigo francisco   # escreve as áreas revistas em labels/silver_labels.txt
```
`--apply` é o que o modelo (`shelfos`) usa para treinar. Só uma pessoa o corre, depois de fazer `git pull` aos ficheiros da outra. Faz backup em `labeler/backups/`, mantém intactas as fotos em que ninguém mexeu, e recusa escrever se alguém alterou essa área do silver entretanto.

Opção: `--prefill previsoes.json` para rever as previsões do modelo em vez do silver.
