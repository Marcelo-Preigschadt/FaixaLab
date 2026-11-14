$ErrorActionPreference = 'Stop'
$destination = (Get-Location).Path
$ready = Join-Path $destination '.runtime\ready'
$launcher = Join-Path $destination 'FaixaLab.exe'
$runtime = Join-Path $destination '.venv\Scripts\pythonw.exe'
if ((Test-Path $launcher) -and (Test-Path $runtime) -and
    (Test-Path $ready) -and (Get-Content $ready -Raw).Trim() -eq '0.10.1') {
    exit 0
}

$work = Join-Path ([IO.Path]::GetTempPath()) ('FaixaLab-' + [Guid]::NewGuid())
New-Item -ItemType Directory -Path $work | Out-Null
try {
    $zip = Join-Path $work 'FaixaLab.zip'
    $url = 'https://github.com/Marcelo-Preigschadt/FaixaLab/releases/download/v0.10.1/FaixaLab_0_10_1_Windows_playback1.zip'
    $expected = '1ea10e446b2d4e9cd5d04d3832ca7133e02fde5ae5beb94945b3024bb1940470'
    Write-Output 'Baixando o FaixaLab para Windows (142 MiB)...'
    & "$env:SystemRoot\System32\curl.exe" --fail --location --silent --show-error --retry 2 --max-time 600 --proto '=https' --output $zip $url
    if ($LASTEXITCODE -ne 0 -or (Get-FileHash $zip -Algorithm SHA256).Hash -ne $expected) {
        throw 'Falha ao verificar o download do FaixaLab.'
    }
    Write-Output 'Extraindo o aplicativo...'
    Expand-Archive -LiteralPath $zip -DestinationPath $work
    $source = Join-Path $work 'FaixaLab'
    if (!(Test-Path (Join-Path $source 'FaixaLab.exe'))) {
        throw 'O pacote do aplicativo veio incompleto.'
    }
    Copy-Item -Path (Join-Path $source '*') -Destination $destination -Recurse -Force
    $batch = Join-Path $destination 'INSTALAR.bat'
    $body = [IO.File]::ReadAllText($batch)
    [IO.File]::WriteAllText($batch, ($body -replace '(?m)^pause\r?$', ''))
    Write-Output 'Preparando o motor local de áudio...'
    & "$env:SystemRoot\System32\cmd.exe" /d /c INSTALAR.bat
    if ($LASTEXITCODE -ne 0 -or !(Test-Path $ready) -or !(Test-Path $runtime)) {
        throw 'O motor local de áudio não foi instalado.'
    }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue
}
