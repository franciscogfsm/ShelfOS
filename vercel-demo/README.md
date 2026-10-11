# ShelfOS — demo para Vercel

Esta pasta já está compilada. Não precisa de Python, modelos, GPU, chaves nem npm install.

Publicar a partir desta pasta:

    npx vercel --prod

No painel Vercel, também podes importar um repositório que contenha apenas esta pasta.
Framework: Other. Output Directory: public. Build Command: vazio.

Depois de publicar:
- Web normal / QR: https://TEU-DOMINIO.vercel.app/
- Colaboradores / QR: https://TEU-DOMINIO.vercel.app/colaboradores

Inclui os 181 frames do dia, produtos, caixas clicáveis, detalhes, replay, analytics e tarefas.
A página dos colaboradores simula a confirmação da reposição. Não executa inferência nova,
contagem, avaliação de maturação ou chat AI sem o backend.

Para voltar a gerar esta pasta: npm --prefix web run package:vercel
