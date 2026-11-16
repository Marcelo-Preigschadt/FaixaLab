$ErrorActionPreference = 'Stop'

$runtime = [IO.Path]::GetFullPath('.runtime')
$nativeArch = $env:PROCESSOR_ARCHITEW6432
if (!$nativeArch) { $nativeArch = $env:PROCESSOR_ARCHITECTURE }
$arch = if ($nativeArch -eq 'ARM64') { 'aarch64' } else { 'x86_64' }

$release = Invoke-RestMethod 'https://api.github.com/repos/astral-sh/uv/releases/latest'
$asset = $release.assets | Where-Object { $_.name -eq "uv-$arch-pc-windows-msvc.zip" } | Select-Object -First 1
if (!$asset) { throw 'Pacote uv indisponivel.' }

$temporary = Join-Path $runtime ('uv-' + [Guid]::NewGuid())
[IO.Directory]::CreateDirectory($temporary) | Out-Null
try {
    $archive = Join-Path $temporary 'uv.zip'
    Invoke-WebRequest -UseBasicParsing $asset.browser_download_url -OutFile $archive
    if ($asset.digest -and $asset.digest.StartsWith('sha256:')) {
        $sha = [Security.Cryptography.SHA256]::Create()
        $stream = [IO.File]::OpenRead($archive)
        try {
            $hash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
            if ($hash -ne $asset.digest.Substring(7)) { throw 'Falha na verificacao do uv.' }
        } finally {
            $stream.Dispose()
            $sha.Dispose()
        }
    }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $entry = $zip.Entries | Where-Object { $_.Name -eq 'uv.exe' } | Select-Object -First 1
        if (!$entry) { throw 'Executavel uv.exe ausente no pacote.' }
        $binary = Join-Path $temporary 'uv.exe'
        [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $binary)
    } finally {
        $zip.Dispose()
    }
    Move-Item -LiteralPath $binary -Destination (Join-Path $runtime 'uv.exe') -Force
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force -ErrorAction SilentlyContinue
}
