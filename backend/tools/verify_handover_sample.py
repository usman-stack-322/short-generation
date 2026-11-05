"""Inspect an existing approval-backed MP4 without regenerating or uploading it."""
import json,sqlite3,subprocess,hashlib
from pathlib import Path
from PIL import Image,ImageDraw
from app.core.config import settings


def main():
    root=Path(__file__).resolve().parents[2];out=root/'release'/'evidence';out.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(root/'backend'/'ai_shorts.db');db.row_factory=sqlite3.Row
    row=db.execute('SELECT v.*,j.status,j.content_revision FROM videos v JOIN video_jobs j ON j.id=v.job_id JOIN approvals a ON a.job_id=j.id ORDER BY a.created_at DESC LIMIT 1').fetchone()
    if not row:raise SystemExit('No approval-backed sample exists')
    video=Path(row['output_path'])
    probe=json.loads(subprocess.check_output([settings.ffprobe_path,'-v','error','-show_streams','-show_format','-of','json',str(video)]))
    decoded=subprocess.run([settings.ffmpeg_path,'-v','error','-i',str(video),'-f','null','-'],capture_output=True,text=True)
    volume=subprocess.run([settings.ffmpeg_path,'-i',str(video),'-af','volumedetect','-vn','-sn','-f','null','-'],capture_output=True,text=True)
    scenes=[dict(s) for s in db.execute('SELECT scene_number,start_time,end_time,narration,caption FROM scenes WHERE job_id=? ORDER BY scene_number',(row['job_id'],))]
    thumbnails=[]
    for i,scene in enumerate(scenes):
        path=out/f'sample-scene-{i+1}.jpg';at=(scene['start_time']+scene['end_time'])/2
        subprocess.run([settings.ffmpeg_path,'-y','-v','error','-ss',str(at),'-i',str(video),'-frames:v','1','-vf','scale=270:480',str(path)],check=True,capture_output=True)
        thumbnails.append(Image.open(path).copy())
    sheet=Image.new('RGB',(270*len(thumbnails),510),'white');draw=ImageDraw.Draw(sheet)
    for i,frame in enumerate(thumbnails):sheet.paste(frame,(i*270,0));draw.text((i*270+8,486),'Scene '+str(i+1),fill='black')
    sheet.save(out/'sample-scenes.jpg')
    report={'job_id':row['job_id'],'video':str(video),'sha256':hashlib.sha256(video.read_bytes()).hexdigest(),
        'status':row['status'],'approval_backed':True,'duration':probe['format']['duration'],
        'streams':[{k:s.get(k) for k in ['codec_type','codec_name','width','height','sample_rate','channels']} for s in probe['streams']],
        'full_decode_passed':decoded.returncode==0,'decode_errors':decoded.stderr,'scenes':scenes,
        'audio_measurements':[line.strip() for line in volume.stderr.splitlines() if 'mean_volume' in line or 'max_volume' in line],
        'listening_review':'Not performed by this verification script. Technical audio presence/levels are not a listening review.',
        'contact_sheet':str(out/'sample-scenes.jpg')}
    (out/'sample-verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='scenes'},indent=2))


if __name__=='__main__':main()
