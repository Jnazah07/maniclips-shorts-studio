# Let phones on this Wi-Fi reach the Shortsmith engine on TCP 8080.
# Run as administrator: right-click > Run with PowerShell, or from an elevated
# PowerShell window:  powershell -File allow-phone-access.ps1
$ErrorActionPreference = "Stop"
$name = "Shortsmith engine (TCP 8080)"
$existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
if (-not $existing) {
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol TCP -LocalPort 8080 `
        -Action Allow -Profile Public,Private -Description "Shortsmith local engine (python server.py)" | Out-Null
    "Firewall rule created."
} else {
    "Firewall rule already present."
}
$r = Get-NetFirewallRule -DisplayName $name
$p = $r | Get-NetFirewallPortFilter
"$($r.DisplayName) | $($r.Action) | profiles: $($r.Profile) | TCP $($p.LocalPort)"
