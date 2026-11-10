# FaixaLab 0.10.1

Separação de instrumentos, cifras, letra e tablatura com modelos públicos, para Windows ou servidor Linux. A versão 0.10 otimiza o processamento local e aproveita uma GPU NVIDIA existente quando o runtime é compatível. Os 33 candidatos automáticos e os pesos são preservados. Não cria recursos pagos na nuvem.

A correção 0.10.1 valida e prepara o runtime JavaScript usado pelo YouTube, prioriza o runtime privado sobre um Deno antigo do sistema e atualiza yt-dlp com o EJS correspondente. A falta desse runtime reproduziu o erro `This video is not available` no vídeo relatado. Isso não confirma, sem o diagnóstico do computador afetado, que seja a única causa do incidente. Verificações e limites: [app/VALIDACAO_0_10_1.md](app/VALIDACAO_0_10_1.md).

A atualização **playback1** corrige o ciclo de tocar, pausar para carregar e descartar o buffer. Há um pacote pequeno que atualiza somente a interface de uma instalação 0.10.1 e reaproveita os projetos e modelos. Testes e limites: [app/VALIDACAO_REPRODUCAO_0_10_1.md](app/VALIDACAO_REPRODUCAO_0_10_1.md).

## Versão online — primeira etapa

A [interface do FaixaLab Online](https://faixalab-marcelo.nainho5.chatgpt.site) foi publicada com acesso privado pela conta ChatGPT do proprietário. O dicionário real acompanha o site. **O servidor de IA ainda não foi provisionado ou conectado; o site informa esse estado e bloqueia novas importações.**

O gateway, a imagem CPU do servidor, a validação de acesso e os testes estão em [online/README.md](online/README.md). O site e a IA são serviços separados: este código não transforma GitHub Pages em servidor de modelos nem provisiona máquinas ou planos pagos. O aplicativo Windows continua funcionando como antes.

As medições e os limites da otimização estão em [app/VALIDACAO.md](app/VALIDACAO.md); a validação anterior foi preservada em [app/VALIDACAO_0_9.md](app/VALIDACAO_0_9.md). Os testes foram realizados em CPU Linux; o caminho CUDA e a execução nativa Windows ainda exigem validação em hardware correspondente. Não há comparação direta que estabeleça desempenho ou qualidade superior ao Moises.

## Ativar o FaixaLab neste repositório

1. A configuração de inicialização fica neste repositório. O código-fonte editável fica na pasta `app/`. Os modelos grandes são obtidos do ZIP do release.
2. Crie um release com a tag **v0.10.1** e anexe **FaixaLab_0_10_1_Windows.zip**, o aplicativo completo recebido nesta atualização. O nome contém Windows por compatibilidade com o pacote existente; ele também contém o servidor Linux.
3. Abra **Code → Codespaces → Create codespace**, escolhendo **2 núcleos / 8 GB**.
4. Aguarde o `postCreateCommand`; ele baixa o release com a identidade do Codespace, confere tamanho, SHA-256 e CRC, extrai o app e instala Python/PyTorch CPU. Os modelos maiores ainda ausentes serão baixados no primeiro processamento.
5. Na aba **Ports**, abra a porta **7860**, mantendo visibilidade **Private**. No celular, entre no mesmo GitHub e abra essa URL.

O manifesto `release.json` fixa o pacote exato. Não troque o ZIP do release por outro arquivo sem atualizar tamanho e SHA-256. O código-fonte em `app/` é executado pelo servidor. O ZIP do release fornece os modelos binários verificados; os arquivos grandes não entram no histórico Git.

O bootstrap usa o `GITHUB_TOKEN` temporário que o Codespaces fornece automaticamente para o próprio repositório. Não cole tokens no código nem no chat. Nenhuma chave de API de IA é necessária.

## Usar e retomar

- Abra o FaixaLab, cole o link do YouTube ou envie um MP3. O processamento ocorre no Codespace.
- Em **Backing track**, prepare uma mixagem sem voz/solo ou com os volumes e M/S escolhidos no mixer. Toque em **Ouvir backing track**, ou baixe o M4A para tocar fora do site.
- Conecte o Bluetooth nas configurações do celular. Não é necessário parear pelo navegador.
- Projetos e modelos ficam em `/workspaces/.faixalab-data`, fora do checkout e do Git. A instância parada conserva esses dados; excluir a instância elimina os arquivos que não foram exportados.
- Pare o Codespace ao terminar. Ao retomá-lo, o `postStartCommand` reinicia o app sem reinstalar os motores.
- Para iniciar manualmente pelo terminal do Codespaces: `bash cloud/start.sh`.
- Logs: `/workspaces/.faixalab-data/server.log`.

## Franquia gratuita e limites verificados em 07/11/2026

GitHub Free pessoal inclui **120 horas-núcleo por mês**, equivalentes a cerca de **60 horas em dois núcleos**, e **15 GB-mês**. O uso é compartilhado entre todos os Codespaces da conta; armazenamento conta mesmo com a instância parada. Confira o consumo e o bloqueio de gastos antes de criar a instância. Esta configuração não habilita GPU, pagamento, aumento de orçamento ou pré-build pago.

Codespaces suspende por inatividade, por padrão após 30 minutos, e tem limite de 12 horas por sessão. A configuração não tenta contornar esses limites. É uma opção para protótipo pessoal, com cota, sem disponibilidade permanente. A CPU não garante aceleração em relação ao seu PC. O YouTube pode restringir downloads a partir de IPs de datacenter; enviar o MP3 é uma entrada alternativa.

[Franquias oficiais](https://docs.github.com/en/billing/concepts/product-billing/github-codespaces) · [Inatividade e ciclo de vida](https://docs.github.com/en/codespaces/setting-your-user-preferences/setting-your-timeout-period-for-github-codespaces)
