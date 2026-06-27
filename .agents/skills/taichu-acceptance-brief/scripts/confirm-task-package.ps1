param(
    [string]$TaskPackage = "Unnamed task package",
    [string]$Goal = "",
    [string]$Acceptance = "",
    [string]$CodeRef = "",
    [switch]$NoGui
)

function Write-Result {
    param([string]$Result)

    [ordered]@{
        result = $Result
        taskPackage = $TaskPackage
        goal = $Goal
        acceptance = $Acceptance
        codeRef = $CodeRef
    } | ConvertTo-Json -Compress
}

if ($NoGui) {
    Write-Result -Result "confirm"
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = "Confirm task package understanding"
$form.StartPosition = "CenterScreen"
$form.Size = New-Object System.Drawing.Size(720, 520)
$form.MinimumSize = New-Object System.Drawing.Size(560, 420)
$form.Topmost = $true

$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Text = "Codex thinks this is the task package to summarize:"
$titleLabel.AutoSize = $true
$titleLabel.Location = New-Object System.Drawing.Point(16, 16)
$titleLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($titleLabel)

$body = @"
Task package:
$TaskPackage

Goal:
$Goal

Acceptance:
$Acceptance

Code reference:
$CodeRef
"@

$textBox = New-Object System.Windows.Forms.TextBox
$textBox.Multiline = $true
$textBox.ReadOnly = $true
$textBox.ScrollBars = "Vertical"
$textBox.WordWrap = $true
$textBox.Text = $body
$textBox.Location = New-Object System.Drawing.Point(16, 48)
$textBox.Size = New-Object System.Drawing.Size(670, 350)
$textBox.Anchor = "Top,Left,Right,Bottom"
$textBox.Font = New-Object System.Drawing.Font("Microsoft YaHei UI", 9)
$form.Controls.Add($textBox)

$confirmButton = New-Object System.Windows.Forms.Button
$confirmButton.Text = "Confirm"
$confirmButton.Size = New-Object System.Drawing.Size(140, 36)
$confirmButton.Location = New-Object System.Drawing.Point(396, 420)
$confirmButton.Anchor = "Right,Bottom"
$confirmButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.Controls.Add($confirmButton)

$reviseButton = New-Object System.Windows.Forms.Button
$reviseButton.Text = "Needs revision"
$reviseButton.Size = New-Object System.Drawing.Size(140, 36)
$reviseButton.Location = New-Object System.Drawing.Point(546, 420)
$reviseButton.Anchor = "Right,Bottom"
$reviseButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.Add($reviseButton)

$form.AcceptButton = $confirmButton
$form.CancelButton = $reviseButton

$form.Add_Shown({ $form.Activate() })
$dialogResult = $form.ShowDialog()

if ($dialogResult -eq [System.Windows.Forms.DialogResult]::OK) {
    Write-Result -Result "confirm"
} else {
    Write-Result -Result "needs_revision"
}
