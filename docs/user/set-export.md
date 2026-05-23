# Set export

Export a setlist to a folder or zip for performers, with optional renaming rules and CSV part sheets.

Open from **Setlists → Export** or the set tree context menu **Export set…**.

---

## Export Settings tab

- Destination folder or zip
- Options for including ABC files, ABCP playlist, and related outputs
- Uses your **Set Export directory** from [Folder rules](settings/folder-rules.md) when applicable

---

## ABC File Renaming tab {#filename-patterns}

Define filename patterns for exported ABC files using variables such as:

- Song title, composer, part count, duration
- Setlist name, position in set, dates

*(See the dialog help text for the full variable list — document expanded examples here later.)*

---

## Part Renaming tab {#part-renaming}

Rename individual parts within ABC files when exporting multi-part sets.

- Similar fields as the file renaming tab, plus a few extras.
- $PlayerAssignment variable only works if you have defined a band layout and assigned parts. However, this is powerful in that part names can contain the name of the player who is supposed to play that part, making it much easier to know who's supposed to play what during playback.

---

## CSV Part Sheet tab {#csv-part-sheet}

Generate a CSV reference sheet for musicians (parts, instruments, assignments).

---

## CSV Part Renaming tab

Customize find-and-replace part naming in the CSV export (helps save space in the spreadsheet).

---

## Player Column Order tab

Reorder columns on the CSV part sheet to match your band's preferences.

---

## Tips

- Export after saving setlist changes
- Ensure you set **Set Export directory** in settings to avoid duplicate indexing of songs
- For ABCP-only sharing, use **Export to ABCP…** from the set context menu ([Import and export](import-export.md))

---

[← User Guide home](index.md) · [Setlists](setlists.md)
