# Importador FaixaLab para Android

O app **FaixaLab Áudio** obtém o áudio com yt-dlp e QuickJS no Android. Abra o
aplicativo e cole o link ou use **Salvar no app Android** no site. O arquivo
fica em Downloads no Android 10 ou mais recente. No Android 8 e 9, o sistema
pede que o usuário escolha o destino. O aplicativo confirma a gravação na
própria tela e permite abrir o arquivo salvo.

Para separar pelo site, **Abrir importador** ativa o serviço local por cinco
minutos de inatividade. Ele escuta em 127.0.0.1:17863 e aceita chamadas apenas
da origem HTTPS do FaixaLab. O navegador recebe o áudio e o envia ao servidor
de separação. O serviço local não usa credenciais do Codespace.

## Compilação

JDK 17+, Gradle 8.11.1 e Android SDK 35.

```sh
gradle -p android :app:assembleDebug
```

O build baixa o executável do mesmo yt-dlp adotado no desktop (2026.10.26) e
confere o SHA-256 antes de incluí-lo no APK. O runtime Python e o QuickJS vêm
de [youtubedl-android 0.18.1](https://github.com/yausername/youtubedl-android).
O servidor HTTP usa [NanoHTTPD](https://github.com/NanoHttpd/nanohttpd).
