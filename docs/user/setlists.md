# Setlists

The **Setlists** page organizes folders, individual sets, songs, timing, and exports.

---

## Setlist tree

Left panel: folders and setlists. Drag to reorder or move between folders.

**Context menu** (right-click):

- Folder: rename, delete
- Set: export, export to ABCP, clear set, delete
- Empty area: new set, add folder

Toolbar: **Add setlist**, **Copy…**, **Add folder**, **Import ABCP**

---

## Set metadata {#create-setlist}

When a set is selected, edit on the right:

| Field | Purpose |
|-------|---------|
| **Name** | Setlist title |
| **Band layout** | Optional; enables part UI and Set Play grid |
| **Set date / Set time** | Event scheduling info |
| **Set length** | Target duration |
| **Song Switch Delay** | Default seconds between songs (changeover) |
| **Notes** | Free text |
| **Locked** | Excludes set from Library **Add to Set** menu |

Computed labels show **Set Duration**, **With Part Switching**, and **Remaining** time.

---

## Songs in set {#timing}

- **Add song** — filterable picker (similar to Library)
- Reorder with **↑↓** buttons or drag rows
- **Play** column — preview from set
- Per-song overrides for part assignments (when band layout is set)

---

## Part Assignment {#set-part-assingment}

Available when a band layout is selected for the set

- Select a song in the set's song list
- Click a player card and assign a part to that player
  - Repeat per part, assinging one part per player
- Duplicate parts will highlight in red text
- Orange text means one of two things:
  - The player's part changed from the previous song (normal/ok)
  - The player you assigned that part to lacks proficiency in that instrument (error state)
- If a song layout contains errors, an icon will display in the second column of the song list. Hovering over this will show a tooltip indicating the issue.

It is strongly desired to complete this process for all songs in the set in order to gain the most from this feature

## Save / Delete / Export

- **Save** — persist setlist edits. This is primarilly for set metadata. Songlist is automatically saved on edits, including part assignment.
- **Delete** — remove selected setlist
- **Export** — open [Set export](set-export.md) dialog

---

## Copy and merge

**Copy…** menu (when a setlist is selected):

- Copy Setlist as New
- Prepend / append between setlists

---

## Import ABCP {#import-abcp}

**Import ABCP** loads Maestro / ABC Player playlist files (`.abcp`). See [Import and export formats](import-export.md).

---

## Locked setlists {#locked-setlists}

Locked sets cannot receive songs from the Library context menu **Add to Set**.

---

[← User Guide home](index.md) · [Set export](set-export.md) · [Set Play](set-play.md)
