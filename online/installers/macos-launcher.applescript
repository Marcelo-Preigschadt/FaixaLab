on run
    set launcher to (POSIX path of (path to me)) & "Contents/Resources/Preparar.command"
    do shell script "/usr/bin/open -a Terminal " & quoted form of launcher
end run
