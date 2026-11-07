# Detecção local de guitarra solo

Modelo: **Lead Instrument Detection from Multitrack Music**, Longshen Ou e colaboradores, ICASSP 2025.

- Código oficial: https://github.com/Sonata165/LeadInstrumentDetection
- Commit: `87bc0e6709cb6d7fc783cf1793b6c76e5effdfbd`.
- Classificador: `MertSoloDetectorFromMixSegment`, média temporal da última camada MERT + Linear(768, 2).
- Checkpoint público: https://huggingface.co/LongshenOu/guitar-solo-segment-cls-mjn
- Revisão: `9835a7a539d758e3d5832882fd50726218aba9cb`.
- Arquivo de origem: `segment_guitar_cls_mjn.ckpt`; SHA256 em `models/solo_presence_metadata.json`.
- Backbone: **MERT-v1-95M**, m-a-p; https://huggingface.co/m-a-p/MERT-v1-95M .

O repositório do detector usa MIT; sua licença está neste diretório. A página do checkpoint não declara uma licença separada. O backbone MERT declara **CC BY-NC 4.0**, https://creativecommons.org/licenses/by-nc/4.0/ . A conversão preserva esses avisos e não amplia as permissões dos modelos originais. Definições MERT/HuBERT adaptadas dos autores e do Transformers: Apache-2.0; licença anexa. Os arquivos originais necessários à reconstrução estão em `tools/solo_detector_source`.

A conversão usa apenas os tensores de inferência, sem otimizador nem execução de classes do checkpoint. O carregador de desenvolvimento verifica SHA256, usa `weights_only=True` e substitui a configuração mlconfig por um dicionário sem métodos. O aplicativo usa exclusivamente ONNX Runtime: nenhum código remoto é baixado/executado para construir o detector. Quantização dinâmica por canal em MatMul/Gemm, int8; convoluções float32; entrada fixa (1, 120320), 24 kHz, cinco segundos + 320 amostras de padding. Nenhuma normalização externa, conforme o loader de treinamento.

FaixaLab acrescenta confirmação em duas vistas (mistura e stem), predominância local solo/base, limiar de silêncio, continuidade temporal e verificação da textura polifônica antes de reduzir a transcrição para uma/duas vozes. Esses filtros não fazem parte do classificador original. Scores são evidências do modelo, sem calibração como probabilidades de acerto do aplicativo.

As letras, títulos, IDs e posições inicial/central/final da música não entram na decisão. Uma região sem solo confirmado permanece sem tablatura automática; não há fallback para transcrever a música inteira. As limitações e medições estão em `VALIDACAO.md`.
