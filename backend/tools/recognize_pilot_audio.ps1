param([string]$InputPath,[string]$OutputPath)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$inputData=Get-Content -LiteralPath $InputPath -Raw -Encoding UTF8 | ConvertFrom-Json
$engine=[System.Speech.Recognition.SpeechRecognitionEngine]::new([System.Globalization.CultureInfo]::GetCultureInfo('en-US'))
try {
    $builder=New-Object System.Speech.Recognition.GrammarBuilder
    $builder.Culture=[System.Globalization.CultureInfo]::GetCultureInfo('en-US')
    $builder.Append([string]$inputData.text)
    $grammar=New-Object System.Speech.Recognition.Grammar($builder)
    $engine.LoadGrammar($grammar)
    $engine.SetInputToWaveFile([string]$inputData.audio_path)
    $result=$engine.Recognize([TimeSpan]::FromSeconds(60))
    if ($null -eq $result) { throw 'No complete acoustic match for the supplied script.' }
    $words=@($result.Words | ForEach-Object { @{text=$_.Text; start=$_.AudioPosition.TotalSeconds; duration=$_.AudioDuration.TotalSeconds; confidence=$_.Confidence} })
    @{provider='Windows System.Speech constrained acoustic recognition'; text=$result.Text; confidence=$result.Confidence; audio_start=$result.Audio.AudioPosition.TotalSeconds; audio_duration=$result.Audio.Duration.TotalSeconds; words=$words} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
} finally { $engine.Dispose() }
