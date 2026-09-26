param([Parameter(Mandatory=$true)][string]$JobFile, [switch]$NoRelaunch)
$ErrorActionPreference = 'Stop'
$job = Get-Content -LiteralPath $JobFile -Raw -Encoding UTF8 | ConvertFrom-Json
$root = [IO.Path]::GetFullPath($job.root).TrimEnd('\', '/')
$stage = [IO.Path]::GetFullPath($job.stage).TrimEnd('\', '/')
if ([IO.Path]::GetDirectoryName($stage) -ne $root -or -not [IO.Path]::GetFileName($stage).StartsWith('.approval-update-')) { throw 'Invalid staging path' }
[IO.File]::WriteAllText((Join-Path $stage 'ready'), 'ready')
$paths = @('ApprovalTool.exe', 'python/dist/ApprovalRunner/ApprovalRunner.exe', 'python/dist/ApprovalRunner/_internal')
$moved = @()
$installed = @()
$success = $false
try {
    if ($job.pid -gt 0) { Wait-Process -Id $job.pid -Timeout 60 -ErrorAction SilentlyContinue }
    if ($job.pid -gt 0 -and (Get-Process -Id $job.pid -ErrorAction SilentlyContinue)) { throw 'Approval tool did not exit; no files replaced' }
    foreach ($relative in $paths) {
        if (-not (Test-Path -LiteralPath (Join-Path "$stage/new" $relative))) { throw "Incomplete update: $relative" }
        $target = [IO.Path]::GetFullPath((Join-Path $root $relative))
        if (-not $target.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe target' }
        # Reject junctions/symlinks: replacement must stay inside the program folder.
        $check = $target
        while ($check -ne $root) {
            if ((Test-Path -LiteralPath $check) -and ((Get-Item -LiteralPath $check -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Linked program paths are not supported for updating' }
            $check = [IO.Path]::GetDirectoryName($check)
        }
    }
    foreach ($relative in $paths) {
        $target = Join-Path $root $relative
        $old = Join-Path "$stage/old" $relative
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($old)) -Force | Out-Null
        if (Test-Path -LiteralPath $target) {
            Move-Item -LiteralPath $target -Destination $old
            $moved += $relative
        }
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($target)) -Force | Out-Null
        Move-Item -LiteralPath (Join-Path "$stage/new" $relative) -Destination $target
        $installed += $relative
    }
    $success = $true
    @{ ok=$true; message="Updated to $($job.version)" } | ConvertTo-Json | Set-Content -LiteralPath $job.result -Encoding UTF8
} catch {
    $failure = $_.Exception.Message
    # Temporary rollback is only for a failed replacement, not a configuration backup feature.
    try {
        foreach ($relative in $installed) {
            $target = [IO.Path]::GetFullPath((Join-Path $root $relative))
            if (-not $target.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe rollback target' }
            Move-Item -LiteralPath $target -Destination (Join-Path "$stage/new" $relative)
        }
        foreach ($relative in $moved) { Move-Item -LiteralPath (Join-Path "$stage/old" $relative) -Destination (Join-Path $root $relative) }
    } catch { $failure += '; rollback could not complete: ' + $_.Exception.Message }
    @{ ok=$false; message=$failure } | ConvertTo-Json | Set-Content -LiteralPath $job.result -Encoding UTF8
}
if (-not $NoRelaunch -and (Test-Path -LiteralPath (Join-Path $root 'ApprovalTool.exe'))) {
    Start-Process -FilePath (Join-Path $root 'ApprovalTool.exe') -WorkingDirectory $root -WindowStyle Hidden
}
if ($success) {
    # This fresh, validated staging directory contains only update-owned files.
    if ([IO.Path]::GetDirectoryName($stage) -eq $root -and [IO.Path]::GetFileName($stage).StartsWith('.approval-update-')) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
if (-not $success) { exit 1 }
