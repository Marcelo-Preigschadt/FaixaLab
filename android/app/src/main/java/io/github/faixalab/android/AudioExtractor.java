package io.github.faixalab.android;

import android.content.Context;
import android.media.MediaExtractor;
import com.yausername.youtubedl_android.YoutubeDL;
import com.yausername.youtubedl_android.YoutubeDLRequest;
import java.io.File;
import java.io.IOException;
import java.net.URI;
import java.net.URLDecoder;
import java.util.Locale;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;

final class AudioExtractor {
    private static final long LIMIT = 128L * 1024 * 1024;
    static final ReentrantLock lock = new ReentrantLock();
    private static final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();

    private AudioExtractor() {}

    static File obtain(Context context, String id, File directory, String process) throws Exception {
        YoutubeDL engine = YoutubeDL.INSTANCE;
        engine.init(context);
        YoutubeDLRequest download = new YoutubeDLRequest("https://www.youtube.com/watch?v=" + id)
            .addOption("--ignore-config").addOption("--no-playlist").addOption("--quiet")
            .addOption("--socket-timeout", 15).addOption("--retries", 1)
            .addOption("--max-filesize", "128M")
            .addOption("--match-filter", "!is_live & duration <= 1800")
            .addOption("-f", "bestaudio[acodec=opus]/bestaudio[acodec^=mp4a]/bestaudio")
            .addOption("-o", new File(directory, "audio.%(ext)s").getAbsolutePath());
        var watchdog = scheduler.schedule(() -> engine.destroyProcessById(process), 180, TimeUnit.SECONDS);
        try {
            engine.execute(download, process, false, null);
        } finally {
            watchdog.cancel(false);
        }
        File[] files = directory.listFiles((dir, name) -> name.matches("audio\\.(m4a|webm|opus|ogg|mp3)"));
        if (files == null || files.length != 1) throw new IOException("Áudio ausente.");
        File file = files[0];
        if (file.length() == 0 || file.length() > LIMIT) throw new IOException("Tamanho inválido.");
        validateAudio(file);
        return file;
    }

    private static void validateAudio(File file) throws IOException {
        MediaExtractor extractor = new MediaExtractor();
        try {
            extractor.setDataSource(file.getAbsolutePath());
            for (int i = 0; i < extractor.getTrackCount(); i++) {
                String mime = extractor.getTrackFormat(i).getString("mime");
                if (mime != null && mime.startsWith("audio/")) return;
            }
            throw new IOException("Áudio inválido.");
        } finally {
            extractor.release();
        }
    }

    static String videoId(String raw) throws Exception {
        if (raw == null || raw.length() > 2000) throw new IOException();
        URI url = new URI(raw.trim());
        if (!"https".equalsIgnoreCase(url.getScheme()) || url.getUserInfo() != null ||
            (url.getPort() != -1 && url.getPort() != 443) || url.getHost() == null) throw new IOException();
        String host = url.getHost().toLowerCase(Locale.ROOT);
        String path = url.getPath();
        String id = "";
        if ("youtu.be".equals(host) || "www.youtu.be".equals(host)) {
            id = path.replaceFirst("^/", "").split("/", -1)[0];
        } else if (host.matches("(www\\.|m\\.|music\\.)?youtube\\.com")) {
            if ("/watch".equals(path) && url.getRawQuery() != null) {
                for (String entry : url.getRawQuery().split("&")) {
                    if (entry.startsWith("v=")) {
                        id = URLDecoder.decode(entry.substring(2), "UTF-8");
                        break;
                    }
                }
            } else if (path.matches("/(shorts|live|embed)/[^/]+/?")) {
                id = path.split("/")[2];
            }
        }
        if (!id.matches("[A-Za-z0-9_-]{11}")) throw new IOException();
        return id;
    }

    static String mime(File file) {
        return switch (suffix(file)) {
            case ".m4a" -> "audio/mp4";
            case ".webm" -> "audio/webm";
            case ".opus", ".ogg" -> "audio/ogg";
            case ".mp3" -> "audio/mpeg";
            default -> "application/octet-stream";
        };
    }

    static String suffix(File file) { return file.getName().substring(5); }

    static String explain(Exception failure) {
        String message = String.valueOf(failure.getMessage()).toLowerCase(Locale.ROOT);
        if (message.contains("not a bot") || message.contains("sign in")) {
            return "O YouTube pediu verificação para este vídeo nesta conexão.";
        }
        if (message.contains("unsupported javascript") || message.contains("no supported javascript")) {
            return "O motor JavaScript do importador está indisponível.";
        }
        if (message.contains("private video") || message.contains("video has been removed")) {
            return "O YouTube restringiu o acesso ao vídeo.";
        }
        if (message.contains("filter") || message.contains("does not pass")) {
            return "Use um vídeo gravado com até 30 minutos.";
        }
        if (failure instanceof YoutubeDL.CanceledException) {
            return "A importação foi interrompida ou excedeu três minutos.";
        }
        return "O importador Android não conseguiu obter um áudio válido deste vídeo.";
    }

    static void clean(File directory) {
        if (directory == null) return;
        File[] files = directory.listFiles();
        if (files != null) for (File file : files) file.delete();
        directory.delete();
    }

}
