# Importador FaixaLab para Android

O aplicativo instala o extrator yt-dlp e o runtime QuickJS no Android. O botão
**Abrir importador** do FaixaLab inicia o aplicativo. Ao voltar para a mesma aba
no Chrome, **Importar neste aparelho** envia o link para o serviço local. O
aplicativo volta a parar após cinco minutos sem atividade.

O serviço escuta em 127.0.0.1:17862 e aceita chamadas apenas da origem HTTPS do
FaixaLab. O navegador recebe o áudio e pode salvá-lo ou enviá-lo ao servidor
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
