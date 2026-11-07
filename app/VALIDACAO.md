# Validação FaixaLab 0.9 — reprodução e entrega do áudio

## Falhas reproduzidas e corrigidas

Cinco testes falharam na cópia imutável da versão 0.8: troca de revisão parava a reprodução/zerava o tempo, sincronismo repetia seeks durante carregamento, uma promessa de play antiga anulava pause, modo solo mantinha todas as faixas decodificando e reprodução local exigia conversão AAC. Todos passaram após a correção. Foram acrescentados testes de recuperação de codec, limite de tentativas, preservação de mixer/posição e retomada de AudioContext suspenso: nove casos aprovados.

O backend foi testado com WAVs diferentes por revisão: após atualizar as faixas e depois remover o nome guitarra ao dividir solo/base, a URL antiga ainda devolve exatamente os mesmos bytes via HTTP Range 206. Revisão desconhecida recebe 404. O histórico armazena referências de arquivos, sem duplicar waveforms.

## Navegador com áudio real

A prévia estática de teste utiliza os arquivos reais da interface, HTMLAudioElement e AudioContext nativos, dois AACs sintetizados e uma API simulada que conclui o refinamento durante a reprodução. Ela não executa os modelos de separação.

- Versão 0.8: revisão atualizada após 2,080 s; reprodução interrompida e posição voltou a zero.
- Versão corrigida: revisão atualizada após 2,049 s; áudio continuou até 5,050 s e o teste confirmou a preservação da reprodução.
- O resultado novo fica pendente para aplicação consciente durante a audição; ao retomar um mixer pausado, a revisão mais recente é carregada mantendo o tempo e o mix das faixas existentes.

## Medições de velocidade

Medição em Linux x86-64, Python 3.12, ONNX Runtime 1.20.1, orçamento de quatro threads. A comparação de timbres foi repetida sem outros testes de CPU em execução. Cada um dos sete controles de instrumento gravado foi repetido até 60 s e analisado com as mesmas 23 janelas e normalização da versão 0.8.

| Etapa medida | Antes | Depois | Evidência |
| --- | ---: | ---: | --- |
| Verificação de timbres, sete controles / 161 contextos | 2,222 s | 1,164 s | redução de 47,6%; scores dos 527 rótulos idênticos; decisões no limiar 0,12 idênticas |
| Primeiros 512 bytes de todas as oito faixas de 90 s | 5,670 s | 0,031 s | AAC frio na versão anterior; WAV direto local nesta versão; respostas Range 206 |
| Primeira faixa disponível no ensaio de entrega | 1,464 s | 0,024 s | mesma gravação de controle repetida, estéreo 44.100 Hz |

O ensaio de mídia mede entrega/conversão no servidor, sem inicialização do decodificador no aparelho. Ele usa oito nomes de faixa ligados à mesma gravação para isolar o custo do transporte. Não mede qualidade de separação nem tempo de processamento completo de uma música.

A aceleração do reconhecedor preserva integralmente as entradas, os pesos e a ordem dos resultados. O limite de quatro tarefas pendentes mantém cancelamento e memória controlados. Máquinas configuradas com duas threads usam execução sequencial, evitando exceder esse orçamento.

## Escopo e limites

O separador principal Mega53, Demucs, os 33 candidatos, modelos de guitarra, detector de solo, acordes e notas não foram trocados ou retreinados. Não houve ajuste por título, artista, link ou marcações fixas de solo.

Não tivemos o arquivo nem um log do congelamento relatado nesta última música. O teste reproduz uma causa concreta existente no código; ele não comprova que todas as causas de interrupção no computador do usuário tenham sido eliminadas.

A execução Windows nativa não foi realizada neste ambiente Linux. O iniciador Windows existente chama os scripts atualizados para 0.9.0. Não foi medido um pipeline completo de uma música com todos os modelos nesta revisão; os ganhos acima são de etapas específicas. Os resultados anteriores permanecem em VALIDACAO_0_8.md e arquivos históricos.

## Verificações reproduzíveis

```sh
python -m unittest discover -s tests -p 'test_*.py'
node tests/test_player.cjs
node tests/test_guitar.js
NODE_PATH=/caminho/node_modules node tests/test_studio_ui.cjs
NODE_PATH=/caminho/node_modules node tests/test_automatic_ui.cjs
python tests/prepare_playback_browser.py --output /caminho/qa --baseline /caminho/FaixaLab_0_8
```

Os testes DOM usam jsdom 26.1.0. O último comando prepara somente uma prévia de QA local, com áudio sintético, fora do pacote do usuário. As métricas estruturadas ficam em tests/resultados/reproducao_e_velocidade_0_9.json.
