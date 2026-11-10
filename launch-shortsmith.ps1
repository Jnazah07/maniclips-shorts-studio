# Shortsmith launcher: starts the local engine if needed, then opens the app window.
$ErrorActionPreference = "SilentlyContinue"
$root    = "C:\Users\Hina\Documents\Default Project\shortsmith"
$py      = "C:\Users\Hina\AppData\Local\Programs\Python\Python312\python.exe"
$chrome  = "C:\Program Files\Google\Chrome\Application\chrome.exe"
$edge    = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
$url     = "http://127.0.0.1:8080/"

function Test-Engine {
    try {
        $r = Invoke-WebRequest -Uri "$url/api/health" -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch { return $false }
}

if (-not (Test-Path $root)) { exit 1 }

# Single instance: focus the app window if it is already open instead of stacking another one.
Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes -ErrorAction SilentlyContinue
$desktop = [System.Windows.Automation.AutomationElement]::RootElement
$children = $desktop.FindAll([System.Windows.Automation.TreeScope]::Children,
                              [System.Windows.Automation.Condition]::TrueCondition)
foreach ($w in $children) {
    $name = $w.Current.Name
    if ($name -and $name -like "Shortsmith*" -and $name -notlike "*Google Chrome*") {
        try {
            $wp = $w.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern)
            $wp.SetWindowVisualState([System.Windows.Automation.WindowVisualState]::Normal)
        } catch { }
        try { $w.SetFocus() } catch { }
        exit 0
    }
}

if (-not (Test-Engine)) {
    if (Test-Path $py) {
        Start-Process -FilePath $py -ArgumentList "server.py" -WorkingDirectory $root
        foreach ($i in 1..40) {
            Start-Sleep -Seconds 1
            if (Test-Engine) { break }
        }
    }
}

$browser = $null
if (Test-Path $chrome) { $browser = $chrome }
elseif (Test-Path $edge) { $browser = $edge }

if ($browser) {
    Start-Process -FilePath $browser -ArgumentList "--app=$url", "--window-size=1300,900", "--window-position=90,50"
} else {
    Start-Process $url
}
