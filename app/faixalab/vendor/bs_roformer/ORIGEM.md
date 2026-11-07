# BS-RoFormer / MVSep Mega53

Código: ZFTurbo/Music-Source-Separation-Training, revisão `f0b527736e7da24eae5b561a2bb1efd0569ec757`; arquivos `models/bs_roformer/bs_roformer.py` e `attend.py`. Arquitetura baseada no trabalho de Wei-Tsung Lu, Ju-Chiang Wang, Qiuqiang Kong e Yun-Ning Hung e na implementação BS-RoFormer de Phil Wang. Licença MIT distribuída neste diretório.

Pesos públicos de Roman Solovyev / MVSep: release v1.0.21, https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/tag/v1.0.21 . Arquivo `mvsep_mega_model_bs_roformer_53_stems_v1.ckpt`, 1.368.919.887 bytes. SHA256, configuração e cadeia de origem em `models/mega53_metadata.json`.

O arquivo de pesos é baixado integralmente da release oficial no primeiro uso; tamanho e SHA256 são verificados antes da troca atômica para o cache. Carregamento com `weights_only=True`, `mmap=True`; nenhum código do checkpoint é executado. O aplicativo constrói apenas os heads treinados solicitados e remapeia suas chaves mantendo os tensores originais. Não existe retreinamento nem substituição de um head por um nome diferente.

Alteração no código vendorizado: import relativo de Attend. A API upstream já aceita seleção de heads. A configuração YAML oficial foi convertida para JSON sem usar carregador YAML capaz de executar objetos Python. Tuplas da arquitetura são reconstruídas explicitamente.

O modelo público tem 53 saídas, incluindo pais e filhos sobrepostos. O catálogo do aplicativo oferece categorias selecionadas sem misturar automaticamente guitarra genérica + elétrica + acústica, teclados + piano, voz genérica + lead/backing ou bateria + peças. A bateria existente é mantida como referência; nenhum head de bateria é solicitado. A saída não identificada permanece em Outros.

O aviso upstream de uso elevado de memória refere-se à execução completa. A execução adaptada usa heads selecionados, janelas menores e acumuladores em disco. Ainda é um modelo pesado, especialmente em CPU. Não é a versão proprietária mais recente do serviço MVSep. Resultados, custos observados e limitações: VALIDACAO.md.
