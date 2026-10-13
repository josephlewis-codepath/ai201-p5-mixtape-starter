"""
tests/test_feed.py — Mixtape

Tests for the Friends Listening Now feed.
"""

import pytest
from datetime import datetime, timedelta, timezone
from app import create_app, db
from models import User, Song, ListeningEvent, friendships
from services.feed_service import get_friends_listening_now, get_activity_feed


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def friends(app):
    """nova is friends with darius and simone."""
    with app.app_context():
        nova = User(username="nova", email="nova@example.com")
        darius = User(username="darius", email="darius@example.com")
        simone = User(username="simone", email="simone@example.com")
        db.session.add_all([nova, darius, simone])
        db.session.flush()

        for friend in (darius, simone):
            db.session.execute(friendships.insert().values(user_id=nova.id, friend_id=friend.id))

        song = Song(title="Late Song", artist="Various", shared_by=darius.id)
        db.session.add(song)
        db.session.commit()
        yield {"nova": nova.id, "darius": darius.id, "simone": simone.id, "song": song.id}


def _listen(user_id, song_id, when):
    db.session.add(ListeningEvent(user_id=user_id, song_id=song_id, listened_at=when))
    db.session.commit()


def test_listening_now_excludes_yesterday(app, friends):
    """A friend whose last listen was late yesterday should not appear today."""
    with app.app_context():
        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        _listen(friends["darius"], friends["song"], midnight - timedelta(minutes=1))  # 23:59 yesterday
        _listen(friends["simone"], friends["song"], midnight)                         # 00:00 today

        feed = get_friends_listening_now(friends["nova"])
        usernames = [entry["friend"]["username"] for entry in feed]
        assert usernames == ["simone"]


def test_activity_feed_still_includes_yesterday(app, friends):
    """The activity feed is not time-filtered, so yesterday's listen still shows there."""
    with app.app_context():
        midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        _listen(friends["darius"], friends["song"], midnight - timedelta(minutes=1))

        feed = get_activity_feed(friends["nova"])
        assert [entry["friend"]["username"] for entry in feed] == ["darius"]
