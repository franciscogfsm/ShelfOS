# Regras

Pontuação por área: identificação +1 / −2; stock certo +1, abaixo −2, acima −3; área em falta = −2 e −3.

## Completude
1. Responder SEMPRE a todas as áreas do planograma. Nunca "não sei", null ou em branco.
2. Não inventar area_ids.

## Stock (`empty` 0 / `half` 0.5 / `full` 1)
3. Em dúvida, escolher o nível MENOR. Só subir com >~60% de confiança.
4. `full` só se estiver claramente cheio (base não se vê); `empty` só se não houver produto ou quase nenhum.
5. Mãos, pessoas, carrinhos, caixas e etiquetas não são produto. Parte tapada = nível mais baixo plausível.
6. Avaliar só o quadrilátero da área (coordenadas negativas = só a parte visível).

## Planograma
7. Por defeito `planogram_compliant = true`.
8. `false` só com >~70% de confiança de que o produto visível é claramente outro.
9. Variedades parecidas, desarrumação ou invasão da área vizinha = `true`.
10. Área vazia = `true`.

## Método e output
11. Cada área é avaliada à parte; não copiar respostas entre áreas com o mesmo produto.
12. Responder só com JSON válido: `{camera: {imagem.jpg: {area_id: {planogram_compliant, stock_level, stock_value}}}}`.
