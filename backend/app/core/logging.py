"""Avoid writing one-time OAuth codes or signed media capabilities to access logs."""
import logging


class RedactAccessQuery(logging.Filter):
    def filter(self,record):
        if isinstance(record.args,tuple) and len(record.args)>=3:
            values=list(record.args)
            if isinstance(values[2],str) and ('/api/youtube/callback' in values[2] or '/generated/' in values[2]):
                values[2]=values[2].split('?',1)[0]+'?[redacted]'
                record.args=tuple(values)
        return True


logging.getLogger('uvicorn.access').addFilter(RedactAccessQuery())
