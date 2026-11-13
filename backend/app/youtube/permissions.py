from fastapi import HTTPException
from app.models import Approval, Channel, VideoJob, WorkspaceMember
from app.core.security import new_id


def channel_access(channel, member, write=False):
    if not channel or channel.workspace_id != member.workspace_id:
        raise HTTPException(404, 'Channel not found')
    if channel.member_id != member.id:
        raise HTTPException(404, 'Channel not found')
    if write and member.role == 'VIEWER':
        raise HTTPException(403, 'Read-only membership')


def job_access(db, job_id, member, write=False):
    job = db.get(VideoJob, job_id)
    if not job:
        raise HTTPException(404, 'Video job not found')
    channel_access(db.get(Channel, job.channel_id), member, write)
    return job


def can_approve(channel, member):
    if member.role == 'VIEWER':
        return False
    owner = member.role in {'OWNER', 'ADMIN'}
    authorized_member = channel.member_id == member.id
    return {'owner_only': owner, 'member_only': authorized_member,
            'either': owner or authorized_member, 'both': owner or authorized_member}.get(channel.approval_policy, False)


def approval_satisfied(db, job, channel):
    approvals = db.query(Approval).filter_by(job_id=job.id, revision=job.content_revision).all()
    members = [db.get(WorkspaceMember, a.member_id) for a in approvals]
    members = [m for m in members if m and m.active and m.workspace_id == job.workspace_id and m.role != 'VIEWER']
    owner = any(m.role in {'OWNER', 'ADMIN'} for m in members)
    member = any(m.id == channel.member_id for m in members)
    # "both" always requires two distinct people, including an owner and the authorizing member.
    both = member and any(m.role in {'OWNER', 'ADMIN'} and m.id != channel.member_id for m in members)
    return {'owner_only': owner, 'member_only': member, 'either': owner or member, 'both': both}.get(channel.approval_policy, False)


def approve(db, job, member, expected_revision=None):
    channel = db.get(Channel, job.channel_id)
    channel_access(channel, member, True)
    if not can_approve(channel, member):
        raise HTTPException(403, 'This channel approval policy requires a different approver')
    if type(expected_revision) is not int or expected_revision!=job.content_revision:
        raise HTTPException(409,'Review version changed or missing. Refresh the review before approving.')
    if job.status not in {'ready_for_review', 'approved'}:
        raise HTTPException(409, 'Only a rendered video ready for review can be approved')
    if not job.video:
        raise HTTPException(409,'Render the complete video before approval')
    if job.video.media_revision!=job.media_revision or job.video.status=='outdated':
        raise HTTPException(409,'Rendered video is outdated. Regenerate narration/video before approval.')
    if not db.query(Approval).filter_by(job_id=job.id, member_id=member.id, revision=job.content_revision).first():
        db.add(Approval(id=new_id(), job_id=job.id, member_id=member.id, revision=job.content_revision))
        db.flush()
    if approval_satisfied(db, job, channel):
        job.status = job.current_step = 'approved'
        if job.video:
            job.video.status = 'approved'
    # Even a first approval under "both" must participate in the job CAS.
    job.row_version+=1
    db.commit()
