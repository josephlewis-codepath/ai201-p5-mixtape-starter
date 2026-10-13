"""
tests/test_notifications.py — Mixtape

Tests for notifications created by song interactions.
"""

import pytest
from app import create_app, db
from models import User, Song, Rating
from services.notification_service import rate_song, get_notifications


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def shared_song(app):
    """aaliya shares a song; kenji is another user who can rate it."""
    with app.app_context():
        aaliya = User(username="aaliya", email="aaliya@example.com")
        kenji = User(username="kenji", email="kenji@example.com")
        db.session.add_all([aaliya, kenji])
        db.session.flush()

        song = Song(title="Golden Hour", artist="Solange K", shared_by=aaliya.id)
        db.session.add(song)
        db.session.commit()
        yield {"aaliya": aaliya.id, "kenji": kenji.id, "song": song.id}


def test_rating_notifies_song_sharer(app, shared_song):
    """Rating someone else's song creates a song_rated notification for the sharer."""
    with app.app_context():
        rate_song(shared_song["kenji"], shared_song["song"], 5)

        notifications = get_notifications(shared_song["aaliya"])
        assert len(notifications) == 1
        assert notifications[0]["type"] == "song_rated"
        assert "kenji" in notifications[0]["body"]
        assert "Golden Hour" in notifications[0]["body"]


def test_rating_own_song_does_not_notify(app, shared_song):
    """Rating your own song should not notify yourself."""
    with app.app_context():
        rate_song(shared_song["aaliya"], shared_song["song"], 4)
        assert get_notifications(shared_song["aaliya"]) == []


def test_rating_still_saved_and_updated(app, shared_song):
    """Re-rating updates the existing Rating rather than creating a second one."""
    with app.app_context():
        rate_song(shared_song["kenji"], shared_song["song"], 2)
        rating = rate_song(shared_song["kenji"], shared_song["song"], 5)

        assert rating.score == 5
        assert db.session.query(Rating).filter_by(song_id=shared_song["song"]).count() == 1


def test_invalid_score_creates_no_notification(app, shared_song):
    """A rejected rating should not produce a notification."""
    with app.app_context():
        with pytest.raises(ValueError):
            rate_song(shared_song["kenji"], shared_song["song"], 9)
        assert get_notifications(shared_song["aaliya"]) == []
