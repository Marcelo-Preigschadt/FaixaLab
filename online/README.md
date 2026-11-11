# FaixaLab Online — site e processamento separados

## API de áudio do FaixaLab

O mesmo servidor de processamento pode importar um link diretamente ou delegar a obtenção do áudio a uma instância própria. A API de áudio executa apenas `yt-dlp`. A separação, a cifra e a letra continuam no servidor principal.

No host da API, instale as dependências em um ambiente Python 3.12, configure `FAIXALAB_AUDIO_SOURCE_KEY` com uma chave aleatória e execute a partir de `app/`.

```bash
python -m pip install -r requirements-source.txt
python prepare_youtube.py
python -m faixalab.source_api --port 7870
```

Configure no servidor principal `FAIXALAB_AUDIO_SOURCE_URL` com a origem da API e `FAIXALAB_AUDIO_SOURCE_KEY` com a mesma chave. Use HTTPS para uma máquina remota e HTTP apenas no loopback. A API escuta no loopback por padrão. Para uma implantação remota, conecte o proxy HTTPS à porta 7870. `FAIXALAB_AUDIO_SOURCE_DATA` define a pasta persistente do cache de áudio por ID do vídeo.

| Rota | Resultado |
| --- | --- |
| `GET /v1/health` | Estado da API |
| `POST /v1/youtube-jobs` | Recebe `{"url":"https://www.youtube.com/watch?v=..."}` e retorna o ID e o estado |
| `GET /v1/youtube-jobs/{id}` | Consulta o processamento ou o resultado em cache |
| `GET /v1/youtube-jobs/{id}/audio` | Envia o arquivo quando estiver pronto |

Todas as rotas exigem `Authorization: Bearer <chave>`. A API reutiliza o áudio salvo do mesmo vídeo. A obtenção do áudio depende da resposta do YouTube ao host que executa a API.

O site usa a mesma interface e o mesmo player do aplicativo. As chamadas `/api/` passam por um gateway que conecta a interface ao servidor Python. O site não executa PyTorch. O navegador não recebe a chave do servidor de IA. Áudio e uploads são encaminhados como streams; HTTP Range 206 e a revisão da faixa são preservados.

## Estado desta etapa

A [interface foi publicada](https://faixalab-marcelo.nainho5.chatgpt.site) com acesso privado pela conta ChatGPT do proprietário. Código de conexão, validação de acesso, build do site e imagem do servidor estão preparados. **Ainda não há servidor de IA provisionado ou conectado; a separação não acontece online nesta etapa.** O Docker completo não foi construído neste ambiente, que não dispõe do executável Docker. O gateway foi exercitado com transporte simulado e o servidor foi testado por HTTP com arquivos WAV reais; isso não equivale a uma implantação do processamento em produção.

Validação desta etapa: dez verificações do gateway e três testes HTTP de acesso remoto aprovados, além das 15 regressões do player e do teste HTTP Range existente. A conexão considera o servidor pronto somente depois de uma consulta autenticada a `/api/connection`, e não apenas porque a sonda pública de saúde respondeu. O dicionário real e o catálogo dos instrumentos acompanham o site, sem depender do servidor de IA.

Mais quatro testes validam o download HTTPS, tamanho e integridade do pacote. O ZIP real foi conferido por tamanho, SHA-256 e CRC e seus seis modelos foram ligados ao código do servidor. No navegador, o dicionário exibiu as 1.047 cifras e 3.078 posições. Em uma viewport de 390 pixels, a largura do documento e a área rolável foram ambas 390 pixels. O endereço de produção confirmou a exigência de login ChatGPT; a sessão de teste não estava autenticada nessa produção. O teste visual foi realizado na prévia da mesma versão publicada. Não houve inferência em uma máquina de nuvem externa.

O repositório ainda não tem releases publicados. `release.json` identifica o ZIP completo 0.10.1 de 149.078.883 bytes, SHA-256 `892f7984c1fb5b8108cb7d801e4d5a54d20151cd73f226a8b2e00a8fa383ab80`. Antes de construir o servidor, esse mesmo arquivo precisa estar em uma URL HTTPS alcançável pela máquina da nuvem. A correção pequena do player não substitui esse pacote de modelos. O código do Git, incluindo a correção do player, é executado; o ZIP fornece os pesos binários.

## Configuração do servidor

Use um segredo aleatório longo para `FAIXALAB_API_KEY`. Não grave o valor no Git, em um Dockerfile ou na interface. A aplicação recusa iniciar em modo remoto sem esse segredo. Chamadas do gateway enviam `X-FaixaLab-Key`; consultas a projetos, arquivos e operações exigem a chave. `/api/health` informa disponibilidade sem listar músicas.

```sh
docker build -f cloud/Dockerfile --build-arg FAIXALAB_BUNDLE_URL=https://ENDERECO-DO-PACOTE/FaixaLab_0_10_1_Windows.zip -t faixalab-server .
docker run --rm -p 7860:7860 -e FAIXALAB_API_KEY -v faixalab-data:/data faixalab-server
```

O nome `FAIXALAB_API_KEY` no segundo comando herda o segredo do ambiente, sem colocá-lo no texto do comando. Os modelos maiores baixados em uso, projetos, áudio e caches ficam em `/data`; esse diretório precisa de armazenamento persistente no provedor. A imagem já prepara o runtime JavaScript e os modelos do pacote durante o build. O primeiro uso de Mega53 e letra ainda pode exigir os modelos maiores ausentes. Há um único worker de processamento, preservando o orçamento de memória.

Esta imagem é uma base **CPU**. Um serviço ZeroGPU/Gradio não é uma substituição direta deste container e precisa de adaptação e teste próprios; não foi anunciado suporte ZeroGPU funcional.

## Configuração do site

O destino de publicação é um Site privado do proprietário. O gateway exige a identidade fornecida por essa hospedagem. Nos segredos de runtime do site:

| Nome | Valor |
| --- | --- |
| `FAIXALAB_BACKEND_URL` | Origem HTTPS do servidor, sem caminho, query ou credenciais |
| `FAIXALAB_BACKEND_KEY` | Mesmo segredo configurado em `FAIXALAB_API_KEY` no servidor |

O build reutiliza os assets reais do app e os incorpora no Worker ESM. Ele não contém dados de exemplo ou processamento simulado na interface. Quando a configuração ou o servidor estão ausentes, o site informa o estado e bloqueia novas importações. No site, MP3s devem ter até 95 MB, respeitando o limite de entrada do proxy; o limite do aplicativo local continua igual.

```sh
node online/build.mjs /CAMINHO/DO/CHECKOUT-DO-SITE
node online/test_proxy.mjs
PYTHONPATH=app python -m unittest discover -s app/tests -p test_remote_access.py -v
```

As chamadas não dependem do endereço do computador do usuário. O processamento depende de um servidor de nuvem ativo. Suspensões e cotas do provedor não são contornadas por este código.

O acesso ao YouTube continua sujeito à disponibilidade do vídeo e à conexão do provedor. A entrada por MP3 permanece disponível quando o YouTube recusar esse acesso; não foi prometido download de qualquer vídeo a partir de qualquer datacenter.

## Opções sem cartão verificadas em 10/11/2026

- A documentação atual do Hugging Face exige plano pago para criar novos Docker/Gradio Spaces em compute. Contas gratuitas elegíveis, com e-mail verificado e mais de 30 dias, podem criar até dois Spaces ZeroGPU; a cota gratuita autenticada é de cinco minutos de GPU por dia. Essa cota é tempo de execução na GPU, não duração da música, e não é garantia de quantidade de músicas. Esse caminho requer outra integração.
- Lightning AI anuncia um Studio CPU gratuito com quatro núcleos e 16 GB, sem cartão, mas exige reinício manual a cada quatro horas. Os créditos iniciais sem cartão são cinco; os outros 25 exigem cartão. Não se trata de GPU gratuita ilimitada ou servidor com disponibilidade garantida.
- Nenhum desses limites foi ativado, alterado ou contornado. Não houve criação de assinatura, contratação de GPU ou configuração de pagamento.

Fontes: [Hugging Face Spaces](https://huggingface.co/docs/hub/spaces-overview), [ZeroGPU](https://huggingface.co/docs/hub/spaces-zerogpu), [Lightning AI](https://studio.lightning.ai/pricing/).

## Cadastro da Lightning bloqueado — observação de 10/11/2026

O fluxo de cadastro do usuário retornou: “We aren't accepting new sign-ups right now. Existing accounts can still sign in.” Isso impede essa nova conta de usar a oferta. A orientação anterior sobre aguardar verificação de e-mail não se aplica a esse aviso. As páginas de preços e ajuda ainda descrevem o plano, mas não comprovam que o cadastro esteja aberto. Não tratar a Lightning como hospedagem disponível para essa implantação enquanto o bloqueio persistir.

## Candidato a validar: execução por tarefas no Kaggle

A documentação oficial do Kaggle oferece GPU gratuita com cota semanal descrita como 30 horas, variável conforme demanda e recursos. A API oficial permite enviar código/notebooks para execução e consultar resultados. Isso permite estudar um processamento por música: enviar a tarefa, acompanhar seu estado e buscar as faixas ao concluir. Não se trata de hospedar o container FastAPI permanentemente.

Esse candidato ainda não está integrado ou testado no FaixaLab. Primeiro é necessário verificar cadastro, verificação da conta e GPU disponível na conta do usuário. O site publicado e o servidor Docker atual não foram alterados para fingir essa integração. Não usar as antigas referências a P100 como indicação de hardware atual: o Kaggle anunciou sua retirada em 15/09/2026; T4 ×2 é a alternativa documentada.

Referências: [cota e uso de GPU](https://www.kaggle.com/docs/efficient-gpu-usage), [API oficial](https://www.kaggle.com/docs/api), [execução de notebooks pela CLI oficial](https://github.com/Kaggle/kaggle-cli/blob/main/docs/kernels.md), [retirada da P100](https://www.kaggle.com/product-announcements/735239).
