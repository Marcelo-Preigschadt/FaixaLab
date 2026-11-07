# Validação — FaixaLab 0.4.0

Data: 06/11/2026. Linux x86-64, Python 3.12.14, ONNX Runtime 1.20.1 CPU, NumPy 1.26.4, librosa 0.11.0, Mido 1.3.3. O modelo neural foi realmente executado.

## Tablatura: notas, tempo e exportação

Áudio controlado de 5,4 s, com notas pinçadas sintéticas E4–G4–A4–B4–E5–D5–A4–G4, harmônicos e pausas. A transcrição ONNX retornou a sequência MIDI 64, 67, 69, 71, 76, 74, 69, 67. Desvio máximo dos ataques: 0.032 s. Foi verificado que afinação[corda] + casa = altura MIDI em cada nota.

O teste percorreu a API real, acompanhou a tarefa em segundo plano, leu MIDI novamente e conferiu alturas/tempos, exportou TXT e verificou CRC e arquivos do ZIP. Moveu E4 para a primeira corda solta, excluiu a última nota e recalculou com região 9–24. A posição corrigida permaneceu fora da nova região, e a nota excluída não reapareceu. O cenário completo levou 12.93 s nesta CPU, incluindo o primeiro carregamento/JIT. Dados: `tests/resultados/solo_integracao_0_4.json`.

Teste temporal longo: 203 s, com repetições da mesma sequência conhecida, total de 296 notas. Foram detectadas 296; 296 corresponderam à altura e ao ataque de referência dentro de 120 ms. Desvio máximo observado: 0.0234 s. Inferência e decodificação em 15.51 s nesta CPU, excluindo a geração do WAV. O teste cobre 124 janelas e verifica que seus offsets físicos não acumulam deriva na linha do tempo. Dados: `tests/resultados/solo_longo_0_4.json`.

Esses testes usam sons sintetizados simples e não estimam acerto em repertório real, guitarras distorcidas ou técnicas expressivas.

## Execução com guitarra real

EGSet12, gravação 01, trecho de 6 a 21 s. O modelo retornou 43 notas, todas com posições correspondentes à altura detectada, sem posições fora do braço. Tempo observado: 0.26 s, com o modelo/JIT já preparados. Não foi usada anotação alinhada para medir a correção das alturas nesse trecho. Origem: https://zenodo.org/records/11406378, CC BY 4.0. O áudio não acompanha o pacote. Dados: `tests/resultados/solo_guitarra_real_0_4.json`.

## Dicionário de acordes

Base pinned de tombatossals/chords-db, MIT. Foram normalizadas casas absolutas e conferidos os números MIDI, as notas permitidas, os intervalos obrigatórios, o baixo e a coerência básica dos dedos. A validação retirou 161 posições incompatíveis com a identidade definida e 9 com metadados de dedos inconsistentes. Duplicatas foram removidas; inversões sem indicação passaram a mostrar o baixo real. Resultado: 1.047 cifras, 3.078 posições, 44 famílias.

Todas as 3.078 posições passaram pelo verificador independente de alturas/baixo no teste Python e pelo validador usado na interface. O gerador preferencial anterior também passou pelos 174 acordes/inversões e pela digitação convencional de Bm/Cm/Fm/F#m. A fonte, o commit e os critérios estão em `faixalab/vendor/chords_db/ORIGEM.md`; o arquivo de dados é único para frontend e backend.

Isso verifica a correspondência cifra/diagrama. O catálogo não retreina BTC/CQT nem garante a identificação correta do acorde em áudio. Extensões podem omitir notas opcionais, conforme a definição da família. A ergonomia de todas as posições não foi avaliada com instrumentistas.

## Interface e verificações

- 19 testes unitários passaram: recursos anteriores, vocabulário de acordes, notas/bassos, posições simultâneas, MIDI, alinhamento de duas notas no TXT, exclusões e exportação de análise desatualizada.
- O teste de DOM percorreu cinco abas e sete faixas; conferiu abertura da tablatura ao selecionar Guitarra solo, duas notas exibidas, diálogo de edição, exportação MIDI, busca Bm e múltiplas posições no dicionário.
- O teste também conservou as verificações da linha do tempo de 203 s, análise anterior, zoom e pestana de Bm.
- JavaScript passou pela checagem de sintaxe; Python passou pela compilação. `uv pip check` verificou a compatibilidade dos 89 pacotes instalados.
- O áudio é simulado somente no teste de DOM. Não houve renderização visual da janela nem teste sonoro no WebView, instalador Windows ou GPU. O iniciador Windows x64 foi preservado; o perfil de dependências passou a 0.4.0.
- O pipeline de separação, os pesos de solo/base e a transcrição da letra não foram alterados. Suas medições anteriores permanecem em `VALIDACAO_0_2.md` e `VALIDACAO_0_3.md`.

## Limites da transcrição

Afinação padrão de seis cordas, casas 0–24, uma ou duas vozes selecionadas. Cordas/casas são sugestões de execução, pois a mesma altura pode ser tocada em posições diferentes. Bends, ligados, slides, vibrato e harmônicos não recebem símbolos de articulação. A grade visual usa 4/4 e BPM estimado; o MIDI e a tabela de notas preservam segundos, sem quantização ao compasso. O modelo pode produzir erros com vazamentos, distorção ou execuções rápidas. Notas podem ser editadas/excluídas; as alterações são preservadas quando solicitado. Transposição/capotraste da cifra não alteram a tablatura.
