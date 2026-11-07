# Origem do reconhecedor BTC

Autor: Jonggwon Park. Projeto: https://github.com/jayg996/BTC-ISMIR19

Commit utilizado: `2682317be668032e6e4b269ded36adaa2ad57df0`.

A licença MIT original está em `LICENSE`. A arquitetura deriva de `btc_model.py` e `utils/transformer_modules.py`. Adaptações: imports relativos, remoção do carregador de configuração de treinamento e do bloco executável de demonstração, e substituição do alias NumPy removido `np.float` por `float`.

Os pesos originais são `test/btc_model.pt` e `test/btc_model_large_voca.pt`. Foram convertidos para manter apenas o state_dict e os parâmetros numéricos de normalização. Não houve retreinamento. Os hashes de origem e dos arquivos convertidos, a configuração e o número de classes estão em `../../models/btc_metadata.json`.

A implementação FaixaLab acrescenta contexto sobreposto, marcação temporal baseada no hop real, fusão dos dois reconhecedores, evidência espectral e análise de baixo. Esses componentes estão fora do código vendorizado.
