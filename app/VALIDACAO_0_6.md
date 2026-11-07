# Validação FaixaLab 0.6 — instrumentos e identificação de timbre

Execução em Linux x86_64, Python 3.12, PyTorch CPU 2.5.1 e ONNX Runtime 1.20.1. O pacote destina-se a Windows x64; instalador e janela nativa não foram executados neste ambiente. A interface foi verificada por DOM/eventos. Históricos: VALIDACAO_0_2.md a VALIDACAO_0_5.md.

## Correção de escopo

A versão 0.5 verificava presença de uma linha melódica no stem chamado guitarra solo. Isso não comprovava o instrumento. O feedback do usuário apontou a confusão com gaita. A validação anterior de intervalos/quantidade de notas era insuficiente para concluir identificação correta de timbre.

A versão 0.6 acrescenta:

- Separação por categorias explícitas com MVSep Mega53 público v1: guitarra elétrica, violão, acordeon, harmônica e outras classes.
- EfficientAT MN10 AudioSet independente para identificar o timbre real, conferir candidatos/saídas e filtrar a autorização de tablatura de guitarra.
- Evidência temporal: observações isoladas precisam de maior força; uma categoria não é confirmada apenas pelo nome do arquivo.
- Refinamento de um projeto existente usando o arquivo anterior da bateria. Nenhum head de bateria é solicitado ao novo modelo.
- Catálogo de 24 categorias; detecção automática ou seleção de até 18. Pais e filhos sobrepostos são controlados. O restante da mistura permanece em Outros.

Os modelos não foram treinados com a música do usuário. Não existem regras por título, letra, ID ou tempos fixos da música.

## Projeto completo fornecido

O ZIP original de 203,307 s, sete WAVs a 44,1 kHz, foi usado para reconstruir a mistura e executar 45 janelas sobrepostas de seis segundos. O separador selecionou nove categorias a partir da identificação nas faixas existentes. A revisão final reteve voz, baixo, guitarra elétrica, violão, piano, acordeon e harmônica, além da bateria anterior e do restante em Outros. O head de cordas tinha energia muito baixa; o de sopros não teve confirmação temporal suficiente. Seus resíduos continuaram na mistura em Outros.

| Verificação | Resultado |
| --- | --- |
| Bateria | Arquivo original reutilizado, bytes idênticos |
| SHA256 da bateria antes/depois | d56c7e56b4ade1ed21902b08ffd6c9cdb33be5f48d224963a557c03bf0e458bf |
| Maior erro absoluto da soma das faixas contra a mistura original | 3,58 × 10⁻⁷ |
| Duração/tamanho temporal | 8.965.824 frames por faixa, 44.100 Hz |
| Acordeon refinado autorizado como guitarra | Zero contextos após confirmação temporal |
| Intermediários de acumulação após revisão final | Zero |

A análise anterior identificou forte evidência de acordeon na faixa chamada Piano. O novo modelo produziu uma saída própria de acordeon e saídas separadas de guitarra elétrica/violão. A classificação também é uma estimativa: não existe referência isolada de todos os instrumentos da gravação comercial para medir sua acurácia ou SI-SDR individual.

A guitarra elétrica refinada passou pelo separador solo/base e pelo fluxo de tablatura real: 193 notas, duas regiões, todas com posições físicas válidas e sem notas fora dos intervalos aceitos. A contagem não mede precisão de alturas ou autenticidade da execução. A avaliação do timbre da gaita usa uma fonte independente da decisão do transcritor. Métricas: tests/resultados/projeto_instrumentos_0_6.json e tablatura_refinada_0_6.json.

## Controle com fontes gravadas conhecidas

Fontes oficiais: demonstrações AudioSep, https://github.com/Audio-AGI/Separate-Anything-You-Describe ; EGSet12, https://zenodo.org/records/11406378 . Áudios não distribuídos no aplicativo. Manifesto com hashes em tests/resultados/fontes_instrumentos_0_6.json.

Uma gravação de acordeon e outra de violão foram misturadas com mesmo RMS, sem separação por posição estéreo. O modelo real foi executado com os dois heads treinados correspondentes, sem retreinamento.

| Fonte | SI-SDR da mistura | SI-SDR separado | Ganho sobre a mistura |
| --- | --- | --- | --- |
| Acordeon | −0,047 dB | 7,511 dB | +7,558 dB |
| Violão | −0,047 dB | 15,068 dB | +15,115 dB |

Ensaio de cinco segundos com fontes de referência conhecidas. Mede recuperação de fontes nesse controle; não compara diretamente com o aplicativo anterior, nem estabelece qualidade para repertório arbitrário.

Identificação real: as gravações de guitarra elétrica EGSet12 e violão foram aceitas como guitarra. Acordeon, violoncelo, saxofone e flauta não foram autorizados como guitarra. Uma gravação de acordeon deliberadamente oferecida ao transcritor como guitar_lead retornou zero notas e uma mensagem de fonte não confirmada. O controle de flauta foi acrescentado como exemplo não usado na escolha inicial da regra. Registro: instrumentos_audio_0_6.json.

## Integração e regressões

- 33 testes Python passaram: lógica anterior, catálogo, seleção de pais/filhos, API, preservação da referência da bateria, cancelamento, cache e regras de timbre.
- Tarefa real de refinamento pela API, sem mock do modelo: acordeon + violão + bateria conhecida. Resultado ready; quatro faixas; bateria idêntica no projeto e no ZIP; letra preservada; acorde manual preservado; revisão de áudio atualizada. Erro máximo de reconstrução 1,12 × 10⁻⁸. Registro: instrumentos_job_0_6.json.
- Fluxo real de tablatura pela API: gravação com silêncio inicial, 36 notas, primeira em 7,0028 s. Notas dentro da região detectada, posições/MIDI/TXT/ZIP e recálculo determinístico com cache conferidos. Registro: solo_job_0_6.json.
- Oito alturas sintetizadas no modo Faixa inteira: alturas corretas, maior erro de ataque 32 ms; edição, exclusão, preservação e exportações passaram. Registro: solo_integracao_0_6.json. Não avalia timbre nem separação.
- Interface: catálogo, ação de refinamento com bateria preservada, seleção automática, mixer com onze faixas, cinco abas, edição, invalidação de análises antigas. Solo de acordeon não solicita tablatura de guitarra. DOM/eventos, sem inspeção visual nativa.
- 174 diagramas de acordes continuam conferidos.
- Frontend Mel NumPy e ONNX EfficientAT comparados com PyTorch em doze contextos reais de cinco segundos: diferença máxima de saída inferior a 1e-6; erro Mel inferior a 1,1e-5. ONNX float32, sem quantização.
- A carga do checkpoint usa apenas tensores/valores permitidos, SHA256 e mmap. Heads não solicitados não são construídos. Um teste real em silêncio confirmou remoção dos arquivos de acumulação.

## Custos e limites

O checkpoint de separação tem aproximadamente 1,37 GB, baixado uma vez e mantido no cache. O reconhecedor de timbre e os modelos de tablatura/acordes já acompanham o ZIP. A inferência usa o computador do usuário. A execução completa pode levar vários minutos em CPU; o progresso indica janelas concluídas e atividade do worker. Em um ensaio de cinco segundos com onze categorias, o pico observado do processo foi cerca de 1,5 GiB, sem constituir requisito máximo para todas as músicas.

O modelo público não é a versão proprietária mais recente do serviço MVSep. Há sobreposição entre algumas categorias brutas; o aplicativo controla combinações e confere a saída, mas instrumentos semelhantes, efeitos, níveis baixos e arranjos densos continuam ambíguos. Algumas fontes podem ficar em Outros ou ser classificadas incorretamente. A seleção manual permite solicitar uma categoria ausente da detecção automática.

A soma correta e a preservação da bateria não provam separação perceptualmente perfeita. O pequeno conjunto de controles não permite garantir acerto universal ou equivalência com Moises pago. Tablatura não inclui articulações automáticas de bends/slides. As posições são sugestões de execução, não identificação inequívoca da corda original.
