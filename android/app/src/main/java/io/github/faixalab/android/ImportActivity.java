package io.github.faixalab.android;

import android.app.Activity;
import android.content.ContentValues;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.text.InputType;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.File;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ImportActivity extends Activity {
    private static final int SAVE_AUDIO = 1;
    private static final String PROCESS = "faixalab-android-save";
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private EditText link;
    private TextView status;
    private Button save;
    private Button openFile;
    private File pending;
    private String pendingName;
    private Uri saved;
    private volatile boolean destroyed;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int spacing = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(spacing, spacing * 3, spacing, spacing);
        TextView title = new TextView(this);
        title.setText("FaixaLab Áudio");
        title.setTextSize(26);
        layout.addView(title);
        link = new EditText(this);
        link.setHint("Link do vídeo no YouTube");
        link.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        link.setSingleLine(true);
        link.setId(1001);
        layout.addView(link);
        Uri start = getIntent().getData();
        if (start != null && "salvar".equals(start.getHost())) {
            String candidate = start.getQueryParameter("url");
            if (candidate != null && candidate.length() <= 2000) link.setText(candidate);
        }

        save = new Button(this);
        save.setText("Salvar áudio no Android");
        save.setOnClickListener(view -> download());
        layout.addView(save);
        status = new TextView(this);
        status.setText("Cole o link para baixar o áudio. O resultado aparece aqui.");
        status.setTextSize(17);
        status.setPadding(0, spacing / 2, 0, spacing);
        layout.addView(status);

        openFile = new Button(this);
        openFile.setText("Abrir áudio salvo");
        openFile.setVisibility(Button.GONE);
        openFile.setOnClickListener(view -> openSavedFile());
        layout.addView(openFile);

        Button connect = new Button(this);
        connect.setText("Conectar ao Chrome para separar faixas");
        connect.setOnClickListener(view -> {
            startForegroundService(new Intent(this, ImportService.class));
            finish();
        });
        layout.addView(connect);
        if (start != null && "abrir".equals(start.getHost())) {
            startForegroundService(new Intent(this, ImportService.class));
            connect.setText("Voltar ao navegador");
            status.setText("O importador foi iniciado. Volte ao FaixaLab ou salve o áudio por aqui.");
        }
        ScrollView scroll = new ScrollView(this);
        scroll.addView(layout);
        setContentView(scroll);
    }

    private void download() {
        final String video;
        try {
            video = AudioExtractor.videoId(link.getText().toString());
        } catch (Exception invalid) {
            link.setError("Cole um link HTTPS válido do YouTube.");
            return;
        }
        save.setEnabled(false);
        openFile.setVisibility(Button.GONE);
        status.setText("Obtendo áudio do YouTube neste aparelho…");
        worker.execute(() -> {
            if (!AudioExtractor.lock.tryLock()) {
                display("Já existe uma importação em andamento. Tente após ela terminar.", null);
                return;
            }
            File directory = null;
            try {
                directory = Files.createTempDirectory(getCacheDir().toPath(), "download-").toFile();
                File audio = AudioExtractor.obtain(getApplicationContext(), video, directory, PROCESS);
                String name = "FaixaLab-" + video + AudioExtractor.suffix(audio);
                if (destroyed) return;
                if (Build.VERSION.SDK_INT >= 29) {
                    display("Áudio salvo em Downloads.", saveInDownloads(audio, name));
                } else {
                    File destination = audio;
                    runOnUiThread(() -> chooseDestination(destination, name));
                    directory = null;
                }
            } catch (IOException storage) {
                if (directory == null) display("O Android não conseguiu preparar a pasta temporária.", null);
                else display(storage instanceof StorageFailure ? "O Android não conseguiu gravar o arquivo em Downloads." : AudioExtractor.explain(storage), null);
            } catch (Exception failure) {
                display(AudioExtractor.explain(failure), null);
            } finally {
                AudioExtractor.clean(directory);
                AudioExtractor.lock.unlock();
            }
        });
    }

    private Uri saveInDownloads(File audio, String name) throws IOException {
        ContentValues values = new ContentValues();
        values.put(MediaStore.Downloads.DISPLAY_NAME, name);
        values.put(MediaStore.Downloads.MIME_TYPE, AudioExtractor.mime(audio));
        values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);
        values.put(MediaStore.Downloads.IS_PENDING, 1);
        Uri destination = null;
        boolean complete = false;
        try {
            Uri downloads = MediaStore.Downloads.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY);
            destination = getContentResolver().insert(downloads, values);
            if (destination == null) throw new IOException();
            copyAudio(audio, destination);
            values.clear();
            values.put(MediaStore.Downloads.IS_PENDING, 0);
            if (getContentResolver().update(destination, values, null, null) != 1) throw new IOException();
            complete = true;
            return destination;
        } catch (IOException | RuntimeException failure) {
            throw new StorageFailure(failure);
        } finally {
            if (!complete && destination != null) {
                try { getContentResolver().delete(destination, null, null); }
                catch (RuntimeException ignored) {}
            }
        }
    }

    private void chooseDestination(File audio, String name) {
        if (destroyed) {
            AudioExtractor.clean(audio.getParentFile());
            return;
        }
        pending = audio;
        pendingName = name;
        Intent chooser = new Intent(Intent.ACTION_CREATE_DOCUMENT);
        chooser.addCategory(Intent.CATEGORY_OPENABLE);
        chooser.setType(AudioExtractor.mime(audio));
        chooser.putExtra(Intent.EXTRA_TITLE, name);
        try {
            startActivityForResult(chooser, SAVE_AUDIO);
        } catch (RuntimeException failure) {
            pending = null;
            AudioExtractor.clean(audio.getParentFile());
            display("O seletor de arquivos do Android está indisponível.", null);
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request != SAVE_AUDIO || pending == null) return;
        File audio = pending;
        String name = pendingName;
        pending = null;
        Uri destination = data == null ? null : data.getData();
        if (result != RESULT_OK || destination == null) {
            AudioExtractor.clean(audio.getParentFile());
            display("O áudio ainda não foi salvo.", null);
            return;
        }
        worker.execute(() -> {
            try {
                copyAudio(audio, destination);
                display("Áudio salvo\n" + name, destination);
            } catch (Exception failure) {
                try { getContentResolver().delete(destination, null, null); }
                catch (RuntimeException ignored) {}
                display("O Android não conseguiu gravar o arquivo.", null);
            } finally {
                AudioExtractor.clean(audio.getParentFile());
            }
        });
    }

    private void copyAudio(File audio, Uri destination) throws IOException {
        try (OutputStream out = getContentResolver().openOutputStream(destination)) {
            if (out == null) throw new IOException();
            Files.copy(audio.toPath(), out);
        }
    }

    private void display(String message, Uri file) {
        runOnUiThread(() -> {
            if (destroyed) return;
            status.setText(message);
            save.setEnabled(true);
            saved = file;
            openFile.setVisibility(file == null ? Button.GONE : Button.VISIBLE);
        });
    }

    private void openSavedFile() {
        if (saved == null) return;
        Intent view = new Intent(Intent.ACTION_VIEW, saved).addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        try { startActivity(view); }
        catch (RuntimeException unavailable) {
            status.append("\nAbra o arquivo pelo app Arquivos do Android.");
        }
    }

    @Override protected void onDestroy() {
        destroyed = true;
        if (pending != null) AudioExtractor.clean(pending.getParentFile());
        worker.shutdown();
        super.onDestroy();
    }

    private static final class StorageFailure extends IOException {
        StorageFailure(Exception cause) { super(cause); }
    }
}
