# Gala Marshalling

A shared tick sheet for gala marshals: every club, every heat, every station, on each marshal's own phone.

1. Run `schema.sql` once in the Supabase SQL editor.
2. Deploy `app.py` on Streamlit Community Cloud with the secrets `SUPABASE_URL` and `SUPABASE_KEY` (same as the Swim Gala Hub).
3. One person opens the app, loads the whole-gala start list (SportSystems link or Meet Centre PDF), chooses the number of stations and creates the room.
4. Send the room link to every marshal. Each picks their station. When a heat is lined up and everyone is there, tap **Lined up, all here**; it then appears at the next station.

Tests: `python3 tests/test_core.py [start-list.pdf]` and `python3 tests/smoke_ui.py`.
