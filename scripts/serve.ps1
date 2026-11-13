# Minimal static file server for the docs/ folder.
# Usage: powershell -ExecutionPolicy Bypass -File scripts/serve.ps1 [-Port 8080]
param([int]$Port = 8080)
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\docs')).Path
$types = @{ '.html'='text/html; charset=utf-8'; '.css'='text/css; charset=utf-8'; '.js'='application/javascript; charset=utf-8';
            '.json'='application/json'; '.svg'='image/svg+xml'; '.png'='image/png'; '.ico'='image/x-icon'; '.bib'='text/plain' }
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add("http://localhost:$Port/")
$listener.Start()
Write-Host "Serving $root at http://localhost:$Port/"
while ($listener.IsListening) {
  $ctx = $listener.GetContext()
  try {
    $rel = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath.TrimStart('/'))
    if (-not $rel) { $rel = 'index.html' }
    $path = [IO.Path]::GetFullPath((Join-Path $root $rel))
    if (-not $path.StartsWith($root) -or -not (Test-Path $path -PathType Leaf)) {
      $ctx.Response.StatusCode = 404; $bytes = [Text.Encoding]::UTF8.GetBytes('Not found')
    } else {
      $ext = [IO.Path]::GetExtension($path).ToLower()
      $ctx.Response.ContentType = $(if ($types[$ext]) { $types[$ext] } else { 'application/octet-stream' })
      $ctx.Response.Headers.Add('Cache-Control', 'no-cache')
      $bytes = [IO.File]::ReadAllBytes($path)
    }
    $ctx.Response.ContentLength64 = $bytes.Length
    $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    Write-Host "$($ctx.Response.StatusCode) $($ctx.Request.Url.AbsolutePath)"
  } catch { Write-Host "error: $_" } finally { $ctx.Response.Close() }
}
