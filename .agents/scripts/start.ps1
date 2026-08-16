$ErrorActionPreference = "Stop"

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
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
        "PROJECT_ASSETS_DIR",
        "MILVUS_URI",
        "RERANKER_BASE_URL",
        "RERANKER_MODEL_PATH",
        "EMBEDDING_SERVER_HOME",
        "EMBEDDING_MODEL_PATH",
        "EMBEDDING_LOG_DIR",
        "EMBEDDING_SERVER_PORT",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_MODEL_ID",
        "EMBEDDING_CONTEXT_SIZE",
        "EMBEDDING_BATCH_SIZE",
        "EMBEDDING_GPU_LAYERS"
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

function Get-DescendantProcessIds(
    [int]$parentProcessId,
    [object[]]$processSnapshot
) {
    foreach ($process in $processSnapshot) {
        if ([int]$process.ParentProcessId -ne $parentProcessId) {
            continue
        }
        Get-DescendantProcessIds `
            -parentProcessId ([int]$process.ProcessId) `
            -processSnapshot $processSnapshot
        [int]$process.ProcessId
    }
}

function Stop-ProcessTree([int]$rootProcessId) {
    $processSnapshot = @(Get-CimInstance Win32_Process)
    $processIds = @(
        Get-DescendantProcessIds `
            -parentProcessId $rootProcessId `
            -processSnapshot $processSnapshot
        $rootProcessId
    ) | Select-Object -Unique

    foreach ($processId in $processIds) {
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    }
}

function Stop-PortListener([int]$port) {
    foreach ($processId in (Get-ListenerProcessIds $port)) {
        Stop-ProcessTree $processId
    }

    $deadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $deadline) {
        $listenerProcessIds = @(Get-ListenerProcessIds $port)
        if ($listenerProcessIds.Count -eq 0) {
            return
        }
        foreach ($processId in $listenerProcessIds) {
            Stop-ProcessTree $processId
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

function Test-HttpHealth([string]$uri) {
    try {
        $response = Invoke-WebRequest `
            -UseBasicParsing `
            -Uri $uri `
            -TimeoutSec 3
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Wait-ForHttpHealth([string]$uri, [int]$timeoutSeconds) {
    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpHealth $uri) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Test-DockerReady {
    try {
        $serverVersion = & docker.exe info --format "{{.ServerVersion}}" 2>$null
        return $LASTEXITCODE -eq 0 -and -not [string]::IsNullOrWhiteSpace($serverVersion)
    }
    catch {
        return $false
    }
}

function Ensure-DockerReady([int]$timeoutSeconds) {
    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue)) {
        throw "找不到 Docker 命令，请先安装 Docker Desktop。"
    }
    if (Test-DockerReady) {
        return
    }

    $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop -PathType Leaf)) {
        throw "Docker 服务未运行，且找不到 Docker Desktop：$dockerDesktop"
    }

    Write-Host "  Docker Engine 未就绪，正在启动 Docker Desktop..."
    if (-not (Get-Process -Name "Docker Desktop" -ErrorAction SilentlyContinue)) {
        [void](Start-Process -FilePath $dockerDesktop -WindowStyle Hidden -PassThru)
    }
    else {
        [void](Start-Process -FilePath $dockerDesktop -WindowStyle Hidden -ErrorAction SilentlyContinue)
    }

    $deadline = (Get-Date).AddSeconds($timeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerReady) {
            Write-Host "  Docker Desktop 已就绪。"
            return
        }
        Start-Sleep -Seconds 2
    }
    throw "Docker Desktop 未能在 $timeoutSeconds 秒内就绪。"
}

function Ensure-MilvusService([string]$baseUrl) {
    $milvusUri = [Uri]$baseUrl
    if (
        $milvusUri.Scheme -ne "http" -or
        $milvusUri.Host -notin @("127.0.0.1", "localhost") -or
        $milvusUri.Port -ne 19530
    ) {
        throw "MILVUS_URI 必须指向本机 19530 端口，当前值：$baseUrl"
    }
    $healthUrl = "http://127.0.0.1:9091/healthz"
    if (Test-HttpHealth $healthUrl) {
        Write-Host "  已复用正在运行的 Milvus：$baseUrl"
        return
    }
    if ((Get-ListenerProcessIds 19530).Count -gt 0) {
        throw "端口 19530 已被占用，但 Milvus 健康检查失败。"
    }
    if ((Get-ListenerProcessIds 9091).Count -gt 0) {
        throw "Milvus 健康检查端口 9091 已被其他进程占用。"
    }

    Ensure-DockerReady 120
    $composeFile = Join-Path $repoRoot "infra\milvus\docker-compose.yml"
    & docker.exe compose -f $composeFile up -d
    if ($LASTEXITCODE -ne 0) {
        throw "Milvus Docker Compose 启动失败。"
    }

    if (-not (Wait-ForHttpHealth $healthUrl 180)) {
        throw "Milvus 启动失败，请运行 docker logs taichu-milvus 查看日志。"
    }
    Write-Host "  Milvus 已启动：$baseUrl"
}

function Ensure-RerankerService([string]$rerankerUrl) {
    $rerankerUri = [Uri]$rerankerUrl
    if (
        $rerankerUri.Host -notin @("127.0.0.1", "localhost") -or
        $rerankerUri.Port -ne 8012
    ) {
        throw "RERANKER_BASE_URL 必须指向本机 8012 端口。"
    }
    $rerankerHealth = "$($rerankerUrl.TrimEnd('/'))/health"
    if (Test-HttpHealth $rerankerHealth) {
        Write-Host "  已复用 BGE 重排服务。"
        return
    }
    if ((Get-ListenerProcessIds 8012).Count -gt 0) {
        $containerRunning = (
            & docker.exe inspect `
                --format "{{.State.Running}}" `
                taichu-bge-reranker `
                2>$null
        ) -eq "true"
        if (-not $containerRunning) {
            throw "端口 8012 已被占用，但不是正在启动的 BGE 容器。"
        }
        Write-Host "  BGE 容器正在预热，等待健康检查..."
        if (-not (Wait-ForHttpHealth $rerankerHealth 600)) {
            throw "BGE 重排服务预热失败，请运行 docker logs taichu-bge-reranker。"
        }
        Write-Host "  BGE 重排服务已就绪。"
        return
    }
    Ensure-DockerReady 120
    $composeFile = Join-Path $repoRoot "infra\reranker\docker-compose.yml"
    & docker.exe compose -f $composeFile up -d
    if ($LASTEXITCODE -ne 0) {
        throw "BGE Docker Compose 启动失败。"
    }
    if (-not (Wait-ForHttpHealth $rerankerHealth 600)) {
        throw "BGE 重排服务启动失败，请运行 docker logs taichu-bge-reranker。"
    }
    Write-Host "  BGE 重排服务已启动。"
}

function Ensure-EmbeddingService(
    [string]$serverHome,
    [string]$modelPath,
    [string]$logDir,
    [int]$port,
    [string]$modelId,
    [int]$contextSize,
    [int]$batchSize,
    [int]$gpuLayers
) {
    $healthUrl = "http://127.0.0.1:$port/health"
    $modelsUrl = "http://127.0.0.1:$port/v1/models"
    if (Test-HttpHealth $healthUrl) {
        $models = Invoke-RestMethod -Uri $modelsUrl -TimeoutSec 5
        $modelIds = @($models.data | ForEach-Object { $_.id })
        if ($modelId -notin $modelIds) {
            throw "端口 $port 的嵌入服务未加载配置模型：$modelId"
        }
        Write-Host "  已复用本地嵌入服务：$modelId"
        return
    }
    if ((Get-ListenerProcessIds $port).Count -gt 0) {
        throw "端口 $port 已被占用，但嵌入服务健康检查失败。"
    }

    $server = Join-Path $serverHome "llama-server.exe"
    if (-not (Test-Path -LiteralPath $server -PathType Leaf)) {
        throw "找不到本地嵌入服务程序：$server"
    }
    if (-not (Test-Path -LiteralPath $modelPath -PathType Leaf)) {
        throw "找不到本地嵌入模型：$modelPath"
    }
    [void](New-Item -ItemType Directory -Path $logDir -Force)

    $arguments = @(
        "--model `"$modelPath`"",
        "--alias `"$modelId`"",
        "--host 127.0.0.1",
        "--port $port",
        "--embedding",
        "--pooling last",
        "--ctx-size $contextSize",
        "--batch-size $batchSize",
        "--ubatch-size $batchSize",
        "--n-gpu-layers $gpuLayers",
        "--parallel 1",
        "--metrics",
        "--cors-origins localhost",
        "--no-cors-credentials",
        "--no-webui"
    ) -join " "
    [void](Start-Process `
        -FilePath $server `
        -ArgumentList $arguments `
        -WorkingDirectory $serverHome `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "llama-server.stdout.log") `
        -RedirectStandardError (Join-Path $logDir "llama-server.stderr.log") `
        -PassThru)

    if (-not (Wait-ForHttpHealth $healthUrl 180)) {
        throw "嵌入服务启动失败，请检查日志：$logDir"
    }
    $models = Invoke-RestMethod -Uri $modelsUrl -TimeoutSec 5
    $modelIds = @($models.data | ForEach-Object { $_.id })
    if ($modelId -notin $modelIds) {
        throw "嵌入服务已响应，但未加载配置模型：$modelId"
    }
    Write-Host "  本地嵌入服务已启动：$modelId"
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
    $milvusUri = Require-TaichuEnvironment "MILVUS_URI"
    $rerankerUrl = Require-TaichuEnvironment "RERANKER_BASE_URL"
    $rerankerModelPath = Require-TaichuEnvironment "RERANKER_MODEL_PATH"
    $embeddingServerHome = Require-TaichuEnvironment "EMBEDDING_SERVER_HOME"
    $embeddingModelPath = Require-TaichuEnvironment "EMBEDDING_MODEL_PATH"
    $embeddingLogDir = Require-TaichuEnvironment "EMBEDDING_LOG_DIR"
    $embeddingPort = [int](Require-TaichuEnvironment "EMBEDDING_SERVER_PORT")
    $embeddingBaseUrl = Require-TaichuEnvironment "EMBEDDING_BASE_URL"
    $embeddingModelId = Require-TaichuEnvironment "EMBEDDING_MODEL_ID"
    $embeddingContextSize = [int](
        Require-TaichuEnvironment "EMBEDDING_CONTEXT_SIZE"
    )
    $embeddingBatchSize = [int](
        Require-TaichuEnvironment "EMBEDDING_BATCH_SIZE"
    )
    $embeddingGpuLayers = [int](
        Require-TaichuEnvironment "EMBEDDING_GPU_LAYERS"
    )
    $embeddingUri = [Uri]$embeddingBaseUrl
    if (
        $embeddingUri.Scheme -ne "http" -or
        $embeddingUri.Host -notin @("127.0.0.1", "localhost") -or
        $embeddingUri.Port -ne $embeddingPort
    ) {
        throw "EMBEDDING_BASE_URL 与 EMBEDDING_SERVER_PORT 必须指向同一本机服务。"
    }
    if (-not (Test-Path -LiteralPath $rerankerModelPath -PathType Container)) {
        throw "找不到本地 BGE 重排模型目录：$rerankerModelPath"
    }

    $mongod = Join-Path $mongoHome "bin\mongod.exe"
    if (-not (Test-Path -LiteralPath $mongod -PathType Leaf)) {
        throw "找不到 MongoDB 服务程序：$mongod"
    }
    [void](New-Item -ItemType Directory -Path $mongoDataDir -Force)
    [void](New-Item -ItemType Directory -Path $mongoLogDir -Force)

    Write-Host "[1/6] 检查 MongoDB 服务..."
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

    Write-Host "[2/6] 检查 Milvus 向量数据库..."
    Ensure-MilvusService $milvusUri

    Write-Host "[3/6] 检查 BGE 重排服务..."
    Ensure-RerankerService $rerankerUrl

    Write-Host "[4/6] 检查本地嵌入模型服务..."
    Ensure-EmbeddingService `
        $embeddingServerHome `
        $embeddingModelPath `
        $embeddingLogDir `
        $embeddingPort `
        $embeddingModelId `
        $embeddingContextSize `
        $embeddingBatchSize `
        $embeddingGpuLayers

    Write-Host "[5/6] 清理后端 8000 和前端 3000 端口..."
    Stop-PortListener 8000
    Stop-PortListener 3000
    Write-Host "  固定端口清理完成。"

    Write-Host "[6/6] 启动后端和前端..."
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
    Write-Host "  Milvus：$milvusUri"
    Write-Host "  BGE 重排：$rerankerUrl"
    Write-Host "  本地嵌入：$embeddingBaseUrl（$embeddingModelId）"
    Write-Host "  关闭对应命令窗口即可停止前后端服务。"
    exit 0
}
catch {
    Write-Error "太初启动已中止：$($_.Exception.Message)"
    exit 1
}
