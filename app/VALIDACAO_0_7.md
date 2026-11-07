# Validação FaixaLab 0.7 — motor automático geral

## Mudança avaliada

O aplicativo passou a executar os mesmos 33 heads candidatos do catálogo para cada importação automática, antes de verificar o timbre. A versão 0.6 solicitava cinco categorias fixas e somente os extras reconhecidos nas faixas antigas. Um instrumento ausente dessa identificação inicial podia ficar sem qualquer tentativa de extração.

A versão 0.7 também usa presença local, normalização limitada na entrada do reconhecedor, resolução de famílias/filhos e duplicatas, conferência de estimativas muito baixas no resíduo e conservação qualificada de estimativas substanciais quando o classificador é incerto. Estimativas incertas entram em ordem de energia quando reduzem o erro de reconstrução. O ganho e o conteúdo dos WAVs não são normalizados pelo reconhecedor. O resíduo fica em Outros.

Não existem regras de execução por título, artista, letra, URL, ID de vídeo ou tempos de uma música. Os trechos fixados abaixo pertencem exclusivamente às gravações de controle dos testes. MVSep Mega53 e EfficientAT permanecem pré-treinados; não houve treinamento com o material do usuário.

## Comparação com a seleção anterior

O código 0.6 foi executado antes da alteração, sobre as mesmas misturas de cinco segundos. Os dois canais são cópias da mesma mistura; não há separação por posição estéreo. As referências receberam RMS definido antes da soma.

| Controle | Seleção 0.6 | Saídas finais 0.7 |
| --- | --- | --- |
| Acordeon + violão, mesmo RMS | Retinha também guitarra elétrica, baixo e harmônica | Acordeon e violão |
| Flauta 20 dB abaixo de violoncelo | Não solicitava flauta; retinha baixo e cordas de arco | Flauta e violoncelo |
| Saxofone 20 dB abaixo de violão | Não solicitava nenhum head de sopro | Violão e saxofone, este qualificado como estimativa |
| Violoncelo + flauta, mesmo RMS | Cordas de arco e sopros | Violoncelo e flauta |
| Acordeon sozinho | Acordeon | Acordeon |

Essas saídas não estabelecem pureza perfeita de cada instrumento. As gravações AudioSep são referências de demonstração com categorias declaradas, e não uma coleção de stems de estúdio rigorosamente isolados e anotados para todos os sons presentes.

## Recuperação das referências

SI-SDR compara a estimativa com o sinal de referência efetivamente misturado. O ganho abaixo é relativo à mistura sem separação, não uma comparação de SI-SDR contra o motor 0.6. Testes de cinco segundos em CPU, com todos os 33 candidatos no modo automático e a mesma política para todos os casos.

| Mistura / referência avaliada | SI-SDR na mistura | SI-SDR separado | Ganho |
| --- | --- | --- | --- |
| Acordeon + violão / acordeon | −0,047 dB | 9,527 dB | +9,574 dB |
| Acordeon + violão / violão | −0,047 dB | 14,905 dB | +14,952 dB |
| Flauta baixa + violoncelo / flauta | −20,093 dB | 7,718 dB | +27,811 dB |
| Saxofone baixo + violão / saxofone | −19,445 dB | 4,182 dB | +23,627 dB |
| Guitarra EGSet12 02 + acordeon / guitarra | 0,033 dB | 20,604 dB | +20,571 dB |
| Guitarra + violoncelo + saxofone / guitarra | 1,054 dB | 14,638 dB | +13,584 dB |
| Guitarra + violoncelo + saxofone / violoncelo | −2,500 dB | 10,600 dB | +13,100 dB |
| Guitarra + violoncelo + saxofone / saxofone | −9,985 dB | 10,537 dB | +20,522 dB |
| Reserva: violino + violão / violino | −0,024 dB | 20,991 dB | +21,014 dB |

Os controles adicionais com guitarra elétrica e segundos 5–10 das demonstrações foram usados para revisar a abstenção do classificador. Portanto, não são um teste independente cego. Violino e trompete foram acrescentados após fixar a política final; seus resultados foram registrados sem nova alteração dessa política.

## Casos que ainda falham ou permanecem ambíguos

- Flauta a −36 dB RMS em relação ao violoncelo: o modelo não produziu uma fonte de flauta utilizável; a saída final reteve apenas o violoncelo como estimativa. Executar o head não garante recuperar um instrumento encoberto.
- Trompete + violão, no controle de reserva: o aplicativo reteve Metais e Violão. A família foi recuperada, mas não houve confirmação suficiente para publicar uma faixa específica de Trompete.
- O controle com guitarra, violoncelo e saxofone também reteve uma saída de Harmônica, sem referência individual para confirmar esse instrumento adicional. A concordância entre o separador e o reconhecedor pode estar errada.
- A importação de MP3 com referências de acordeon/violão também reteve uma estimativa de voz. O sucesso do processamento não comprova a identidade de todas as saídas.
- Uma fonte que já estava quase limpa pode perder qualidade ao passar pelo separador: no controle extremo da flauta muito baixa, a referência de violoncelo tinha SI-SDR 36,001 dB na mistura e 27,320 dB na saída. Soma correta não significa melhoria de todos os stems.

Não há evidência para prometer ausência de erros em qualquer música, equivalência ao Moises pago, identificação de instrumentos fora do catálogo ou isolamento rigoroso de todos os sons das referências AudioSep.

## Presença breve e posição temporal

Uma gravação de flauta de dois segundos, com RMS 0,002, foi colocada em dois locais diferentes — 2 s e 91 s — de sinais de 120 segundos. Nos dois casos, a verificação local confirmou a flauta. A relação RMS global ficou em 0,002582, abaixo do antigo corte 0,003. Esse ensaio mede a decisão de presença, sem executar separação de 120 segundos nem avaliar limites de solos.

Silêncio digital retornou zero categorias e Outros silencioso. Todos os ensaios completos conferiram reconstrução numérica e ausência de acumuladores temporários. A conferência não mede pureza perceptual.

## Integração real e regressões

- **37 testes Python** passaram, incluindo importação YouTube por URLs distintas com análise automática padrão, contratos de API/worker, cancelamento, rótulos de incerteza, conservação de áudio/anotações e regressões de acordes/tablatura.
- **Importação real de MP3 pela API**, sem mock dos separadores: decodificação, Demucs, Mega53 com 33 candidatos, verificação, cifra, persistência e ZIP. Status ready, zero avisos, 53,29 s em CPU para o controle curto, erro máximo de reconstrução 5,96 × 10⁻⁸. Instrumentos detalhados foram produzidos sem clicar num segundo botão.
- **Interface em DOM**: importação automática selecionada, catálogo de 33 categorias, mixer com onze faixas, indicação de estimativa, resolução da seleção pai/filho, botão de refinamento enviando seleção automática, cinco abas e zero erros de DOM. Ouvir acordeon não solicita tablatura de guitarra.
- **174 diagramas** de acordes e posições convencionais/pestana de Bm continuaram conferidos. Sintaxe JavaScript e compilação dos módulos Python passaram.
- Os contratos da rota YouTube foram testados, mas não foi feito um novo download real de vídeo neste ambiente. O teste de importação ponta a ponta usou MP3. Disponibilidade do vídeo e mudanças do serviço continuam sendo dependências de entrada.
- O executável/iniciador Windows não foi executado nativamente neste ambiente Linux. O bootstrap anterior foi mantido, e os scripts de instalação/inicialização foram atualizados para o perfil 0.7.0.

## Recursos e reprodução

O checkpoint público de separação tem 1.368.919.887 bytes e o mesmo SHA256 da versão 0.6. Ele é baixado uma vez, conferido e mantido no cache; não acompanha o ZIP. O reconhecedor e os modelos de acordes/tablatura já acompanham o aplicativo. Os controles de cinco segundos levaram aproximadamente 23–28 s por execução completa, incluindo carga e verificação. O maior pico observado foi aproximadamente 3,43 GiB de RAM do processo; não é um limite garantido para Windows ou músicas completas. Músicas completas exigem muitas janelas e podem levar vários minutos em CPU.

As demonstrações AudioSep e EGSet12 02 totalizam oito gravações. URLs, tamanhos e SHA256 estão em `tests/fixtures/instrument_control_sources.json`; os áudios não são distribuídos. Fontes:

- https://github.com/Audio-AGI/Separate-Anything-You-Describe
- https://zenodo.org/records/11406378
- Separador: https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21
- Reconhecedor: https://github.com/fschmid56/EfficientAT

Com as dependências do aplicativo instaladas, os controles podem ser reproduzidos com:

```text
python tests/automatic_instruments_regressions.py --controls CONTROLES --download-controls --cache CACHE_DO_MEGA53 --output resultados_automaticos.json
python tests/automatic_import_integration.py --controls CONTROLES --models-cache CACHE_DOS_MODELOS --output importacao.json
python -m unittest discover -s tests -p "test_*.py" -v
node tests/test_guitar.js
```

O ensaio DOM usa jsdom 26.1.0 como dependência somente de desenvolvimento: `node tests/test_automatic_ui.cjs`. As métricas estruturadas desta revisão estão em `tests/resultados/*_0_7.json`. As validações das versões anteriores permanecem nos arquivos `VALIDACAO_0_2.md` a `VALIDACAO_0_6.md`.
