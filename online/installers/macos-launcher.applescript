on run
    set launcher to (POSIX path of (path to me)) & "Contents/Resources/Preparar.sh"
    set progress description to "Iniciando Importador FaixaLab"
    set progress additional description to "Preparando os componentes de áudio…"
    try
        with timeout of 600 seconds
            do shell script "/bin/bash " & quoted form of launcher
        end timeout
        display dialog "Importador ativo. Volte ao FaixaLab e cole o link do YouTube." with title "Importador FaixaLab" buttons {"OK"} default button "OK"
    on error
        display alert "Falha ao iniciar o Importador FaixaLab" message "O diagnóstico está na pasta Biblioteca/Application Support/FaixaLab/Importador/.runtime." as critical
    end try
end run
