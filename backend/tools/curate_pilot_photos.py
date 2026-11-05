"""Operator-selected Commons files; licenses/descriptions reviewed on source pages.
Does not claim that the application Commons search API recovered.
"""
import json,hashlib,io
from pathlib import Path
from urllib.parse import quote
from PIL import Image,ImageDraw
from app.services.assets.wikimedia import fetch
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'generated/imagery-continuation';PHOTOS=OUT/'photos';PHOTOS.mkdir(exist_ok=True)
data=[
 ('Ronaldo','Cristiano Ronaldo of Manchester United, November 5, 2008.jpg','Tsutomu Takasu','2008-11-05','2.0'),
 ('Ronaldo','Cristiano Ronaldo of Manchester United, November 5, 2008, B.jpg','Tsutomu Takasu','2008-11-05','2.0'),
 ('Ronaldo','Cristiano Ronaldo ~ Manchester United.jpg','Paolo Camera','2009-02-21','2.0'),
 ('Ronaldo',"Cristiano Ronaldo - Ballon d'Or (cropped).jpg",'Anish Morarji','2015-01-15','2.0'),
 ('Messi','Messi 2008.jpg','Tiago "Cata" Luiz','2008-07-29','2.0'),
 ('Messi','Messi arms.jpg','m.caimary (Miquel C.)','2011-03-08','2.0'),
 ('Messi','Lionel Messi vs Osasuna.jpg','Jeroen Bennink','2011-09-17','2.0'),
 ('Messi','Argentina vs mexico messi.jpg','Hossein Zohrevand / Tasnim News Agency','2022-11-26','4.0'),
 ('Henry','Thierry Henry applauding 2012.jpg','wonker','2012-01-09','2.0'),
 ('Henry','Thierry Henry (6820443721).jpg','wonker','2012-02-04','2.0'),
 ('Henry','Thierry Henry (51649035951) (cropped).jpg','Diarmuid Greene / Web Summit via Sportsfile','2021-11-02','2.0'),
 ('Henry','Italy vs France - FIFA World Cup 2006 final - Thierry Henry.jpg','David Ruddell; crop by Danyele','2006-07-10','2.0')]
result=[];images=[]
for n,(subject,title,creator,date,version) in enumerate(data):
 filename=title.replace(' ','_');md5=hashlib.md5(filename.encode()).hexdigest()
 url=f'https://upload.wikimedia.org/wikipedia/commons/{md5[0]}/{md5[:2]}/'+quote(filename)
 row={'subject':subject,'title':title,'creator':creator,'capture_date':date,'license':'CC BY '+version,'license_url':'https://creativecommons.org/licenses/by/'+version+'/','source_url':'https://commons.wikimedia.org/wiki/File:'+quote(filename),'download_url':url,'editorial_use':'Illustrative archive photograph of subject, not the historical award event','metadata_basis':'Commons public file description reviewed through web research; automatic Commons API remains blocked'}
 path=PHOTOS/f'{n+1:02}-{subject}.jpg'
 try:
  if not path.exists():
   body,_=fetch(url,hosts={'upload.wikimedia.org'},max_bytes=15*1024*1024,timeout=15)
   image=Image.open(io.BytesIO(body));image.verify();path.write_bytes(body);row['retrieval']='fresh CDN HTTP 200'
  else:row['retrieval']='previously downloaded this continuation'
  image=Image.open(path).convert('RGB');row.update(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),width=image.width,height=image.height)
  assert min(image.size)>=400
  image.thumbnail((300,320));images.append((n,subject,date,image))
 except Exception as e:row['error']=type(e).__name__+': '+str(e)
 result.append(row);print(subject,title,'OK' if 'error' not in row else row['error'],flush=True)
(OUT/'curated-photos.json').write_text(json.dumps(result,indent=2),encoding='utf8')
sheet=Image.new('RGB',(1200,1100),'#ffffff');draw=ImageDraw.Draw(sheet)
for i,(n,subject,date,im) in enumerate(images):
 x=(i%4)*300;y=(i//4)*365;sheet.paste(im,(x,y+40));draw.text((x+4,y+5),f'{n+1}: {subject}, {date}',fill='black')
sheet.save(OUT/'photo-contact-sheet.jpg')
