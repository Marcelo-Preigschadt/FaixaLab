# Validação — FaixaLab 0.2.0

Data: 06/11/2026. Linux x86-64, Python 3.12.14, PyTorch/torchaudio 2.5.1+cpu, NumPy 1.26.4, librosa 0.11.0, Numba 0.61.2. Inferências reais, sem simular os motores.

## Cifra segue o acompanhamento

A entrada de BTC/CQT foi alterada para o acompanhamento instrumental, acrescido da informação do baixo. Voz e guitarra solo ficam fora dessa entrada. O andamento pode usar a música original; isso não determina os rótulos dos acordes. O modo estável suaviza probabilidades e remove eventos curtos em relação à batida estimada.

Teste específico: acompanhamento C–Am–F–G com uma linha melódica cujas notas mudam a cada 0,18 s. A melodia foi misturada com dois níveis de volume. Nos dois casos, o reconhecimento retornou somente C–Am–F–G, sem acompanhar as notas da melodia. Resultado em `tests/resultados/cifra_sem_melodia_vocal.json`.

Seis regressões de áudio sintetizado foram comparadas com a versão 0.1. Correspondência exata do rótulo em grade de 10 ms, contra a progressão nominal; não é uma precisão medida sobre repertório real.

| Caso | Anterior | 0.2 estável |
| --- | ---: | ---: |
| pop_C | 97.33% | 99.25% |
| pop_G | 97.83% | 99.50% |
| minor_E | 97.83% | 99.50% |
| sevenths | 97.83% | 99.50% |
| suspensions | 48.67% | 71.92% |
| silence | 58.47% | 95.40% |

Persistem ambiguidades. No caso Dsus2, o modelo indicou Asus4, que tem o mesmo conjunto de alturas, com raiz diferente. O silêncio final foi reconhecido depois da cauda de decaimento. Timestamps e confiança continuam sendo estimativas; a confiança não é uma probabilidade de acerto calibrada.

## Separação geral — modo Estúdio

Três primeiros arquivos de test em ordem alfabética do pacote MUSDB18-7-STEMS: AM Contra — Heart Peripheral; Al James — Schoolboy Facination; Angels In Amplifiers — I'm Alright. Cada trecho tem aproximadamente 6,803 s. A entrada é a soma das quatro fontes decodificadas; a métrica é SI-SDR estéreo, média removida e projeção escalar, sem ajuste de alinhamento. Para comparar other, guitarra+piano+outros foram somados.

| Fonte | Anterior | Estúdio |
| --- | ---: | ---: |
| Voz | 10.387 dB | 10.432 dB |
| Bateria | 5.789 dB | 6.006 dB |
| Baixo | 7.696 dB | 8.021 dB |
| Acompanhamento / outros | -0.331 dB | 1.651 dB |

Há pequenas regressões em fontes individuais. A soma das seis faixas reconstruiu o original com erro absoluto máximo inferior a 1,20 × 10⁻⁷. A amostra não mede guitarra ou piano isoladamente nem garante melhoria em toda música. Dados: `tests/resultados/separacao_tres_trechos.json`. Origem: https://github.com/sigsep/sigsep-mus-db/releases/download/v0.4.0/MUSDB18-7-STEMS.zip . As músicas do dataset não acompanham o aplicativo.

## Guitarra solo e base — experimental

Foram carregados e executados dois checkpoints próprios para lead/rhythm. A configuração padrão usa HTDemucs Lead/Rhythm Dry Paint; a alternativa Mel-Band RoFormer listra92 é acessível pela CLI. O padrão gera duas estimativas treinadas, projetadas para que sua soma mantenha a guitarra original. Não se trata de duplicar ou renomear a faixa de guitarra.

Três misturas controladas de gravações independentes do EGSet12: faixas 01, 02 ou 07 como lead, com a faixa 06 como rhythm, 15 s a partir de 6 s; RMS da base em 0,72 × RMS do solo. Dataset: Pedroza, Abreu, Corey e Roman, EGSet12, CC BY 4.0, https://zenodo.org/records/11406378 . Papéis foram atribuídos para o teste, não são stems de uma produção de estúdio.

| Faixa lead + base 06 | Solo: mistura sem separar | Solo: separado | Base: mistura sem separar | Base: separada |
| --- | ---: | ---: | ---: | ---: |
| 01 | 2.817 dB | 0.540 dB | -2.923 dB | -1.063 dB |
| 02 | 2.759 dB | -7.494 dB | -3.038 dB | -3.115 dB |
| 07 | 2.819 dB | 3.117 dB | -2.921 dB | -0.417 dB |

A separação ainda apresenta vazamentos e perda de conteúdo: piorou a métrica de solo em dois dos três casos e não iguala a qualidade garantida de um motor comercial. Por isso a opção está identificada como experimental. A soma solo+base reconstruiu a guitarra com erro máximo inferior a 6 × 10⁻⁸. A função está operacional, mas a qualidade semântica ainda precisa evoluir. Dados: `tests/resultados/guitarras_qualidade_tres_casos.json`.

## Integração e interface

- Um MP3 com fala pública JFK + acompanhamento passou por separação, cifra, Whisper small, streaming HTTP Range e ZIP; foram verificados 22 timestamps de palavras e os arquivos exportados.
- A rota Separar solo e base foi executada sobre um projeto existente: sete faixas, letra preservada, revisão de áudio atualizada, streaming HTTP 206 de solo e base e ZIP com sete WAVs. Erro de reconstrução da guitarra: 3.725290298461914e-09.
- A importação de um novo áudio de duas guitarras executou o fluxo padrão completo de sete faixas e terminou ready sem avisos em 66.63 s nesta CPU, sem transcrição por se tratar de um instrumental. Não é uma estimativa de tempo para outro computador.
- O refinamento de um projeto manteve exatamente a letra e o intervalo de acorde corrigido manualmente.
- Oito testes de lógica/API passaram. 174 diagramas foram conferidos contra as notas e o baixo especificados.
- As quatro abas Stems, Letra, Acordes e Formas, as sete linhas, as letras segmentadas e os controles de mute, seleção de separação e zoom passaram por testes de DOM com dados de um projeto real e reprodução simulada apenas no teste de UI.
- O CSS e o layout foram implementados a partir das imagens fornecidas. Não foi realizada nova validação visual da janela em Windows, nem teste de reprodução sonora no WebView, instalador Windows ou GPU. O iniciador Windows x64 existente foi mantido.
- Sintaxe JavaScript e compilação Python passaram. A importação YouTube não foi alterada nem revalidada nesta atualização; o teste anterior foi bloqueado pela conexão.

Os arquivos JSON em `tests/resultados` registram medições e saídas observadas. Pesos de separação são baixados no primeiro uso e verificados por hash. Os dois modelos BTC são distribuídos no pacote com a origem e as licenças do código.
