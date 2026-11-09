# Validação FaixaLab 0.10.1 — importação do YouTube

## Reprodução do erro relatado

Em 09/11/2026, com Python 3.12.14, yt-dlp 2026.10.26 e EJS 0.8.0, o vídeo `u_ix058WpVo` retornou exatamente `This video is not available` quando os runtimes JavaScript foram desativados. Esse resultado reproduz a mensagem, mas não identifica sozinho a configuração do computador afetado.

Com Node 24.22.1, a extração do mesmo vídeo retornou o título “Renato Quase Russo - Que país é este (Acústico no teatro)” e duração de 235 segundos. O link `C51rj1HJmpU` também retornou título e duração. O preparo portátil do Deno foi executado realmente em Linux: baixou Deno 2.9.8, validou o tamanho e o SHA-256 publicado no asset do GitHub e testou o executável. Com esse Deno, o vídeo relatado retornou o mesmo título/duração e cinco formatos que continham áudio.

A tentativa de baixar o arquivo completo nesta conexão retornou 195 bytes de HTML no lugar do áudio. O guard existente rejeitou e excluiu esse arquivo. Portanto, a recuperação da extração foi observada, mas o download completo do áudio não foi validado aqui. Não houve teste nativo Windows nem acesso ao log do computador do usuário. Não se afirma que a atualização elimine restrições de acesso ou todas as causas possíveis de falha no YouTube.

## Falhas corrigidas

- Um Deno global antigo era escolhido antes do Deno privado informado pelo iniciador. O executável não era validado e sua presença impedia a tentativa com Node. Agora se verifica execução/versão, prioriza-se a configuração privada e descartam-se candidatos incompatíveis.
- A descoberta do runtime privado dependia do BAT do Windows. Agora também funciona pelo launcher Python, pelo servidor e fora do diretório do app. O preparo Linux instala um runtime privado quando não encontra Deno 2.3+ ou Node 22+.
- O instalador podia manter um yt-dlp antigo que ainda satisfazia `>=2026.3.3`. Agora exige no mínimo a versão estável 2026.10.26, atualiza o grupo `default` e confere o EJS correspondente antes de concluir.
- O atualizador verificava apenas a instalação do pacote Python. Agora valida/prepara também o runtime. Uma atualização concluída da 0.10 reaproveita o perfil de áudio e não dispara sua reinstalação no próximo início.
- Avisos do extrator eram descartados e sequências ANSI chegavam à interface. Agora os detalhes são normalizados e versões, runtime, avisos e erro ficam em `youtube-diagnostico.json`, na pasta local do projeto.
- A mensagem genérica de indisponibilidade deixa de sugerir que a disponibilidade do vídeo é a única explicação. Restrições explícitas de acesso continuam distintas.

Nenhum ID, título ou artista determina o comportamento de produção. O ID do relato aparece somente nos testes e neste registro de validação.

## Testes

Foram aprovados 16 testes específicos, cobrindo runtime privado, Deno antigo, fallback para Node, timeout de executável, EJS ausente/incompatível, extrator antigo, validação anterior à rede, URL canônica, cancelamento, normalização de erro, diagnóstico, arquivo vazio, HTML no lugar do áudio e preservação do runtime anterior diante de download corrompido.

Também passaram as nove regressões existentes do player e as 174 verificações dos diagramas de acordes. A inferência e os pesos dos modelos não mudaram nesta correção; não se repetiu o benchmark completo de separação da 0.10.

```sh
PYTHONPATH=app python -m unittest discover -s app/tests -p test_youtube_import.py -v
python app/prepare_youtube.py --check
node app/tests/test_player.cjs
node app/tests/test_guitar.js
```

Referências primárias: [requisitos EJS e runtimes](https://github.com/yt-dlp/yt-dlp/wiki/EJS), [versão estável 2026.10.26](https://github.com/yt-dlp/yt-dlp/releases/tag/2026.10.26).
