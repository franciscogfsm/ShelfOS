# ShelfOS: custo e velocidade (resumo para o pitch)

Tudo corre localmente, dentro da loja. Nenhuma imagem vai para a cloud.

**Medido** = portátil com RTX 4050 6 GB. **Estimado** = contas nossas, ainda não testadas em Jetson.

## Velocidade (medido, RTX 4050)

| | Lite (ViT-B) | Full (ViT-B + ViT-L) |
|---|---|---|
| Tempo por imagem | ~0,4 s (mediana 371 ms) | ~1,1 s (média 1137 ms) |
| Tempo por área de prateleira | ~35 ms | ~100 ms |
| Débito | ~2,7 imagens/s | ~0,9 imagens/s |
| Câmaras por GPU, 1 foto/min | ~160 | ~50 |
| Câmaras por GPU, 1 foto a cada 5 min | ~800 | ~260 |

- Uma imagem tem em média 11 áreas (304 áreas em 28 imagens).
- O número do lite foi medido com a GPU partilhada com outros jobs, por isso tem ruído.
- Não há "FPS" de vídeo: o sistema analisa fotos, e uma prateleira muda em minutos. A métrica certa é câmaras por dispositivo.
- Retreinar com labels novas: ~1 min.

## Dispositivo na loja

| | Jetson Orin Nano Super 8 GB (estimado) | Portátil RTX 4050 (medido) |
|---|---|---|
| Preço do hardware | ~250–300 € | ~1 000 € |
| Consumo | 7–25 W (~15 W em média) | ~80–100 W em carga |
| Tempo por imagem (lite) | ~2 s | ~0,4 s |
| Câmaras a 1 foto/min | ~30 (2 lojas de 14 câmaras) | ~160 (11 lojas) |
| Eletricidade, ligado 24/7 | ~2 €/mês (~11 kWh) | ~12–15 €/mês |
| Energia por imagem | ~30 J (~0,008 Wh) | ~30 J |

- Uma loja de 14 câmaras a 1 foto/min usa cerca de metade de um Jetson.
- O modelo lite (86 M de parâmetros) ocupa menos de 1 GB de memória.
- O modelo full também cabe no Jetson, mas fica ~3x mais lento (~6 s por imagem).
- O Jetson Nano antigo (2019, 4 GB) não é recomendado: descontinuado e ~10 s ou mais por imagem.

## Custo por loja

| | Valor |
|---|---|
| Hardware (uma vez) | ~300 € |
| Eletricidade | ~2 €/mês |
| Total amortizado a 3 anos | **~10 €/mês** |
| Câmaras novas | 0 (usa as que a loja já tem) |
| Chamadas cloud para previsões | 0 |

## Frases para o slide

- "~0,4 s por imagem num portátil."
- "Corre numa caixa de 300 € e 15 W dentro da loja: ~2 € de eletricidade por mês."
- "Sem cloud: as imagens nunca saem da loja."

## Pressupostos

- Eletricidade a 0,20 €/kWh.
- Jetson 4–6x mais lento do que a RTX 4050; preço e consumo de memória, sem confirmar na loja da NVIDIA.
- Cadência de 1 foto por minuto por câmara (no dataset há cerca de 1 foto por hora).
- No slide, marcar os números do Jetson como "estimado".
