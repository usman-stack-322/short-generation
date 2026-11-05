import json


from app.core.security import hash_password, new_id
from app.database.session import Base, SessionLocal, engine
from app.models import Channel, Personality, User, VideoJob, Workspace, WorkspaceMember

def seed_demo_data():
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
        if db.query(User).filter_by(email="owner@example.com").first():
            return
        workspace = Workspace(id=new_id(), name="Demo Workspace")
        owner = User(id=new_id(), name="Demo Owner", email="owner@example.com", password_hash=hash_password("DemoOwner123!"))
        editor = User(id=new_id(), name="Demo Editor", email="editor@example.com", password_hash=hash_password("DemoEditor123!"))
        db.add_all([workspace, owner, editor])
        db.flush()
        owner_membership = WorkspaceMember(id=new_id(), workspace_id=workspace.id, user_id=owner.id, role="OWNER")
        editor_membership = WorkspaceMember(id=new_id(), workspace_id=workspace.id, user_id=editor.id, role="MEMBER")
        db.add_all([owner_membership, editor_membership])
        db.flush()
        channel = Channel(
            id=new_id(), workspace_id=workspace.id, member_id=editor_membership.id,
            name="Demo Sports Channel", youtube_channel_id="demo-channel-001", status="demo",
            default_language="en", default_voice="en-US", approval_required=True,
        )
        db.add(channel)
        db.flush()
        personality = Personality(
            id=new_id(), workspace_id=workspace.id, channel_id=channel.id,
            name="Cristiano Ronaldo", category="Football",
            description="Energetic, context-first football stories. Demo research is not live news.",
            keywords=json.dumps(["Cristiano Ronaldo", "Ronaldo", "CR7"]),
            research_keywords=json.dumps(["Cristiano Ronaldo", "football"]),
            tone="Energetic documentary/news style", default_duration=45, default_voice="en-US",
        )
        db.add(personality)
        db.flush()
        db.add(VideoJob(
            id=new_id(), workspace_id=workspace.id, channel_id=channel.id,
            personality_id=personality.id, topic_title="Demo job — create a Short to render real media",
            duration=45, voice="en-US", status="failed", current_step="failed",
            error_message="Seeded sample job. Use Create Short to run the complete local video pipeline.",
        ))
        db.commit()
    finally:
        db.close()


