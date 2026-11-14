package io.github.faixalab.android;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

public final class ImportActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int spacing = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(spacing, spacing * 3, spacing, spacing);
        TextView title = new TextView(this);
        title.setText("Importador FaixaLab");
        title.setTextSize(26);
        layout.addView(title);
        TextView status = new TextView(this);
        status.setText("Volte ao FaixaLab no Chrome e selecione Importar neste aparelho. O importador fica ativo por cinco minutos de inatividade.");
        status.setTextSize(17);
        status.setPadding(0, spacing, 0, spacing);
        layout.addView(status);
        Button back = new Button(this);
        back.setText("Voltar ao navegador");
        back.setOnClickListener(view -> finish());
        layout.addView(back);
        setContentView(layout);
        startForegroundService(new Intent(this, ImportService.class));
    }
}
