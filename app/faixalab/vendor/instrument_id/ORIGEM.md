# EfficientAT — identificação independente de timbres

Fonte oficial: https://github.com/fschmid56/EfficientAT , revisão `a425fdce92572e602a1d5634799bd9f1f2efa806`. Modelo MN10 treinado em AudioSet, `mn10_as_mAP_471.pt`, release v0.0.1. Licença MIT anexa. Trabalhos dos autores: Efficient Large-Scale Audio Tagging Via Transformer-To-CNN Knowledge Distillation, ICASSP 2023, e Dynamic Convolutional Neural Networks as Efficient Pre-trained Audio Models.

O modelo foi convertido para ONNX float32, sem quantização. O checkpoint não acompanha a instalação; o ONNX de inferência e os filtros do frontend já estão no pacote. O runtime utiliza ONNX Runtime e NumPy/SciPy, sem Torchvision. Código de origem necessário à reconstrução em tools/instrument_id_source; script em tools/build_instrument_id.py.

Pré-processamento idêntico ao eval upstream: mono a 32 kHz; preênfase 0,97; STFT 1.024, janela Hann não periódica de 800 amostras centrada, hop 320; banco Mel Kaldi de 128 bandas, 0–15 kHz; log com epsilon 1e-5; normalização `(logmel + 4.5) / 5`. As 527 classes têm saídas sigmoid independentes. Não se aplica softmax nem seleção forçada de um único instrumento.

O frontend NumPy e o grafo ONNX foram comparados com o modelo PyTorch em doze contextos reais de cinco segundos. Diferença máxima de saída inferior a 1e-6; diferença do Mel inferior a 1,1e-5. Pesos, hashes do grafo e dos filtros, labels e versões estão em models/instrument_id_metadata.json.

O aplicativo usa essa evidência para reconhecer instrumentos em fontes existentes, conferir saídas da separação e impedir uma tablatura de guitarra quando há evidência mais forte de acordeon/gaita de boca ou outro instrumento. Um rótulo de arquivo não é usado como prova de timbre. Scores são evidências do classificador, não porcentagens calibradas de acerto. Repertório, efeitos e vazamentos ainda podem causar erros.
