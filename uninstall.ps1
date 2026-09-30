[CmdletBinding(SupportsShouldProcess = $true)]
param([string]$GamePath)
$ErrorActionPreference = 'Stop'
if (-not $GamePath) {
    $steamRoots = [System.Collections.Generic.List[string]]::new()
    foreach ($key in @('HKCU:\Software\Valve\Steam', 'HKLM:\Software\WOW6432Node\Valve\Steam', 'HKLM:\Software\Valve\Steam')) {
        try { $value = (Get-ItemProperty -LiteralPath $key -Name SteamPath).SteamPath; if ($value) { $steamRoots.Add($value) } } catch { }
    }
    foreach ($root in @("${env:ProgramFiles(x86)}\Steam", "$env:ProgramFiles\Steam")) { if (Test-Path -LiteralPath $root) { $steamRoots.Add($root) } }
    $found = @()
    foreach ($root in ($steamRoots | Select-Object -Unique)) {
        $libraries = @($root); $vdf = Join-Path $root 'steamapps\libraryfolders.vdf'
        if (Test-Path -LiteralPath $vdf) { $content = Get-Content -LiteralPath $vdf -Raw; $libraries += [regex]::Matches($content, '"path"\s+"([^"]+)"') | ForEach-Object { $_.Groups[1].Value.Replace('\\', '\') } }
        foreach ($library in ($libraries | Select-Object -Unique)) { $candidate = Join-Path $library 'steamapps\common\ARK Survival Ascended'; if ((Test-Path (Join-Path $library 'steamapps\appmanifest_2399830.acf')) -and (Test-Path -LiteralPath $candidate -PathType Container)) { $found += (Resolve-Path -LiteralPath $candidate).Path } }
    }
    $found = @($found | Select-Object -Unique)
    if ($found.Count -eq 0) { throw 'Steam did not reveal an installed ASA (App 2399830). Pass -GamePath explicitly.' }
    if ($found.Count -gt 1) { throw "Multiple ASA installs found. Pass -GamePath explicitly: $($found -join ', ')" }
    $GamePath = $found[0]
}
$target = Join-Path $GamePath 'ShooterGame\Content\Paks\ASA_RU_Fix_P.pak'
if (Test-Path -LiteralPath $target -PathType Leaf) {
    if ($PSCmdlet.ShouldProcess($target, 'Remove only ASA_RU_Fix_P.pak')) { Remove-Item -LiteralPath $target -Force }
} else { Write-Host "Patch file is not installed: $target" }
