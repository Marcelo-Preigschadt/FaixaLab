# Componentes de terceiros

O aplicativo contém código próprio e instala componentes de suas distribuições oficiais. Os modelos são fornecidos pelos respectivos projetos.

| Projeto | Fonte |
| --- | --- |
| Demucs | https://github.com/facebookresearch/demucs |
| faster-whisper | https://github.com/SYSTRAN/faster-whisper |
| Whisper | https://github.com/openai/whisper |
| PyTorch / torchaudio | https://pytorch.org/ |
| BTC-ISMIR19 — arquitetura e pesos pré-treinados, MIT | https://github.com/jayg996/BTC-ISMIR19 |
| Spotify Basic Pitch — modelo ONNX e decodificação de notas, Apache-2.0 | https://github.com/spotify/basic-pitch |
| Lead Instrument Detection — classificador de guitarra solo, código MIT | https://github.com/Sonata165/LeadInstrumentDetection |
| MERT-v1-95M — backbone do detector, CC BY-NC 4.0 | https://huggingface.co/m-a-p/MERT-v1-95M |
| chords-db — posições de acordes, MIT | https://github.com/tombatossals/chords-db |
| ONNX Runtime, MIT | https://github.com/microsoft/onnxruntime |
| Mido, MIT | https://github.com/mido/mido |
| librosa | https://librosa.org/ |
| yt-dlp e EJS | https://github.com/yt-dlp/yt-dlp |
| FFmpeg | https://ffmpeg.org/ |
| imageio-ffmpeg | https://github.com/imageio/imageio-ffmpeg |
| FastAPI | https://github.com/fastapi/fastapi |
| pywebview | https://github.com/r0x0r/pywebview |
| uv | https://github.com/astral-sh/uv |
| Deno | https://github.com/denoland/deno |

As licenças e avisos distribuídos com esses componentes permanecem aplicáveis às respectivas bibliotecas, binários e modelos. O instalador não substitui esses arquivos.

Modelos de guitarra solo/base: HTDemucs Lead/Rhythm (Dry Paint Dealer Undr) e alternativa Mel-Band RoFormer (listra92), distribuídos em https://huggingface.co/noblebarkrr/mvsepless_resources . Arquiteturas MIT e procedência em `faixalab/vendor/roformer`.

Basic Pitch: commit, hash do modelo e parâmetros em `faixalab/models/solo_notes_metadata.json`; licença e adaptações em `faixalab/vendor/basic_pitch`. Dicionário: commit, critérios de validação e licença em `faixalab/vendor/chords_db`.

Detector de solos: procedência, revisões, licença do backbone, permissões declaradas pelo repositório do classificador e alterações em `faixalab/vendor/solo_presence/ORIGEM.md`. Hashes e quantização em `faixalab/models/solo_presence_metadata.json`. A conversão para ONNX não amplia as permissões dos pesos originais. Código MERT/Transformers Apache-2.0 preservado para reconstrução em `tools/solo_detector_source`; nenhuma dependência Transformers é instalada pelo aplicativo.

Refinamento detalhado: MVSep Mega53 público v1.0.21 e BS-RoFormer, MIT; checkpoint oficial, configuração e hash em faixalab/models/mega53_metadata.json, procedência e adaptações em faixalab/vendor/bs_roformer. O modelo é baixado no primeiro uso e não integra o ZIP.

Identificação de timbres: EfficientAT MN10 AudioSet, MIT; modelo convertido para ONNX float32 e filtros Mel acompanham o aplicativo. Hashes em faixalab/models/instrument_id_metadata.json; origem e alterações em faixalab/vendor/instrument_id. Torchvision é dependência de reconstrução, não do runtime do aplicativo.
