[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$GamePath)
$ErrorActionPreference = 'Stop'
$patch = Join-Path $PSScriptRoot 'dist\ASA_RU_Fix_P.pak'
if (-not (Test-Path -LiteralPath $patch -PathType Leaf)) { throw "Patch PAK not found: $patch. Run python build.py first." }

function Find-AsaInstall {
    $steamRoots = [System.Collections.Generic.List[string]]::new()
    foreach ($key in @('HKCU:\Software\Valve\Steam', 'HKLM:\Software\WOW6432Node\Valve\Steam', 'HKLM:\Software\Valve\Steam')) {
        try { $value = (Get-ItemProperty -LiteralPath $key -Name SteamPath).SteamPath; if ($value) { $steamRoots.Add($value) } } catch { }
    }
    foreach ($root in @("${env:ProgramFiles(x86)}\Steam", "$env:ProgramFiles\Steam")) { if (Test-Path -LiteralPath $root) { $steamRoots.Add($root) } }
    $found = [System.Collections.Generic.List[string]]::new()
    foreach ($root in ($steamRoots | Select-Object -Unique)) {
        $vdf = Join-Path $root 'steamapps\libraryfolders.vdf'
        $libraries = [System.Collections.Generic.List[string]]::new(); $libraries.Add($root)
        if (Test-Path -LiteralPath $vdf) {
            $content = Get-Content -LiteralPath $vdf -Raw
            foreach ($match in [regex]::Matches($content, '"path"\s+"([^"]+)"')) { $libraries.Add($match.Groups[1].Value.Replace('\\', '\')) }
        }
        foreach ($library in ($libraries | Select-Object -Unique)) {
            $manifest = Join-Path $library 'steamapps\appmanifest_2399830.acf'
            $candidate = Join-Path $library 'steamapps\common\ARK Survival Ascended'
            if ((Test-Path -LiteralPath $manifest) -and (Test-Path -LiteralPath $candidate -PathType Container)) { $found.Add((Resolve-Path -LiteralPath $candidate).Path) }
        }
    }
    return @($found | Select-Object -Unique)
}

if (-not $GamePath) {
    $matches = @(Find-AsaInstall)
    if ($matches.Count -eq 0) { throw 'Steam did not reveal an installed ASA (App 2399830). Pass -GamePath explicitly.' }
    if ($matches.Count -gt 1) { throw "Multiple ASA installs found. Pass -GamePath explicitly: $($matches -join ', ')" }
    $GamePath = $matches[0]
}
$destination = Join-Path $GamePath 'ShooterGame\Content\Paks\ASA_RU_Fix_P.pak'
if ($PSCmdlet.ShouldProcess($destination, 'Copy/replace only ASA_RU_Fix_P.pak')) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
    Copy-Item -LiteralPath $patch -Destination $destination -Force
}
Write-Host "Patch target: $destination"
