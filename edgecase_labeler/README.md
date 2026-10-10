# Labeler dos edge cases

```powershell
python edgecase_labeler/app.py --name marti
```

Abre automaticamente http://127.0.0.1:8767. Se essa porta estiver ocupada, usa `--port 8770`. É um servidor local, só com Python standard; abrir o HTML diretamente não permite guardar no disco.

Mostra as 119 imagens dos edge cases, a área do planograma selecionada e uma ampliação. Filtra por câmara, cenário ou split. As etiquetas propostas são pré-preenchidas, mas **não contam como revisão humana**. Cada área é confirmada separadamente. Quantidades tapadas e fronteiras ambíguas podem ser excluídas com um motivo.

- `1/2/3`: vazio/meio/cheio; `4`: stock não visível.
- `5/6/7`: produto certo/outro produto/não identificável.
- `U`: incerto; `Enter`: confirmar a área e avançar.
- Setas: imagem anterior/seguinte. Também há botões para todas as ações.

Guarda automaticamente a cada alteração:

- `output/<nome>_progress.json`: progresso completo, incluindo notas, exclusões e propostas ainda não confirmadas.
- `output/<nome>_reviewed_manifest.json`: apenas etiquetas explicitamente confirmadas, sem incerteza e sem exclusão. Inclui `complete_human_review` para distinguir imagens completas de revisão parcial.

O botão **Exportar revistas** descarrega o mesmo manifesto para partilhar. Usa outro `--name` para outro revisor; os ficheiros ficam separados. Juntar revisores requer resolver os desacordos, não sobrescrever automaticamente.

Mantém as etiquetas do dataset original, checkpoints e manifesto inicial intactos. Não aplica as correções automaticamente ao treino. O manifesto revisto é compatível com `tools/edgecases.py`; não treinar no conjunto de teste.

As gravações são sequenciais no browser, atómicas no disco e protegidas contra alterações concorrentes noutra janela. Se aparecer erro, verifica o progresso guardado antes de fechar. O servidor precisa de estar em execução para gravar.

Usa a mesma convenção acordada no labeler original. As propostas sintéticas existentes seguem uma revisão local anterior e podem discordar dessas fronteiras: confirma o que realmente vês, incluindo todas as áreas da imagem, e resolve os limites com os mentores.
