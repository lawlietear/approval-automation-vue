param(
    [Parameter(Mandatory=$true)][ValidateSet('list','view','close','approve','status','unlock')][string]$Action,
    [string]$TaskId,
    [string]$Cdp = 'http://localhost:9222',
    [ValidateSet('old','new')][string]$System = 'old',
    [string]$PageUrl,
    [string]$Config,
    [string]$ReviewToken,
    [string]$ConfirmTaskId,
    [ValidateRange(1,10)][int]$Quantity = 1,
    [string]$BusinessType,
    [switch]$PasswordFromStdin
)
$ErrorActionPreference = 'Stop'
if ($Action -notin @('list','unlock') -and !$TaskId) { throw "$Action requires -TaskId. Run list first." }
if ($Action -in @('approve','status') -and !$ReviewToken) { throw 'Run view first and provide -ReviewToken.' }
if ($Action -eq 'approve' -and ($System -ne 'old' -or $ConfirmTaskId -ne $TaskId)) { throw 'Core approval requires explicit matching -ConfirmTaskId.' }
if ($Action -eq 'unlock' -and $System -ne 'old') { throw 'Session unlock only supports the core system.' }
if ($PasswordFromStdin -and $Action -ne 'unlock') { throw '-PasswordFromStdin only applies to unlock.' }
$runner = Join-Path $PSScriptRoot 'python/dist/ApprovalRunner/ApprovalRunner.exe'
if (!(Test-Path -LiteralPath $runner)) { throw 'Place this script beside ApprovalTool.exe in the portable edition.' }
if (!$Config) {
    $Config = Join-Path $env:LOCALAPPDATA 'com.yourcompany.approvaltool/Settings/config.json'
    if (!(Test-Path -LiteralPath $Config)) { $Config = Join-Path $PSScriptRoot 'python/dist/ApprovalRunner/config.json' }
}
$arguments = @('--config', $Config, '--cdp', $Cdp, '--oa-type', $System)
if ($Action -eq 'approve') { $arguments += @('--approve-task', '--confirm-task-id', $ConfirmTaskId, '--qty', "$Quantity") }
elseif ($Action -eq 'status') { $arguments += '--approval-status' }
elseif ($Action -eq 'unlock') { $arguments += '--unlock-session' }
else { $arguments += @('--read-action', $Action) }
if ($ReviewToken) { $arguments += @('--review-token', $ReviewToken) }
if ($BusinessType) { $arguments += @('--biz-type', $BusinessType) }
if ($TaskId) { $arguments += @('--task-id', $TaskId) }
if ($PageUrl) { $arguments += @('--page-url', $PageUrl) }
if ($Action -eq 'unlock') {
    $bstr = [IntPtr]::Zero
    $password = $null
    $previousEncoding = $OutputEncoding
    try {
        if ($PasswordFromStdin) {
            if (-not [Console]::IsInputRedirected) { throw 'Redirect stdin when using -PasswordFromStdin.' }
            $password = [Console]::In.ReadLine()
        } else {
            $secure = Read-Host '核心系统解锁密码' -AsSecureString
            $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        }
        if ([string]::IsNullOrEmpty($password)) { throw 'Unlock password is empty.' }
        $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
        $password | & $runner @arguments | ForEach-Object { $_ }
        $commandExit = $LASTEXITCODE
    } finally {
        $OutputEncoding = $previousEncoding
        $password = $null
        if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    }
    exit $commandExit
}
& $runner @arguments | ForEach-Object { $_ }
exit $LASTEXITCODE
