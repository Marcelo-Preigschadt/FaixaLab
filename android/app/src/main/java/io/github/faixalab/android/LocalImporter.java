package io.github.faixalab.android;

import android.content.Context;
import android.media.MediaExtractor;
import com.yausername.youtubedl_android.YoutubeDL;
import com.yausername.youtubedl_android.YoutubeDLRequest;
import fi.iki.elonen.NanoHTTPD;
import java.io.File;
import java.io.FileInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.net.URI;
import java.net.URLDecoder;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantLock;
import org.json.JSONObject;

final class LocalImporter extends NanoHTTPD {
    private static final int PORT = 17862;
    private static final String ORIGIN = "https://marcelo-preigschadt.github.io";
    private static final String PROCESS = "faixalab-youtube";
    private static final long LIMIT = 128L * 1024 * 1024;
    private final Context context;
    private final Runnable hold;
    private final Runnable idle;
    private final ReentrantLock lock = new ReentrantLock();
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();

    LocalImporter(Context context, Runnable hold, Runnable idle) {
        super("127.0.0.1", PORT);
        this.context = context;
        this.hold = hold;
        this.idle = idle;
    }

    @Override public Response serve(IHTTPSession session) {
        Map<String, String> headers = session.getHeaders();
        if (!("127.0.0.1:" + PORT).equals(headers.get("host")) || !ORIGIN.equals(headers.get("origin"))) {
            return newFixedLengthResponse(Response.Status.FORBIDDEN, MIME_PLAINTEXT, "Origem não autorizada.");
        }
        if (!"/import".equals(session.getUri())) return failure(Response.Status.NOT_FOUND, "Rota inexistente.");
        if (session.getMethod() == Method.OPTIONS) {
            Response preflight = cors(newFixedLengthResponse(Response.Status.NO_CONTENT, MIME_PLAINTEXT, ""));
            preflight.addHeader("Access-Control-Allow-Methods", "POST");
            preflight.addHeader("Access-Control-Allow-Headers", "Content-Type, X-FaixaLab-Import");
            preflight.addHeader("Access-Control-Allow-Private-Network", "true");
            return preflight;
        }
        if (session.getMethod() != Method.POST || !"1".equals(headers.get("x-faixalab-import"))) {
            return failure(Response.Status.FORBIDDEN, "Solicitação não autorizada.");
        }
        String id;
        try {
            int length = Integer.parseInt(headers.get("content-length"));
            if (length < 1 || length > 8192 || headers.containsKey("transfer-encoding") ||
                !headers.getOrDefault("content-type", "").startsWith("application/json")) {
                return failure(Response.Status.BAD_REQUEST, "Formato de solicitação inválido.");
            }
            byte[] body = new byte[length];
            new java.io.DataInputStream(session.getInputStream()).readFully(body);
            id = videoId(new JSONObject(new String(body, StandardCharsets.UTF_8)).getString("url"));
        } catch (Exception failure) {
            return failure(Response.Status.BAD_REQUEST, "Cole um link HTTPS válido de um vídeo do YouTube.");
        }
        if (!lock.tryLock()) return failure(Response.Status.CONFLICT, "Já existe uma importação em andamento.");
        hold.run();
        File directory = null;
        try {
            directory = Files.createTempDirectory(context.getCacheDir().toPath(), "audio-").toFile();
            return obtain(id, directory);
        } catch (Exception failure) {
            clean(directory);
            String message = String.valueOf(failure.getMessage()).toLowerCase(Locale.ROOT);
            boolean verification = message.contains("not a bot") || message.contains("sign in");
            return failure(Response.Status.SERVICE_UNAVAILABLE, verification
                ? "O YouTube pediu verificação nesta conexão."
                : "O importador Android não conseguiu obter o áudio deste vídeo.");
        } finally {
            lock.unlock();
            idle.run();
        }
    }

    private Response obtain(String id, File directory) throws Exception {
        YoutubeDL engine = YoutubeDL.INSTANCE;
        engine.init(context);
        YoutubeDLRequest download = new YoutubeDLRequest("https://www.youtube.com/watch?v=" + id)
            .addOption("--ignore-config").addOption("--no-playlist").addOption("--quiet")
            .addOption("--socket-timeout", 15).addOption("--retries", 1)
            .addOption("--max-filesize", "128M")
            .addOption("--match-filter", "!is_live & duration <= 1800")
            .addOption("-f", "bestaudio[acodec=opus]/bestaudio[acodec^=mp4a]/bestaudio")
            .addOption("-o", new File(directory, "audio.%(ext)s").getAbsolutePath());
        var watchdog = scheduler.schedule(() -> engine.destroyProcessById(PROCESS), 180, TimeUnit.SECONDS);
        try {
            engine.execute(download, PROCESS, false, null);
        } finally {
            watchdog.cancel(false);
        }
        File[] files = directory.listFiles((dir, name) -> name.matches("audio\\.(m4a|webm|opus|ogg|mp3)"));
        if (files == null || files.length != 1) throw new IOException("Áudio ausente.");
        File file = files[0];
        if (file.length() == 0 || file.length() > LIMIT) throw new IOException("Tamanho inválido.");
        validateAudio(file);
        String mime = file.getName().endsWith(".m4a") ? "audio/mp4" :
            file.getName().endsWith(".webm") ? "audio/webm" : "application/octet-stream";
        FilterInputStream result = new FilterInputStream(new FileInputStream(file)) {
            @Override public void close() throws IOException {
                try { super.close(); } finally { clean(directory); }
            }
        };
        Response response = cors(newFixedLengthResponse(Response.Status.OK, mime, result, file.length()));
        response.addHeader("X-FaixaLab-Filename", URLEncoder.encode(id + file.getName().substring(5), "UTF-8"));
        return response;
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

    private static Response cors(Response response) {
        response.addHeader("Access-Control-Allow-Origin", ORIGIN);
        response.addHeader("Access-Control-Expose-Headers", "X-FaixaLab-Filename");
        response.addHeader("Cache-Control", "no-store");
        response.addHeader("X-Content-Type-Options", "nosniff");
        response.addHeader("Vary", "Origin");
        return response;
    }

    private static Response failure(Response.Status status, String detail) {
        return cors(newFixedLengthResponse(status, "application/json", "{\"detail\":" + JSONObject.quote(detail) + "}"));
    }

    private static void clean(File directory) {
        if (directory == null) return;
        File[] files = directory.listFiles();
        if (files != null) for (File file : files) file.delete();
        directory.delete();
    }

    @Override public void stop() {
        YoutubeDL.INSTANCE.destroyProcessById(PROCESS);
        scheduler.shutdownNow();
        super.stop();
    }
}
