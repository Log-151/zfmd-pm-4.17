param(
    [string]$BackupRoot = "",
    [switch]$KeepStopped
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($BackupRoot)) {
    $BackupRoot = Join-Path $ProjectRoot "backups"
}

$Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$BackupDir = Join-Path $BackupRoot $Timestamp
$ComposeFile = Join-Path $ProjectRoot "docker-compose.yml"

$ItemsToCopy = @(
    @{ Name = "addons"; Path = Join-Path $ProjectRoot "addons"; Type = "Directory" },
    @{ Name = "docs"; Path = Join-Path $ProjectRoot "docs"; Type = "Directory" },
    @{ Name = "postgres_data"; Path = Join-Path $ProjectRoot "postgres_data"; Type = "Directory" },
    @{ Name = "odoo_data"; Path = Join-Path $ProjectRoot "odoo\data"; Type = "Directory" },
    @{ Name = "docker-compose.yml"; Path = Join-Path $ProjectRoot "docker-compose.yml"; Type = "File" },
    @{ Name = "odoo.conf"; Path = Join-Path $ProjectRoot "odoo\odoo.conf"; Type = "File" }
)

function Copy-ProjectItem {
    param(
        [string]$SourcePath,
        [string]$TargetPath,
        [string]$ItemType
    )

    if ($ItemType -eq "Directory") {
        New-Item -ItemType Directory -Force -Path $TargetPath | Out-Null
        robocopy $SourcePath $TargetPath /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "复制目录失败：$SourcePath"
        }
    }
    else {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $TargetPath) | Out-Null
        Copy-Item -LiteralPath $SourcePath -Destination $TargetPath -Force
    }
}

function Write-BackupSummary {
    param(
        [string]$TargetDir,
        [array]$CopiedItems
    )

    $SummaryPath = Join-Path $TargetDir "BACKUP_README.txt"
    $Lines = @(
        "ZFMD 本地完整备份",
        "生成时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
        "项目目录：$ProjectRoot",
        "备份目录：$TargetDir",
        "",
        "包含内容："
    )
    foreach ($item in $CopiedItems) {
        $Lines += "- $($item.Name)"
    }
    $Lines += ""
    $Lines += "恢复顺序建议："
    $Lines += "1. 停止本地 Odoo 容器。"
    $Lines += "2. 恢复 postgres_data。"
    $Lines += "3. 恢复 odoo_data。"
    $Lines += "4. 恢复 addons、docs、配置文件。"
    $Lines += "5. 重新启动 docker compose。"
    Set-Content -LiteralPath $SummaryPath -Value $Lines -Encoding UTF8
}

if (-not (Test-Path $ComposeFile)) {
    throw "未找到 docker-compose.yml：$ComposeFile"
}

New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

$ComposeWasStopped = $false
Push-Location $ProjectRoot
try {
    Write-Host "正在停止本地 Odoo 容器..."
    docker compose down
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose down 执行失败。"
    }
    $ComposeWasStopped = $true

    foreach ($item in $ItemsToCopy) {
        if (-not (Test-Path $item.Path)) {
            throw "备份项不存在：$($item.Path)"
        }
        $TargetPath = Join-Path $BackupDir $item.Name
        Write-Host "正在备份 $($item.Name)..."
        Copy-ProjectItem -SourcePath $item.Path -TargetPath $TargetPath -ItemType $item.Type
    }

    Write-BackupSummary -TargetDir $BackupDir -CopiedItems $ItemsToCopy
    Write-Host "备份完成：$BackupDir"
}
finally {
    if ($ComposeWasStopped -and -not $KeepStopped) {
        Write-Host "正在重新启动本地 Odoo 容器..."
        docker compose up -d
    }
    Pop-Location
}
