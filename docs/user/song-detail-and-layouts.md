# Song detail and layouts

Open **Song detail** from the Library **Actions → Edit** button or by double-clicking a row.

---

## Basic Info tab {#basic-info}

Shows read-only fields parsed from the ABC file (title, composers, transcriber, duration, export timestamp, part count).

You can edit app-managed fields:

- **Rating**
- **Status**
- **Play history** — mark played, edit history dialog

Click **Save** to persist metadata to the database (not to the ABC file).

---

## Notes and Lyrics tab

Store notes and lyrics in the app database. Useful for set notes or performance reminders.

---

## Raw ABC tab {#raw-abc}

**Advanced:** edit the underlying ABC text.

This should be done with extreme caution, as editing the wrong thing or doing so incorrectly can break the file.

If the file changed on disk since you opened the dialog, the app warns you about conflicts before saving.

**Save Metadata to ABC** (writing title/composer back into the file) is not yet implemented. You can do this by manually editing the ABC text if you know what you are doing and are comfortable.

---

## Parts list and Layouts tab {#song-layouts}

- **Not fully working as intended in this context**

Lists ABC parts and any **song layouts** linked to this song.

A **song layout** pairs a **band layout** with assignments: which band member plays which part.

---

## Song layout editor {#part-assignments}

- **Not fully working as intended in this context**

Open from Song detail or Library **Actions → Layout**.

- **New Layout…** — pick a band layout not yet used for this song
- Existing layout names — edit assignments

The grid shows band members and part dropdowns (including **None**).

Layouts affect:

- Playback stereo panning ([Playback](playback.md#stereo))
- Setlist part-assignment UI ([Setlists](setlists.md))
- Set Play part highlighting ([Set Play](set-play.md))

---

[← User Guide home](index.md) · [Bands](bands.md) · [Library](library.md)
