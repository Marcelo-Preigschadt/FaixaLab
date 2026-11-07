# Validação — FaixaLab 0.3.0

Data: 06/11/2026. Linux x86-64, Python 3.12.14, PyTorch/torchaudio 2.5.1+cpu, NumPy 1.26.4, librosa 0.11.0 e Numba 0.61.2.

## Progresso e retomada

O executor de janelas mantém o overlap-add, padding e deslocamentos do Demucs. Cada janela concluída emite progresso, inclusive a passada de guitarra/piano. Um teste determinístico de 203 s, com modelo linear de duas fontes a 100 Hz, verificou mais de 50 janelas, progresso estritamente crescente e igualdade bit a bit com o executor original, com e sem deslocamento. Esse teste valida o executor; não mede desempenho de inferência de 203 s com Demucs.

A integração com os modelos reais recebeu um MP3 de 11 s com fala pública JFK e acompanhamento C–Am–F–G. Executou o ensemble Estúdio, a passada de seis fontes, BTC/CQT/semi-Markov e Whisper small. Finalizou sem avisos em 67,43 s nesta CPU. O polling registrou 27,8 → 30,8 → 33,7 → 36,7% dentro da segunda etapa, em vez de aguardar o modelo inteiro. Foram verificados seis WAVs por HTTP Range 206, 22 palavras com timestamps e integridade CRC do ZIP. Isso não estima o tempo em outro computador. Dados: `tests/resultados/integracao_0_3.json`.

Um segundo teste iniciou um worker Estúdio real, solicitou sua parada durante a primeira janela e recalculou a cifra do acompanhamento já salvo. Preservou exatamente os caminhos e a revisão das faixas, a letra e um intervalo corrigido manualmente para Am7. Concluiu o cenário em 17,95 s, incluindo preparação e nova análise. Dados: `tests/resultados/cancelar_e_recalcular_0_3.json`.

O backend registra tempo decorrido e tempo sem nova saída; esses sinais não provam utilização de CPU ou travamento. Não foi observado o processo no computador do usuário.

O modo Equilibrado também executou os seis stems reais do áudio de 11 s, com quatro janelas e progresso 0 → 25 → 50 → 75 → 100% dentro da etapa. A soma dos WAVs reconstruiu o original com erro absoluto máximo 5.960e-08. Dados: `tests/resultados/equilibrado_0_3.json`.

## Cifra estável

A duração mínima das hipóteses harmônicas passa a integrar a decodificação semi-Markov: duas batidas, limitada a 0,6–1,2 s. A classe sem acorde tem duração livre. Extensões recebem penalidade e o reconhecedor de tríades recebe maior peso. O modo estável desativa inversões automáticas; o modo detalhado as mantém. A entrada continua sendo o acompanhamento; voz e guitarra solo não entram diretamente. Vazamentos presentes em stems podem afetar a análise.

O teste de posterior controlado inclui quatro interferências de Em com 0,2 s sobre C e uma mudança real sustentada para G em 6 s. O modo estável retorna C → G, com a mudança em 6 s. Isso verifica a política temporal, sem representar uma medição de acerto em repertório real.

Seis regressões de áudio sintetizado conhecido foram reexecutadas. Comparação exata do rótulo em grade de 10 ms, contra a progressão nominal:

| Caso | 0.2 estável | 0.3 estável |
| --- | ---: | ---: |
| pop_C | 99.25% | 99.25% |
| pop_G | 99.50% | 99.50% |
| minor_E | 99.50% | 99.50% |
| sevenths | 99.50% | 99.50% |
| suspensions | 71.92% | 70.17% |
| silence | 95.40% | 95.40% |

Persistem a ambiguidade Dsus2/Asus4 e a cauda de decaimento antes do silêncio final. O caso de suspensões apresenta pequena regressão em relação à versão 0.2; a duração mínima também pode ocultar mudanças rápidas reais. Use Detalhada para esse caso. As outras cinco regressões conservaram os rótulos e as métricas anteriores. Dados: `tests/resultados/cifras_0_3.json`. A confiança exibida não é uma probabilidade de acerto calibrada. O MP3 da música mostrada pelo usuário não estava disponível para conferência acorde por acorde.

## Diagramas e linha do tempo

174 acordes/inversões foram verificados por conjunto de alturas e nota mais grave. Bm, Cm, Fm e F#m também passaram por verificações das posições convencionais. Bm retorna x24432, dedos 1–3–4–2–1 e pestana na casa 2 da corda A à e. O desenho anterior x20x02 contém B–D–B–F# e é harmonicamente Bm; foi substituído por uma digitação usual.

O teste de DOM verificou as quatro abas, sete faixas, mute, configurações e zoom. Uma música de 203 s a 152 BPM abriu uma janela de oito compassos (12,63 s). Com largura de janela de 1.440 px, um acorde de 1,6 s recebeu aproximadamente 137,81 px, em vez de comprimir a música inteira no viewport. A régua identifica tempo e compasso. Foram conferidos o aviso de análise anterior, a solicitação de recalcular enquanto o projeto está ocupado e o SVG da pestana de Bm. A reprodução é simulada somente nesse teste de UI; não houve renderização visual do aplicativo. Dados: `tests/resultados/interface_0_3.json`.

## Verificações e limites

- 12 testes unitários de lógica, duração harmônica, API, cancelamento, supervisão do subprocesso e executor de progresso passaram.
- A sintaxe JavaScript e a compilação Python foram verificadas.
- Não houve execução do instalador, teste sonoro no WebView, validação visual da janela em Windows ou teste de GPU.
- Os modelos de separação e de solo/base não foram retreinados. O modo Estúdio preserva o algoritmo e os parâmetros anteriores; Equilibrado é o novo padrão de importação.
- A separação solo/base continua experimental. As medições de qualidade da versão anterior estão em `VALIDACAO_0_2.md`, com as regressões observadas.
- YouTube e o iniciador Windows x64 foram preservados e não foram revalidados nesta atualização.
