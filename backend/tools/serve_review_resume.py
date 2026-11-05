import os
os.environ['YOUTUBE_UPLOADS_ENABLED']='false'
os.environ['SCHEDULER_ENABLED']='false'
import uvicorn
uvicorn.run('app.main:app',host='127.0.0.1',port=8000,workers=1)
