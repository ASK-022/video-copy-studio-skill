# Windows one-command installer. No Git, shared key, or administrator session required.
param(
    [ValidateSet('auto','codex','claude','openclaw','custom')][string]$Agent = 'auto',
    [string]$SkillsDir = '',
    [string]$Python = '',
    [string]$RuntimeHome = '',
    [switch]$SkillOnly,
    [switch]$NoOpen
)

function Find-VcsPython {
    param([string]$Preferred)
    $candidates = @()
    if ($Preferred) { $candidates += @{ Command = $Preferred; Prefix = @() } }
    foreach ($version in @('3.12','3.11','3.10')) {
        if (Get-Command py -ErrorAction SilentlyContinue) { $candidates += @{ Command = 'py'; Prefix = @('-' + $version) } }
    }
    foreach ($name in @('python','python3')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and $command.Source -notmatch 'Microsoft[\\/]WindowsApps') { $candidates += @{ Command = $command.Source; Prefix = @() } }
    }
    foreach ($relative in @('Programs/Python/Python312/python.exe','Programs/Python/Python311/python.exe','Programs/Python/Python310/python.exe')) {
        $path = Join-Path $env:LOCALAPPDATA $relative
        if (Test-Path -LiteralPath $path) { $candidates += @{ Command = $path; Prefix = @() } }
    }
    $bundled = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (Test-Path -LiteralPath $bundled) { $candidates += @{ Command = $bundled; Prefix = @() } }
    foreach ($candidate in $candidates) {
        try {
            $arguments = @($candidate.Prefix) + @('-c', 'import sys,json; print(json.dumps(sys.executable)); sys.exit(0 if (3,10)<=sys.version_info[:2]<=(3,12) else 1)')
            $resolved = & $candidate.Command @arguments 2>$null
            if ($LASTEXITCODE -eq 0 -and $resolved) { return [string]((@($resolved)[-1]) | ConvertFrom-Json) }
        } catch { }
    }
    throw 'Python 3.10-3.12 was not found. Install Python 3.12 from https://www.python.org/downloads/windows/ and run this command again.'
}

function Get-VcsTargets {
    param([string]$Selected, [string]$CustomRoot)
    if ($Selected -eq 'custom') {
        if (-not $CustomRoot) { throw '-Agent custom requires -SkillsDir.' }
        return @([PSCustomObject]@{ Name = 'custom'; Path = [IO.Path]::GetFullPath($CustomRoot) })
    }
    if ($CustomRoot) { throw '-SkillsDir must be used with -Agent custom.' }
    $roots = [ordered]@{
        codex = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $env:USERPROFILE '.codex' })
        claude = $(if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $env:USERPROFILE '.claude' })
        openclaw = (Join-Path $env:USERPROFILE '.openclaw')
    }
    if ($Selected -ne 'auto') { return @([PSCustomObject]@{ Name = $Selected; Path = (Join-Path $roots[$Selected] 'skills') }) }
    $targets = @()
    foreach ($name in $roots.Keys) {
        if (Test-Path -LiteralPath $roots[$name] -PathType Container) { $targets += [PSCustomObject]@{ Name = $name; Path = (Join-Path $roots[$name] 'skills') } }
    }
    if ($targets.Count -eq 0) { $targets = @([PSCustomObject]@{ Name = 'codex'; Path = (Join-Path $roots['codex'] 'skills') }) }
    return $targets
}

$vcsOldErrorPreference = $ErrorActionPreference
$vcsOldConsoleEncoding = [Console]::OutputEncoding
$ErrorActionPreference = 'Stop'
$vcsTemp = $null
$vcsFailure = $null
try {
    if ($env:OS -ne 'Windows_NT') { throw 'The complete local runtime currently requires Windows 10/11.' }
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
    $vcsPython = Find-VcsPython $Python
    $vcsTargets = @(Get-VcsTargets $Agent $SkillsDir)
    $vcsRepo = 'ASK-022/video-copy-studio-skill'
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Write-Host '[1/4] Downloading the latest verified Skill release...'
    $vcsRelease = Invoke-RestMethod -Uri ('https://api.github.com/repos/' + $vcsRepo + '/releases/latest') -Headers @{ 'User-Agent' = 'video-copy-studio-setup'; Accept = 'application/vnd.github+json' }
    $vcsAsset = @($vcsRelease.assets | Where-Object { $_.name -match '^video-copy-studio-v[0-9]+\.[0-9]+\.[0-9]+\.zip$' })
    if ($vcsAsset.Count -ne 1) { throw 'The release does not contain exactly one Skill ZIP.' }
    $vcsAsset = $vcsAsset[0]
    $vcsChecksumAsset = @($vcsRelease.assets | Where-Object { $_.name -eq ($vcsAsset.name + '.sha256') })
    if ($vcsChecksumAsset.Count -ne 1) { throw 'The release is missing its SHA256 file.' }
    foreach ($item in @($vcsAsset, $vcsChecksumAsset[0])) {
        if (-not $item.browser_download_url.StartsWith('https://github.com/' + $vcsRepo + '/releases/download/')) { throw 'Unexpected release download address.' }
    }
    $vcsTempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    $vcsTemp = Join-Path $vcsTempRoot ('video-copy-studio-setup-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $vcsTemp | Out-Null
    $vcsZip = Join-Path $vcsTemp 'skill.zip'
    Invoke-WebRequest -UseBasicParsing -Uri $vcsAsset.browser_download_url -OutFile $vcsZip
    $vcsChecksumText = [string](Invoke-RestMethod -Uri $vcsChecksumAsset[0].browser_download_url)
    $vcsExpected = [regex]::Match($vcsChecksumText.Trim(), '^[a-fA-F0-9]{64}').Value
    if (-not $vcsExpected -or (Get-FileHash -LiteralPath $vcsZip -Algorithm SHA256).Hash -ne $vcsExpected) { throw 'SHA256 mismatch. Nothing was installed.' }
    $vcsUnpack = Join-Path $vcsTemp 'unpacked'
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $vcsArchive = [IO.Compression.ZipFile]::OpenRead($vcsZip)
    try {
        foreach ($entry in $vcsArchive.Entries) {
            $entryPath = [IO.Path]::GetFullPath((Join-Path $vcsUnpack $entry.FullName))
            if (-not $entryPath.StartsWith([IO.Path]::GetFullPath($vcsUnpack) + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe ZIP path.' }
            if ((($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw 'ZIP symbolic links are not supported.' }
        }
    } finally { $vcsArchive.Dispose() }
    Expand-Archive -LiteralPath $vcsZip -DestinationPath $vcsUnpack
    $vcsSource = Join-Path $vcsUnpack 'video-copy-studio'
    if (-not (Test-Path -LiteralPath (Join-Path $vcsSource 'SKILL.md'))) { throw 'The Skill entrypoint is missing.' }
    Write-Host '[2/4] Installing the Skill into detected Agent directories...'
    $vcsInstalled = @()
    foreach ($target in $vcsTargets) {
        $existingManifest = Join-Path $target.Path 'video-copy-studio/release.json'
        if (Test-Path -LiteralPath $existingManifest) {
            $existing = Get-Content -LiteralPath $existingManifest -Raw | ConvertFrom-Json
            if ($existing.repository -and $existing.repository -ne $vcsRepo) { throw ('A different Skill owns ' + $target.Path + '. Choose an explicit directory.') }
        }
        $resultText = & $vcsPython (Join-Path $vcsSource 'scripts/install_skill.py') --agent custom --skills-dir $target.Path --update
        if ($LASTEXITCODE -ne 0) { throw ('Skill installation failed: ' + $target.Name) }
        $result = ($resultText -join "`n") | ConvertFrom-Json
        $vcsInstalled += [string]$result.installed_path
        Write-Host ('  ' + $target.Name + ': ' + $result.installed_path)
    }
    $vcsPrimary = $vcsInstalled[0]
    if (-not $SkillOnly) {
        Write-Host '[3/4] Preparing the local runtime (first installation may take a while)...'
        $runtimeArguments = @()
        if ($RuntimeHome) { $runtimeArguments = @('--runtime-home', $RuntimeHome) }
        $doctorText = & $vcsPython (Join-Path $vcsPrimary 'scripts/studio_agent.py') @runtimeArguments doctor
        if ($LASTEXITCODE -ne 0) { throw 'Runtime inspection failed.' }
        $doctor = ($doctorText -join "`n") | ConvertFrom-Json
        if (-not ($doctor.data.service -and $doctor.data.service.ok -and $doctor.data.service.asr_ready)) {
            if (-not $doctor.data.runtime_registered) {
                & $vcsPython (Join-Path $vcsPrimary 'scripts/bootstrap.py') @runtimeArguments --install --download-ffmpeg
                if ($LASTEXITCODE -ne 0) { throw 'The Skill is installed, but runtime setup failed. See bootstrap.log and rerun the installer after fixing the error.' }
            }
            Write-Host '[4/4] Starting the local client...'
            $startArguments = @('start')
            if (-not $NoOpen) { $startArguments += '--open' }
            & $vcsPython (Join-Path $vcsPrimary 'scripts/studio_agent.py') @runtimeArguments @startArguments
            if ($LASTEXITCODE -ne 0) { throw 'The Skill is installed, but the local client did not start.' }
        } else { Write-Host '[4/4] Reusing the already-running local studio.' }
    } else { Write-Host '[3/4] Runtime setup skipped (-SkillOnly).'; Write-Host '[4/4] Skill installation complete.' }
    Write-Host ('Installed ' + $vcsRelease.tag_name + '. Restart your Agent or start a new chat. Configure your own AI Key in the local studio Settings.')
} catch {
    $vcsFailure = $_
} finally {
    if ($vcsTemp -and (Test-Path -LiteralPath $vcsTemp)) {
        $checked = [IO.Path]::GetFullPath($vcsTemp)
        $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
        if ($checked.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase) -and [IO.Path]::GetFileName($checked).StartsWith('video-copy-studio-setup-')) {
            Remove-Item -LiteralPath $checked -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
    $ErrorActionPreference = $vcsOldErrorPreference
    [Console]::OutputEncoding = $vcsOldConsoleEncoding
}
if ($null -ne $vcsFailure) { throw $vcsFailure }
