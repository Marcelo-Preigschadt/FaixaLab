# Validação FaixaLab 0.8 — velocidade e uso na nuvem

Execução em Linux, Python 3.12, PyTorch 2.5.1 CPU e ONNX Runtime 1.20.1. A comparação do separador usa uma cópia imutável da versão 0.7, os mesmos pesos Mega53 e o mesmo trecho estéreo de seis segundos. São medições pontuais de inferência, sem download nem etapas restantes do pipeline; não representam o tempo total de uma música.

| Verificação | Resultado observado |
| --- | --- |
| Mega53, todos os 33 candidatos, quatro threads | 14,308 s → 10,996 s; redução de 23,2% |
| Erro de áudio máximo / RMS, quatro threads | 5,96 × 10⁻⁸ / 7,38 × 10⁻¹⁰ |
| Mega53, duas threads, referência/otimizado | 16,582 s → 16,028 s; redução de 3,3% |
| MERT, controle de 60 s com guitarra gravada e regiões limitadas | 14,370 s → 5,378 s; 120 → 46 chamadas; seções iguais e vazias |
| Basic Pitch, cinco segundos de guitarra gravada | primeira execução 6,362 s; nova digitação por cache ≈1 ms; 14 notas com tempos e alturas idênticos; zero chamadas de inferência na segunda execução |
| Regressões Python, lógica e API | 43 testes aprovados |
| Diagramas de acordes | 174 diagramas aprovados; posições e pestana de Bm conferidas |
| DOM do estúdio e importação automática | aprovados, cinco abas, 33 categorias, backing track, correção de notas e música de 203 s; zero erros de DOM |
| Áudio móvel real | FFmpeg/AAC: remove voz de 440 Hz e solo de 660 Hz; conserva base de 220 Hz; cache reaproveitado e HTTP Range 206 |
| Origem Codespaces | origem HTTPS da porta privada aceita; origem externa rejeitada com 403 |

O ensaio MERT com áudio gravado não contém um solo positivo confirmado pelo detector. Ele verifica equivalência e custo, sem demonstrar sensibilidade do detector. Regressões adicionais com seções positivas em três posições verificam que a máscara de contextos preserva exatamente os intervalos decodificados. Não houve novo treinamento de modelo nem avaliação anotada de repertório real nesta revisão.

O teste de cache real usa o modo de faixa inteira para medir Basic Pitch, sem forçar a confirmação de um solo. As verificações de cache com revisão diferente repetem a inferência; mudanças de casas preservam notas, correções e exclusões no pós-processamento.

## Escopo verificado

Os testes não usam regras por música, título, artista ou ID de YouTube. Os controles gravados vêm das mesmas referências externas de guitarra registradas nas versões anteriores. Os áudios não são redistribuídos.

A conferência visual em navegador não foi concluída: o serviço de prévia deste ambiente não dispõe do runtime Python usado pelo backend. DOM, sintaxe, arquivos estáticos e APIs foram verificados. Reprodução física em um celular e caixa Bluetooth não foi testada. O comportamento de tela bloqueada depende do navegador e do sistema operacional; o arquivo M4A pode ser baixado e aberto pelo player do celular.

A instalação automática e a URL de uma instância real do GitHub dependem de autenticação na conta e de franquia disponível. Preparar a configuração local não significa que o app já esteja hospedado. Não há medição de desempenho em uma máquina real do Codespaces nesta revisão.

A execução Windows nativa não foi repetida neste ambiente Linux. O iniciador existente chama os scripts Windows, atualizados para 0.8.0. Os motores e pesos continuam os mesmos; a validação de separação e instrumentos da versão 0.7 permanece em VALIDACAO_0_7.md.

## Reproduzir as verificações

```sh
python -m unittest discover -s tests -p 'test_*.py'
node tests/test_guitar.js
NODE_PATH=/caminho/node_modules node tests/test_automatic_ui.cjs
NODE_PATH=/caminho/node_modules node tests/test_studio_ui.cjs
```

As duas verificações DOM usam jsdom 26.1.0 como dependência de desenvolvimento. As métricas numéricas estão em `tests/resultados/velocidade_0_8.json`.
