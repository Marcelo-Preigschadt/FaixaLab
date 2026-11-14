package io.github.faixalab.android;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import java.io.IOException;

public final class ImportService extends Service {
    private static final String CHANNEL = "importacao";
    private static final int NOTIFICATION = 17862;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable idle = this::stopSelf;
    private LocalImporter importer;

    @Override public int onStartCommand(Intent intent, int flags, int id) {
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(CHANNEL, "Importação de áudio", NotificationManager.IMPORTANCE_LOW));
        PendingIntent activity = PendingIntent.getActivity(this, 0, new Intent(this, ImportActivity.class), PendingIntent.FLAG_IMMUTABLE);
        startForeground(NOTIFICATION, new Notification.Builder(this, CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download).setContentTitle("Importador FaixaLab")
            .setContentText("Disponível para o FaixaLab no Chrome").setContentIntent(activity).build());
        if (importer == null) {
            importer = new LocalImporter(getApplicationContext(), () -> handler.post(this::hold),
                () -> handler.post(this::resetIdle));
            try {
                importer.start(10000);
            } catch (IOException failure) {
                stopSelf();
                return START_NOT_STICKY;
            }
        }
        resetIdle();
        return START_NOT_STICKY;
    }

    private void hold() { handler.removeCallbacks(idle); }

    private void resetIdle() {
        hold();
        handler.postDelayed(idle, 300000);
    }

    @Override public void onTimeout(int startId, int foregroundServiceType) { stopSelf(); }

    @Override public void onDestroy() {
        hold();
        if (importer != null) importer.stop();
        super.onDestroy();
    }

    @Override public IBinder onBind(Intent intent) { return null; }
}
