"""Durable protection and concurrency regression tests for daily video preparation.

Verifies:
1. Coordinated simultaneous triggers for the same channel & slot resolve to one job.
2. Independent channels progress concurrently without cross-channel interference.
3. Errors in one channel do not block other independent channels.
4. Channel timezone is respected when determining the local scheduled date.
5. Interrupted or failed jobs are never silently duplicated or permanently stranded.
"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import Mock
import pytest

from app.database.session import SessionLocal
from app.models import Channel, Personality, VideoJob, GenerationRequest, WorkspaceMember, User
from app.core.security import new_id
from app.services.preparation import prepare_due
from app.services.recovery import recover_interrupted_jobs


def test_duplicate_worker_delivery_does_not_overlap_or_repeat(publishable, monkeypatch):
    from app.services.pipeline import run_job
    import time
    calls=[]
    def execute(db, job, *args):
        calls.append(job.id)
        time.sleep(.05)
        job.status=job.current_step='ready_for_review'
        db.commit()
    monkeypatch.setattr('app.services.pipeline.run_pipeline',execute)
    with SessionLocal() as db:
        job=db.get(VideoJob,publishable['job_id']);job.status=job.current_step='researching';db.commit()
    barrier=threading.Barrier(4)
    def deliver():
        barrier.wait();run_job(publishable['job_id'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in [pool.submit(deliver) for _ in range(4)]:future.result()
    assert calls==[publishable['job_id']]


def test_coordinated_concurrent_requests_resolve_to_one_job(publishable, monkeypatch):
    p = publishable
    worker = Mock()
    monkeypatch.setattr('app.api.videos.run_job', worker)

    with SessionLocal() as db:
        channel = db.get(Channel, p['channel_id'])
        channel.automatic_generation_enabled = True
        channel.daily_video_target = 1
        workspace_id = channel.workspace_id
        db.commit()
        before_count = db.query(VideoJob).filter_by(channel_id=p['channel_id']).count()

    instant = datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc)
    num_threads = 4
    barrier = threading.Barrier(num_threads)

    def worker_task():
        barrier.wait()
        prepare_due(instant)

    try:
        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(worker_task) for _ in range(num_threads)]
            for f in futures:
                f.result()

        with SessionLocal() as db:
            jobs = db.query(VideoJob).filter_by(channel_id=p['channel_id']).all()
            assert len(jobs) == before_count + 1, f"Expected exactly 1 new job, got {len(jobs) - before_count}"
            new_job = jobs[-1]
            trace = json.loads(new_job.research_trace or '{}')
            assert trace.get('generation_origin') == 'daily_preparation'

            # Ensure exactly one GenerationRequest exists
            reqs = db.query(GenerationRequest).filter_by(workspace_id=workspace_id).all()
            auto_reqs = [r for r in reqs if r.job_id == new_job.id]
            assert len(auto_reqs) == 1

        assert worker.call_count == 1, f"Worker called {worker.call_count} times; expected exactly 1"
    finally:
        with SessionLocal() as db:
            ch = db.get(Channel, p['channel_id'])
            if ch:
                ch.automatic_generation_enabled = False
                db.commit()


def test_independent_channels_progress_correctly(publishable, monkeypatch):
    p = publishable
    worker = Mock()
    monkeypatch.setattr('app.api.videos.run_job', worker)

    with SessionLocal() as db:
        ch1 = db.get(Channel, p['channel_id'])
        ch1.automatic_generation_enabled = True
        ch1.daily_video_target = 2
        member = db.query(WorkspaceMember).join(User).filter(User.email == 'editor@example.com').one()

        # Create a second independent channel with its own theme
        ch2 = Channel(
            id=new_id(), workspace_id=member.workspace_id, member_id=member.id,
            name='Second Channel', status='connected', approval_policy='owner_only',
            automatic_generation_enabled=True, daily_video_target=1,
            default_language='en-US', default_voice='en-US'
        )
        db.add(ch2); db.flush()
        theme2 = Personality(
            id=new_id(), workspace_id=member.workspace_id, channel_id=ch2.id,
            name='Second Theme', category='Technology', enabled=True
        )
        db.add(theme2)
        db.commit()
        ch2_id = ch2.id

    instant = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
    num_threads = 4
    barrier = threading.Barrier(num_threads)

    def worker_task():
        barrier.wait()
        prepare_due(instant)

    try:
        with ThreadPoolExecutor(max_workers=num_threads) as pool:
            futures = [pool.submit(worker_task) for _ in range(num_threads)]
            for f in futures:
                f.result()

        with SessionLocal() as db:
            ch1_jobs = db.query(VideoJob).filter_by(channel_id=p['channel_id']).all()
            ch2_jobs = db.query(VideoJob).filter_by(channel_id=ch2_id).all()

            # Channel 1 had target 2 (plus the 1 from publishable fixture = 3 total)
            # Channel 2 had target 1 = 1 total
            assert len(ch1_jobs) == 3, f"Expected fixture plus two daily jobs for Channel 1, got {len(ch1_jobs)}"
            assert len(ch2_jobs) == 1, f"Expected 1 job for Channel 2, got {len(ch2_jobs)}"
            assert any(json.loads(j.research_trace or '{}').get('generation_origin') == 'daily_preparation' for j in ch1_jobs)
            assert any(json.loads(j.research_trace or '{}').get('generation_origin') == 'daily_preparation' for j in ch2_jobs)

        # Worker should have been called 2 (ch1) + 1 (ch2) = 3 times
        assert worker.call_count == 3
    finally:
        with SessionLocal() as db:
            c1 = db.get(Channel, p['channel_id'])
            if c1: c1.automatic_generation_enabled = False
            c2 = db.get(Channel, ch2_id)
            if c2: c2.automatic_generation_enabled = False
            db.commit()


def test_channel_error_isolation(publishable, monkeypatch):
    """If one channel fails during preparation, other independent channels must still progress."""
    p = publishable
    worker = Mock()
    monkeypatch.setattr('app.api.videos.run_job', worker)

    with SessionLocal() as db:
        member = db.query(WorkspaceMember).join(User).filter(User.email == 'editor@example.com').one()

        # Channel 1 is enabled but has NO themes, so it will be skipped
        ch1 = db.get(Channel, p['channel_id'])
        ch1.automatic_generation_enabled = True
        ch1.daily_video_target = 1
        # Disable themes on ch1
        for theme in db.query(Personality).filter_by(channel_id=ch1.id).all():
            theme.enabled = False

        # Channel 2 is valid and enabled
        ch2 = Channel(
            id=new_id(), workspace_id=member.workspace_id, member_id=member.id,
            name='Healthy Channel', status='connected', approval_policy='owner_only',
            automatic_generation_enabled=True, daily_video_target=1,
            default_language='en-US', default_voice='en-US'
        )
        db.add(ch2); db.flush()
        theme2 = Personality(
            id=new_id(), workspace_id=member.workspace_id, channel_id=ch2.id,
            name='Healthy Theme', category='Sports', enabled=True
        )
        db.add(theme2)
        db.commit()
        ch2_id = ch2.id

    instant = datetime(2026, 10, 25, 8, 0, tzinfo=timezone.utc)
    try:
        prepare_due(instant)

        with SessionLocal() as db:
            ch2_jobs = db.query(VideoJob).filter_by(channel_id=ch2_id).all()
            assert len(ch2_jobs) == 1, "Healthy channel 2 should have produced a job despite ch1 having no themes"
    finally:
        with SessionLocal() as db:
            c1 = db.get(Channel, p['channel_id'])
            if c1: c1.automatic_generation_enabled = False
            for theme in db.query(Personality).filter_by(channel_id=p['channel_id']).all():
                theme.enabled = True
            c2 = db.get(Channel, ch2_id)
            if c2: c2.automatic_generation_enabled = False
            db.commit()


def test_channel_timezone_determines_local_scheduled_date(publishable, monkeypatch):
    """A channel configured with a non-UTC timezone uses its local calendar date."""
    p = publishable
    worker = Mock()
    monkeypatch.setattr('app.api.videos.run_job', worker)

    with SessionLocal() as db:
        channel = db.get(Channel, p['channel_id'])
        channel.automatic_generation_enabled = True
        channel.daily_video_target = 1
        # Tokyo is UTC+9. At 2026-10-25 18:00 UTC, it is 2026-10-26 03:00 in Tokyo.
        channel.operational_defaults = json.dumps({'timezone': 'Asia/Tokyo'})
        db.commit()

    utc_time = datetime(2026, 10, 25, 18, 0, tzinfo=timezone.utc)
    try:
        prepare_due(utc_time)

        with SessionLocal() as db:
            job = db.query(VideoJob).filter_by(channel_id=p['channel_id']).order_by(VideoJob.created_at.desc()).first()
            assert job is not None
            trace = json.loads(job.research_trace or '{}')
            # Should have scheduled for 2026-10-26 (Tokyo date)
            assert 'auto:' + p['channel_id'] + ':2026-10-26:0' in trace.get('daily_operation', '')
    finally:
        with SessionLocal() as db:
            ch = db.get(Channel, p['channel_id'])
            if ch:
                ch.automatic_generation_enabled = False
                ch.operational_defaults = '{}'
                db.commit()


def test_interrupted_worker_preserves_slot_without_silent_duplication(publishable, monkeypatch):
    """Interrupted daily preparation jobs are marked failed at restart and not duplicated on subsequent scheduler runs."""
    p = publishable
    worker = Mock()
    monkeypatch.setattr('app.api.videos.run_job', worker)

    with SessionLocal() as db:
        channel = db.get(Channel, p['channel_id'])
        channel.automatic_generation_enabled = True
        channel.daily_video_target = 1
        db.commit()

    instant = datetime(2026, 10, 25, 6, 0, tzinfo=timezone.utc)
    try:
        # First preparation run creates the job
        prepare_due(instant)
        assert worker.call_count == 1

        with SessionLocal() as db:
            job = db.query(VideoJob).filter_by(channel_id=p['channel_id']).order_by(VideoJob.created_at.desc()).first()
            assert job.status in ('researching', 'ready_for_review')

            # Simulate process restart while the worker was active
            job.status = 'researching'
            job.current_step = 'script_generation'
            db.commit()

            # Process restart runs recovery
            recover_interrupted_jobs(db)
            db.refresh(job)
            assert job.status == 'failed'
            assert job.current_step == 'interrupted'

        # Subsequent scheduler ticks for the same slot must NOT create a new duplicate job
        prepare_due(instant)
        assert worker.call_count == 1, "Worker should NOT be called again for an already-claimed slot"

        with SessionLocal() as db:
            jobs = db.query(VideoJob).filter_by(channel_id=p['channel_id']).all()
            # Only the fixture job + the single interrupted job exist
            daily_jobs = [j for j in jobs if json.loads(j.research_trace or '{}').get('generation_origin') == 'daily_preparation']
            assert len(daily_jobs) == 1
    finally:
        with SessionLocal() as db:
            ch = db.get(Channel, p['channel_id'])
            if ch:
                ch.automatic_generation_enabled = False
                db.commit()
