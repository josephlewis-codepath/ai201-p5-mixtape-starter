# Project 5 — Mixtape Bug Hunt: Submission

**Branch:** `bugfix/mixtape`

## AI Usage

<!-- AI_USAGE -->

---

## Codebase Map

### Main files and their roles

| File | Responsibility |
|---|---|
| `app.py` | Flask application factory. `create_app(config=None)` builds the app, sets the SQLite URI (`sqlite:///mixtape.db` by default, overridable by `DATABASE_URL` or a `config` dict, which is how the tests use `sqlite:///:memory:`), initialises the shared `db = SQLAlchemy()` object, registers four blueprints under `/songs`, `/playlists`, `/users`, `/feed`, and calls `db.create_all()`. |
| `models.py` | All SQLAlchemy models. 7 model classes: `User`, `Tag`, `Song`, `ListeningEvent`, `Rating`, `Playlist`, `Notification`. It also defines 3 association tables: `friendships` (self-referential User↔User, stored as two directed rows per friendship), `song_tags` (Song↔Tag), and `playlist_entries` (Playlist↔Song, which carries extra columns `position`, `added_by`, `added_at`, so playlist order is explicit). All primary keys are UUID strings. `Rating` has a unique constraint on `(user_id, song_id)` so each user rates a song at most once. `User` stores denormalised streak state (`listening_streak`, `last_listened_at`) and does not recompute it from events. Every model has a `to_dict()` used for JSON responses. |
| `routes/songs.py` | `GET /songs/search?q=`, `GET /songs/<id>`, `POST /songs/<id>/rate`, `POST /songs/<id>/listen`. |
| `routes/playlists.py` | `POST /playlists/` (create), `GET /playlists/<id>` (metadata), `GET /playlists/<id>/songs`, `POST /playlists/<id>/songs` (add a song). |
| `routes/users.py` | `GET /users/<id>`, `GET /users/<id>/streak`, `GET /users/<id>/notifications[?unread_only=true]`, `POST /users/notifications/<id>/read`. This is the only route file that touches the DB directly (`get_user`). |
| `routes/feed.py` | `GET /feed/<id>/listening-now` and `GET /feed/<id>/activity`. |
| `services/streak_service.py` | `record_listening_event()` writes a `ListeningEvent` and calls `update_listening_streak()`, which compares the calendar date of `now` against `user.last_listened_at` to decide whether the streak stays the same, increments, or resets. `get_streak()` just reads the stored column. |
| `services/feed_service.py` | `get_friends_listening_now()` returns each friend's single most recent `ListeningEvent` newer than a cutoff. `get_activity_feed()` returns the latest N friend events with no time filter. |
| `services/search_service.py` | `search_songs()` does a case-insensitive `ILIKE` match on `Song.title` / `Song.artist`. `get_song()` fetches a song by ID. |
| `services/notification_service.py` | Owns notifications **and** the two "interaction" actions that should produce them: `add_to_playlist()` and `rate_song()`. `create_notification()` is the shared helper that inserts and commits a `Notification`. Also `get_notifications()` and `mark_as_read()`. |
| `services/playlist_service.py` | `create_playlist()`, `get_playlist()` (metadata), `get_user_playlists()`, and `get_playlist_songs()`, which joins `Song` to `playlist_entries` and orders by `position`. |
| `seed_data.py` | Drops and recreates the DB, then seeds 5 users (nova, darius, simone, kenji, aaliya), 5 friendships, 10 tags, 13 songs (grouped by 0, 1, and 3 tags), listening events from 10 minutes to ~58 hours ago, 3 playlists with 7 songs each at positions 1–7, and one `song_added_to_playlist` notification. |
| `tests/` | pytest suites for streaks, search, and playlists. Each builds a fresh in-memory app via `create_app({...":memory:"})` and calls service functions directly, not over HTTP. |

### Data flow 1: a user rates a song

1. `POST /songs/<song_id>/rate` with JSON `{"user_id", "score"}` hits `rate()` in `routes/songs.py`.
2. The route checks that both fields are present (400 otherwise), casts `score` to `int`, and calls `rate_song(user_id, song_id, score)` in `services/notification_service.py`.
3. `rate_song()` checks that the score is between 1 and 5, loads the `Song` and the rater `User` with `db.session.get` (raising `ValueError` if either is missing), then looks for an existing `Rating` for that `(user_id, song_id)`. If one exists, it updates the score. If not, it adds a new `Rating`. Then it commits.
4. It returns the `Rating`. The route serialises it with `to_dict()` and returns 201. Any `ValueError` becomes a 400.

### Data flow 2: a user adds a song to a playlist

`POST /playlists/<id>/songs` → `routes/playlists.add_song()` → `notification_service.add_to_playlist(playlist_id, song_id, added_by)`. This loads the Song, User, and Playlist, inserts the song into the playlist, then calls `create_notification(user_id=song.shared_by, notification_type="song_added_to_playlist", ...)` when the adder is not the song's original sharer. The notification is later read through `GET /users/<id>/notifications` → `get_notifications()`, which orders by `created_at` descending.

### Data flow 3: a user views a playlist

`GET /playlists/<id>/songs` → `routes/playlists.get_songs()` → `playlist_service.get_playlist_songs()`. This runs `SELECT song JOIN playlist_entries WHERE playlist_id = ? ORDER BY position ASC` and serialises the songs. The route wraps the list as `{"songs": [...], "count": n}`.

### Patterns I noticed

- **Thin routes, fat services.** Routes only parse JSON or query args, call one service function, and turn the result (or a `ValueError`) into a JSON response with a status code. All business logic and DB access live in `services/`.
- **Errors are `ValueError`.** Services raise `ValueError` for not-found or invalid input, and each route maps it to a 404 (reads) or a 400 (writes).
- **Services commit their own transactions.** Each write service calls `db.session.commit()` itself.
- **Notifications are a side effect of an interaction.** They are not created by a separate event system. The function that performs the interaction calls `create_notification()` inline, which is why `add_to_playlist` and `rate_song` live in `notification_service.py` and not in playlist or song services.
- **Times are UTC.** Models default to `datetime.now(timezone.utc)`. SQLite stores them as naive values, so services re-attach `tzinfo=utc` when they compare them (for example in `update_listening_streak`).
- **Two query styles.** Most services use the legacy `db.session.query(...)` API. `search_service` uses the 2.0-style `db.session.execute(select(...)).scalars()`.

---

## Root Cause Analyses

<!-- RCA -->
