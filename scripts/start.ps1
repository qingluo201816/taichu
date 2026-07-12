$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$envFile = Join-Path $repoRoot ".env"
$windowStyle = if ($env:TAICHU_NON_INTERACTIVE) { "Hidden" } else { "Minimized" }

function Import-TaichuEnvironment {
    if (-not (Test-Path -LiteralPath $envFile -PathType Leaf)) {
        return
    }

    $startupVariables = @(
        "MONGODB_HOME",
        "MONGODB_DATA_DIR",
        "MONGODB_LOG_DIR",
        "MONGODB_URI",
        "MONGODB_DATABASE",
        "PROJECT_ASSETS_DIR"
    )
    foreach ($line in Get-Content -LiteralPath $envFile -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#") -or -not $trimmed.Contains("=")) {
            continue
        }
        $name, $value = $trimmed.Split("=", 2)
        $name = $name.Trim()
        if (
            $name -notin $startupVariables -or
            [Environment]::GetEnvironmentVariable($name, "Process")
        ) {
            continue
        }
        [Environment]::SetEnvironmentVariable($name, $value.Trim(), "Process")
    }
}

function Require-TaichuEnvironment([string]$name) {
    $value = [Environment]::GetEnvironmentVariable($name, "Process")
    if (-not $value) {
        throw "未配置 $name，请检查当前用户环境变量或项目 .env。"
    }
    return $value
}

function Get-ListenerProcessIds([int]$port) {
    $pattern = "^\s*TCP\s+\S+:$port\s+\S+\s+LISTENING\s+(\d+)\s*$"
    return @(
        & netstat.exe -ano -p tcp |
            ForEach-Object {
                if ($_ -match $pattern) {
                    [int]$matches[1]
                }
            } |
            Sort-Object -Unique
    )
}

function Stop-PortListener([int]$port) {
    foreach ($processId in (Get-ListenerProcessIds $port)) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }

    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline) {
        if ((Get-ListenerProcessIds $port).Count -eq 0) {
            return
        }
        Start-Sleep -Milliseconds 200
    }
    throw "固定端口 $port 未能完成清理。"
}

function Wait-ForPort([int]$port, [int]$timeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if ((Get-ListenerProcessIds $port).Count -gt 0) {
            return $true
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
}

function Wait-ForApplicationHealth([int]$timeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $backend = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri "http://127.0.0.1:8000/api/knowledge/types" `
                -TimeoutSec 2
            $frontend = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri "http://localhost:3000/knowledge" `
                -TimeoutSec 2
            if ($backend.StatusCode -eq 200 -and $frontend.StatusCode -eq 200) {
                return $true
            }
        }
        catch {
            # 服务仍在启动，继续轮询直到统一截止时间。
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

try {
    Write-Host "=== 太初一键启动 ==="
    Import-TaichuEnvironment

    $mongoHome = Require-TaichuEnvironment "MONGODB_HOME"
    $mongoDataDir = Require-TaichuEnvironment "MONGODB_DATA_DIR"
    $mongoLogDir = Require-TaichuEnvironment "MONGODB_LOG_DIR"
    $mongoUri = Require-TaichuEnvironment "MONGODB_URI"
    [void](Require-TaichuEnvironment "MONGODB_DATABASE")

    $mongod = Join-Path $mongoHome "bin\mongod.exe"
    if (-not (Test-Path -LiteralPath $mongod -PathType Leaf)) {
        throw "找不到 MongoDB 服务程序：$mongod"
    }
    [void](New-Item -ItemType Directory -Path $mongoDataDir -Force)
    [void](New-Item -ItemType Directory -Path $mongoLogDir -Force)

    Write-Host "[1/3] 检查 MongoDB 服务..."
    $mongoListeners = Get-ListenerProcessIds 27017
    if ($mongoListeners.Count -gt 0) {
        if ($mongoListeners.Count -ne 1) {
            throw "端口 27017 存在多个监听进程，启动已中止。"
        }
        $mongoProcess = Get-Process -Id $mongoListeners[0] -ErrorAction SilentlyContinue
        if (-not $mongoProcess -or $mongoProcess.ProcessName -ne "mongod") {
            throw "端口 27017 已被非 MongoDB 进程占用，进程号：$($mongoListeners[0])。"
        }
        Write-Host "  已复用正在运行的 MongoDB，进程号：$($mongoListeners[0])。"
    }
    else {
        $mongoArguments = "--bind_ip 127.0.0.1 --port 27017 --dbpath `"$mongoDataDir`" --logpath `"$(Join-Path $mongoLogDir 'mongod.log')`" --logappend"
        [void](Start-Process `
            -FilePath $mongod `
            -ArgumentList $mongoArguments `
            -WorkingDirectory $repoRoot `
            -WindowStyle Hidden `
            -PassThru)
        if (-not (Wait-ForPort 27017 15)) {
            throw "MongoDB 启动失败，请检查日志：$(Join-Path $mongoLogDir 'mongod.log')"
        }
        Write-Host "  MongoDB 已启动，数据目录：$mongoDataDir"
    }

    Write-Host "[2/3] 清理后端 8000 和前端 3000 端口..."
    Stop-PortListener 8000
    Stop-PortListener 3000
    Write-Host "  固定端口清理完成。"

    Write-Host "[3/3] 启动后端和前端..."
    [void](Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/k", "uv run taichu") `
        -WorkingDirectory $repoRoot `
        -WindowStyle $windowStyle `
        -PassThru)
    [void](Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/k", "set PORT=3000&& npm run dev") `
        -WorkingDirectory (Join-Path $repoRoot "web") `
        -WindowStyle $windowStyle `
        -PassThru)

    if (-not (Wait-ForApplicationHealth 30)) {
        throw "前后端未能在固定端口 8000/3000 完整启动，请检查对应命令窗口。"
    }

    Write-Host ""
    Write-Host "=== 太初已启动 ==="
    Write-Host "  前端：http://localhost:3000"
    Write-Host "  后端：http://127.0.0.1:8000"
    Write-Host "  MongoDB：$mongoUri"
    Write-Host "  关闭对应命令窗口即可停止前后端服务。"
    exit 0
}
catch {
    Write-Error "太初启动已中止：$($_.Exception.Message)"
    exit 1
}
