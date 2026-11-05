$ErrorActionPreference='Stop'
[Console]::InputEncoding=[System.Text.Encoding]::UTF8
$payload=[Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
Add-Type -ReferencedAssemblies System.Speech -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Speech.Synthesis;
using System.Speech.AudioFormat;
public class TimedWord { public int character; public int length; public double start; public string text; }
public class TimedNarration {
 public static List<TimedWord> Render(string text,string voiceName,int rate,int volume,string path) {
  var words=new List<TimedWord>();
  using(var synth=new SpeechSynthesizer()) {
   bool selected=false;
   foreach(var installed in synth.GetInstalledVoices()) {
    var name=installed.VoiceInfo.Name;
    if(voiceName.StartsWith(name,StringComparison.OrdinalIgnoreCase)) { synth.SelectVoice(name);selected=true;break; }
   }
   if(!selected) throw new Exception("Selected local voice is unavailable to timed SAPI synthesis");
   synth.Rate=rate;synth.Volume=volume;
   synth.SpeakProgress+=(sender,e)=>words.Add(new TimedWord {character=e.CharacterPosition,length=e.CharacterCount,start=e.AudioPosition.TotalSeconds,text=e.Text});
   synth.SetOutputToWaveFile(path,new SpeechAudioFormatInfo(16000,AudioBitsPerSample.Sixteen,AudioChannel.Mono));synth.Speak(text);
  }
  return words;
 }
}
'@
$words=[TimedNarration]::Render([string]$payload.text,[string]$payload.voice_name,[int]$payload.rate,[int]$payload.volume,[string]$payload.path)
@{words=@($words)} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath ([string]$payload.timing_path) -Encoding UTF8
