package io.github.faixalab.android;

import android.content.Context;
import com.yausername.youtubedl_android.YoutubeDL;
import fi.iki.elonen.NanoHTTPD;
import java.io.File;
import java.io.FileInputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Map;
import org.json.JSONObject;

final class LocalImporter extends NanoHTTPD {
    private static final int PORT = 17863;
    private static final String ORIGIN = "https://marcelo-preigschadt.github.io";
    private static final String PROCESS = "faixalab-youtube";
    private final Context context;
    private final Runnable hold;
    private final Runnable idle;

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
            id = AudioExtractor.videoId(new JSONObject(new String(body, StandardCharsets.UTF_8)).getString("url"));
        } catch (Exception failure) {
            return failure(Response.Status.BAD_REQUEST, "Cole um link HTTPS válido de um vídeo do YouTube.");
        }
        if (!AudioExtractor.lock.tryLock()) return failure(Response.Status.CONFLICT, "Já existe uma importação em andamento.");
        hold.run();
        File directory = null;
        try {
            directory = Files.createTempDirectory(context.getCacheDir().toPath(), "audio-").toFile();
            return obtain(id, directory);
        } catch (Exception failure) {
            AudioExtractor.clean(directory);
            return failure(Response.Status.SERVICE_UNAVAILABLE, AudioExtractor.explain(failure));
        } finally {
            AudioExtractor.lock.unlock();
            idle.run();
        }
    }

    private Response obtain(String id, File directory) throws Exception {
        File file = AudioExtractor.obtain(context, id, directory, PROCESS);
        FilterInputStream result = new FilterInputStream(new FileInputStream(file)) {
            @Override public void close() throws IOException {
                try { super.close(); } finally { AudioExtractor.clean(directory); }
            }
        };
        Response response = cors(newFixedLengthResponse(Response.Status.OK, AudioExtractor.mime(file), result, file.length()));
        response.addHeader("X-FaixaLab-Filename", URLEncoder.encode(id + AudioExtractor.suffix(file), "UTF-8"));
        return response;
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

    @Override public void stop() {
        YoutubeDL.INSTANCE.destroyProcessById(PROCESS);
        super.stop();
    }
}
