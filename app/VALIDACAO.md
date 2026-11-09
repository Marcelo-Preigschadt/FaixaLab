# Validação FaixaLab 0.10 — otimização do processamento

## Comparação completa com a versão 0.9

Linux, Python 3.12.14, PyTorch 2.5.1 CPU, ONNX Runtime 1.20.1; AMD EPYC 9V45, nove CPUs visíveis e cota de oito. A versão 0.9 limita os workers a quatro threads; a 0.10 usa oito nessa máquina. Não há medição de GPU nem de execução nativa Windows.

Entrada: MP3 de 60 segundos formado por uma mistura controlada de gravações de guitarra elétrica EGSet12, violão, acordeon e flauta AudioSep, repetidas até 60 s. Não é uma música comercial completa. Os arquivos e referências estão identificados em `tests/fixtures/instrument_control_sources.json` e o hash do MP3 está no relatório JSON. Áudio não é redistribuído.

As duas versões usaram as mesmas dependências, pesos previamente baixados e opções padrão: seis faixas iniciais, Equilibrado, 33 candidatos automáticos, solo/base, cifra estável e letra Whisper small. A conversão MP3, carregamento dos modelos, verificações e gravação dos resultados entram no tempo. Download dos pesos, transferência do YouTube, fila e tablatura sob demanda ficam fora.

“Novo cache” significa cache DSP/Numba vazio; os pesos e o cache de disco do sistema já estavam preparados. “Cache preparado” é outra execução em processo separado, reutilizando o cache DSP. A duração da letra também variou; a diferença total entre essas duas execuções não deve ser atribuída somente ao cache.

| Etapa | 0.9 | 0.10 · novo cache DSP | 0.10 · cache DSP preparado |
| --- | ---: | ---: | ---: |
| Separação inicial | 26.955 s | 15.831 s | 16.059 s |
| Refinamento de instrumentos | 157.222 s | 90.297 s | 92.606 s |
| Guitarra solo/base | 42.195 s | 12.393 s | 11.982 s |
| Cifra | 7.686 s | 7.680 s | 1.603 s |
| Letra | 47.586 s | 55.610 s | 29.180 s |
| Total, incluindo conversão e atualizações do projeto | 282.144 s | 182.156 s | 151.764 s |

Redução total medida: **35.4%** com novo cache DSP; **46.2%** na execução com cache preparado. A cifra passou de aproximadamente 7,7 s para 1,6 s com cache preparado. A letra não melhorou em todas as execuções. O controle instrumental provocou transcrições indevidas em algumas passagens; o novo encaminhamento para uma voz isolada não estabelece precisão garantida nem elimina esse problema em todo caso.

## Preservação do áudio e das decisões

- Mesmos 33 candidatos e mesmos instrumentos retidos após verificação, incluindo as estimativas indicadas como incertas. Não se removem candidatos para obter o ganho.
- Mesmas faixas finais, com guitarra solo/base publicadas no projeto. Eventos, tempos e confidências da cifra foram idênticos nesse controle.
- Maior diferença de amostra para a 0.9: 1.188367605e-06. Maior RMS da diferença: 8.511262327e-08. Relação sinal/diferença entre 94.9 e 123.1 dB. Isso mede a diferença para a implementação anterior, não a qualidade da separação contra stems verdadeiros.
- Erro máximo na soma das faixas contra a mistura original: 1.788139343e-07.
- Pesos, limiares, classes, janelas, overlap e precisão float32 do separador são preservados. A transcrição prefere uma voz já salva no histórico quando a separação atual não contém voz; por isso as letras podem mudar.
- A compilação DSP é isolada por versão, instalação, ambiente e dependências. A execução em um novo processo com cache preparado concluiu normalmente.

## Medições isoladas

Um trecho gravado de seis segundos com todos os 33 candidatos levou 11,15 s com quatro threads e 5,60 s com oito. A maior diferença numérica observada foi inferior a 0,000001. Duas threads levaram 16,14 s; isso não é promessa de aceleração em máquinas menores.

A resolução de sobreposições, no mesmo orçamento de quatro threads, caiu de 5,38–5,76 s para 0,37–0,39 s num controle de 60 s com 33 estimativas reais do modelo. A aceitação de timbres foi fixada nesse microbenchmark para exercitar o caso de muitas faixas: após os grupos pai/filho restaram 27. As decisões foram idênticas. Essa medição isolada não é o tempo total da separação.

As correlações usam todos os samples e canais em blocos. Casos próximos ao limiar de duplicação retornam à aritmética antiga. A verificação algébrica do resíduo inclui uma margem conservadora para o arredondamento da subtração float32 e também retorna ao cálculo original quando a decisão pode mudar.

## Verificações concluídas

- 66 testes Python, nove regressões do player e 174 verificações de diagramas.
- Duas suítes DOM, incluindo seleção automática, tablatura, dicionário e backing track, sem erros.
- Fluxo real completo sem mocks de modelos; faixas publicadas, soma de áudio e cifra conferidas.
- Instalação e validação real do motor CPU. Detecção de driver, escolha de wheels, falha CUDA, recuperação em CPU e compatibilidade da chamada SDPA exercitadas em testes controlados. Esses testes não representam execução em GPU real.
- Recuperação de GPU limitada a uma tentativa em CPU; cancelamento e outros erros continuam propagados.

Código reproduzível: `tests/benchmark_pipeline.py`. Prepare previamente os modelos e execute cada versão em um processo separado com o mesmo MP3, ambiente e cache de pesos. Dados completos: `tests/resultados/otimizacao_0_10.json`.

## Limites

Não houve comparação direta com o Moises, validação nativa Windows ou medição em CUDA. Não se estabelece equivalência ou superioridade ao Moises nem precisão sobre qualquer repertório. O desempenho depende do orçamento real de CPU, GPU/driver, duração e conteúdo do áudio. O primeiro download continua dependendo da rede; o processamento continua disponível em CPU. O reconhecimento da tablatura não recebeu um benchmark completo de velocidade nesta revisão.

Referências técnicas: [PyTorch e wheels CUDA](https://pytorch.org/get-started/previous-versions/), [compatibilidade CUDA](https://docs.nvidia.com/cuda/archive/12.8.1/cuda-toolkit-release-notes/index.html), [cache e identificação da CPU no Numba](https://numba.readthedocs.io/en/stable/developer/caching.html).
