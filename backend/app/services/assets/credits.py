"""Retain full credits in preview/export metadata; never truncate license obligations."""
import json
from app.models import Asset

MARKER='\n\nImage credits:\n'


def credits_for(db,job):
    return list(dict.fromkeys(json.loads(a.provenance or '{}').get('required_credit',a.attribution)
        for a in db.query(Asset).filter_by(job_id=job.id).order_by(Asset.scene_number)
        if a.source!='Local text card'))


def sync_credits(db,job):
    if not job.script or not job.script.seo:return
    seo=job.script.seo
    base=seo.description.split(MARKER)[0]
    credits=credits_for(db,job)
    description=base+(MARKER+'\n'.join(credits) if credits else '')
    if len(description.encode('utf-8'))>4400:
        raise ValueError('Image credits exceed description budget. Use fewer photos or shorten the description; credits were not truncated.')
    seo.description=description
