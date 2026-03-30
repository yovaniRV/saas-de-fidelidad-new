$cfg = Get-Content "$env:USERPROFILE\.railway\config.json" | ConvertFrom-Json
$token = $cfg.user.accessToken
$headers = @{ "Authorization" = "Bearer $token"; "Content-Type" = "application/json" }

# Crear servicio PostgreSQL oficial de Railway
# Buscar el template de PostgreSQL disponible en Railway
$body = @{
  query = 'query { templates(searchTerm: "postgres") { edges { node { id code name services { edges { node { template } } } } } } }'
} | ConvertTo-Json

$resp = Invoke-RestMethod -Uri "https://backboard.railway.app/graphql/v2" -Method POST -Headers $headers -Body $body
Write-Host "Templates:" ($resp | ConvertTo-Json -Depth 8)
