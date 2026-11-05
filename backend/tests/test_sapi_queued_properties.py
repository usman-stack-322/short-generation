import io,json,types,wave
from pathlib import Path
from app.tts import local_worker

def test_timed_sapi_applies_queued_voice_rate_and_volume_before_payload(monkeypatch,tmp_path):
 voices=[types.SimpleNamespace(id='david-id',name='Microsoft David Desktop',languages=['en-US']),types.SimpleNamespace(id='zira-id',name='Microsoft Zira Desktop',languages=['en-US'])]
 state={'voice':'david-id','rate':200,'volume':1};events=[]
 native=types.SimpleNamespace(Rate=0,Volume=100)
 class Engine:
  def __init__(self):self.pending=[];self.proxy=types.SimpleNamespace(_driver=types.SimpleNamespace(_tts=native))
  def getProperty(self,key):return voices if key=='voices' else state[key]
  def setProperty(self,key,value):self.pending.append((key,value))
  def runAndWait(self):
   events.append('flush')
   for key,value in self.pending:
    state[key]=value
    if key=='rate':native.Rate=-2
    if key=='volume':native.Volume=round(value*100)
   self.pending=[]
  def stop(self):events.append('stop');self.pending=[]
 engine=Engine();monkeypatch.setattr(local_worker.pyttsx3,'init',lambda:engine)
 audio=tmp_path/'voice.wav';monkeypatch.setattr(local_worker.sys,'argv',['local_worker',str(audio),'zira-id','0.96','0.8']);monkeypatch.setattr(local_worker.sys,'stdin',io.StringIO('Hello world.'))
 captured=[]
 def render(args,**kwargs):
  payload=json.loads(kwargs['input']);captured.append(payload)
  assert events[0]=='flush' and payload['voice_name']=='Microsoft Zira Desktop'
  assert payload['rate']==-2 and payload['volume']==80
  with wave.open(payload['path'],'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\x01\x00'*16000)
  Path(payload['timing_path']).write_text(json.dumps({'words':[{'character':0,'length':5,'start':0,'text':'Hello'},{'character':6,'length':5,'start':.5,'text':'world'}]}))
 monkeypatch.setattr(local_worker.subprocess,'run',render)
 local_worker.main()
 assert captured and state['rate']==149
 timing=json.loads(audio.with_suffix('.words.json').read_text())
 assert timing['words'][0]['char']==0 and timing['script_sha256'] and timing['audio_sha256']
