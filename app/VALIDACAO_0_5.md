# Validação FaixaLab 0.5 — detecção geral de solos

Execução em 6/11/2026, Linux x86_64, Python 3.12, PyTorch CPU 2.5.1 e ONNX Runtime CPU 1.20.1. O aplicativo destina-se a Windows x64; instalador e janela nativa não foram executados neste ambiente. Os testes de interface verificam DOM e eventos, sem avaliação visual nativa. Registros anteriores: VALIDACAO_0_2.md, VALIDACAO_0_3.md e VALIDACAO_0_4.md.

## Mudança

A versão 0.4 transcrevia guitar_lead.wav inteiro. Reduzir a uma voz transformava vazamentos de acordes em notas, sem verificar a presença de solo. Agora o modo padrão detecta candidatos usando MERT, mistura e stem, predominância solo/base e continuidade. Antes de reduzir as vozes, Basic Pitch verifica a textura polifônica: um trecho com mais de 55% dos frames ativos contendo três ou mais alturas é rejeitado como acompanhamento predominantemente de acordes. Faixa inteira continua disponível para uma transcrição completa.

O detector não consulta letras, títulos, IDs nem posições fixas da música. Os parâmetros são globais. A voz não aplica um veto absoluto. Sem solo confirmado, o resultado automático fica vazio. Edições e exclusões explícitas continuam preservadas quando solicitado.

## Projeto real fornecido

Entrada: ZIP do usuário, 203,307 s, sete WAVs a 44,1 kHz. A mistura foi reconstruída somando as faixas. Não foi necessário baixar novamente o YouTube. O ZIP original permaneceu intacto.

| Medida | Versão 0.4 exportada | Versão 0.5 |
| --- | --- | --- |
| Notas automáticas | 1.121 | 205 |
| Intervalos de transcrição | Faixa inteira | 5,9–19,3 s e 78,5–96,3 s |
| Tempo coberto pelos solos | Sem detector | 31,2 s |

Os dois intervalos são compatíveis com a descrição do usuário: solo no início e no meio. Os tempos exatos não foram anotados manualmente. A contagem menor demonstra o recorte temporal; não mede a exatidão das 205 alturas. Não existe tablatura de referência alinhada para medir precisão/recall de notas nessa gravação.

Primeira análise observada: cerca de 120 s, incluindo inicializações. Recálculo com detecção em cache e verificação de textura: cerca de 13 s. Esses tempos não são uma previsão para outros computadores. Métricas: tests/resultados/projeto_real_0_5.json.

## Controles com gravações externas

Fontes oficiais: GuitarSet, https://zenodo.org/records/3371780 ; EGSet12, https://zenodo.org/records/11406378 . Áudios não distribuídos; hashes em tests/resultados/fontes_audio_0_5.json. Trechos usados: 6–18 s de cada arquivo.

Controles com papéis conhecidos: ganho 0,08 no stem solo para vazamento de acompanhamento, ou 0,92 para testar uma atribuição predominante ao solo. A base recebe o ganho complementar; a mistura é preservada. Esses controles avaliam detecção/transcrição, sem medir o separador Demucs.

| Conjunto | Acompanhamentos sem solo | Falsas detecções | Solos | Casos com detecção |
| --- | --- | --- | --- | --- |
| Desenvolvimento: bossa, jazz, guitarra elétrica e solo com voz | 4 | 0 | 4 | 4 |
| Reserva: rock/jazz de acompanhamento, funk/rock solo | 2 | 0 | 2 | 2 |

O desenvolvimento revelou dois falsos positivos quando o acompanhamento era atribuído fortemente ao stem solo. Eles motivaram a verificação de textura. Os quatro casos de reserva foram avaliados depois de fixar essa regra. Resultados anteriores à verificação: presenca_antes_textura_0_5.json; finais: presenca_solo_0_5.json e presenca_reserva_0_5.json.

O caso com voz acrescenta um trecho vocal ativo à guitarra, RMS vocal aproximadamente 0,068, e mantém a detecção. Verifica a ausência de veto pela mera presença de voz. A amostra é pequena e usa fontes controladas: não estabelece taxas de erro para repertório arbitrário ou mixagens comerciais completas.

## Integração e regressões

- 27 testes Python passaram: lógica anterior, cifra, dicionário, posições, cache, cancelamento, silêncio, incerteza, ausência de fallback para a música inteira, deslocamento de fronteiras com o áudio e invalidação de análises antigas.
- 174 diagramas conferidos; posições convencionais Bm/Cm/Fm/F#m preservadas.
- DOM passou: sete faixas, cinco abas, seções, edição, descarte da análise 0.4 e solicitação automática do detector atual. Um resultado válido sem solo não entra em ciclo de reprocessamento.
- Tarefa real da API, sem mocks dos modelos: gravação com sete segundos de silêncio inicial; seção 6,8–19,2 s e 36 notas, primeira em 7,0028 s. Notas dentro da seção, posições físicas, tempos originais no MIDI, TXT, ZIP e recálculo determinístico com cache verificados. Registro: solo_job_0_5.json.
- Transcrição de alturas no modo Faixa inteira: oito alturas sintetizadas conhecidas, erro máximo de ataque 32 ms; correção, exclusão, preservação e exportações passaram. Registro: solo_integracao_0_5.json. Esse ensaio não valida a detecção semântica.
- Conversão do detector: 17 contextos. ONNX float32 concordou com PyTorch dentro da precisão numérica observada. Int8 apresentou diferença máxima de aproximadamente 0,070 na saída da classe solo. Modelo reduzido: 122.240.293 bytes; SHA256 e origem em solo_presence_metadata.json. Scores não são probabilidades calibradas da decisão final.

## Limitações

Arpejos de base podem parecer melodia; solos em acordes podem parecer acompanhamento. Papéis trocados na separação, guitarra baixa, efeitos intensos e timbres semelhantes também podem provocar erros. A textura favorece solos melódicos de uma/duas vozes; não classifica universalmente intenção musical. Nenhuma etapa foi treinada com a música enviada pelo usuário.

A alteração delimita a tablatura; não corrige o áudio separado nem acrescenta bends, slides ou articulações. Não promete equivalência com o motor proprietário do Moises. Para estudar passagens rejeitadas, use Faixa inteira. Os controles manuais permanecem disponíveis.
