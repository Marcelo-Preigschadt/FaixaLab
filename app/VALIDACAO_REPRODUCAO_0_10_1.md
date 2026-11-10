# FaixaLab 0.10.1 playback1 — recuperação de buffer

O relato foi esclarecido como “ele toca e para, carrega toca e para”. Não tivemos acesso aos arquivos ou ao log do computador afetado. A inspeção identificou um ciclo possível no código: uma espera curta pausava todos os elementos com `preload=none`, a retomada exigia apenas `readyState>=3`, e seis segundos de espera disparavam `load()`, que descarta o buffer existente.

## Correção

- Elementos ativos usam `preload=auto`, inclusive durante a pausa por buffering. Elementos silenciados ou fora do solo usam `none` e continuam pausados.
- A retomada exige dados a partir da posição preservada: até dois segundos em cada faixa ativa. Perto do fim, exige somente o trecho restante.
- Uma transferência que está progredindo não é reiniciada após seis segundos. O progresso das faixas é acompanhado durante a espera.
- Não há recarga de um elemento saudável na recuperação comum. Troca de codec, erro de mídia e elemento sem dados ainda podem exigir `load()`.
- Uma espera sem progresso termina após 20 segundos; há também limite total de 60 segundos. A mensagem informa que a separação está salva.
- O cache da interface recebe uma identificação nova. Os motores, pesos, parâmetros da análise e projetos permanecem iguais.

## Verificações realizadas

Três novos testes falharam contra o player anterior: carregamento pausado com `preload=none`, retomada com somente 200 ms de buffer e recarga destrutiva durante uma transferência em progresso. Os três passaram depois da correção.

A suíte final contém 15 casos aprovados, incluindo os nove casos anteriores, retomada sem perder posição, limite da espera e buffering perto do fim. O teste HTTP com arquivos WAV reais também passou: a revisão anterior continua disponível por Range 206 após refinamento e divisão de guitarra.

```sh
node app/tests/test_player.cjs
PYTHONPATH=app python -m unittest discover -s app/tests -p test_audio_stability.py -v
```

Foi preparado `tests/test_player_browser.cjs` para testar Chromium com elementos de mídia e Web Audio reais, WAV float32 estéreo e uma interrupção controlada de transferência. A execução não pôde iniciar o Chromium neste ambiente: o sistema recusou a criação do socket do navegador. Esse teste permanece sem resultado; os 15 casos aprovados usam um modelo controlado de HTMLAudioElement. Não houve validação nativa Windows nem audição no computador do usuário.

O pacote pequeno contém apenas `faixalab/web/app.js`, `faixalab/web/service-worker.js`, instruções e seu manifesto SHA-256. Não executa instalador ou modelos. É aplicado à instalação 0.10.1 existente. O pacote completo original e seu manifesto permanecem como base da instalação; esta atualização é complementar. O código editável do Git incorpora a correção. Não se afirma que esta mudança elimine todos os motivos possíveis de interrupção, como arquivo danificado, saída de áudio ou conexão insuficiente.
