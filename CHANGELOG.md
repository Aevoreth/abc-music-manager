# Changelog

All notable changes to ABC Music Manager are documented here. Most recent at the top.

## Version 0.2.3b
* Set Play:
  * FIX: Part Change Highlighting is now based on next selected song vs. currently playing song, not next selected song vs. previous song in the list.

## Version 0.2.2b

* Setlist and Set Play
  * FIX: Setlist Editor was not fully deleting sets if that set had a Set Play playback history, leaving behind an empty set instead
  * FIX: Newly created setlists were not showing up in Set Play until app restart (Due to list only refreshing on startup)
  * FIX: Set Play no longer requires a band layout for sets to be loaded.
  * ADD: Ability to clear a setlist
  * IMPROVE: Set Play Set selection combo box now has a tree view for folders and sets
  * IMPROVE: Replaced "Add Song" dialogue with a proper, filterable song table similar to Library view

## Version 0.2.1b

* Added: Set Play feature
  * Select and load setlist
  * Broadcast set playback status via a user-created Cloudflare Relay (Cloudflare account required; even heavy usage under normal circumstances will never come close to exceeding free-tier usage)
  * Cloudflare Relay URL defined in Settings; multiple relays can be defined and used for different bands
  * Song list with checkboxes for skip, next, Current, and Played
  * Advancing a song marks the currently selected Current song as Played, the currently selected next song as Current, and the next song in the setlist that is not marked skip as next
  * Band layout with part change highlighting
  * List of band member names; selecting member(s) highlights them on the band layout (not broadcast; client only)
  * Option to automatically mark songs played in Library Playback History
* Added: Band Assistant
  * Select relay and enter the seven-character code from the band leader, then Connect
  * Read-only view of what the band leader is broadcasting, including the song list with skip, next, current, and played fields and the band layout with instrument change highlighting
  * List of band member names; selecting member(s) highlights them on the band layout (not broadcast; client only)
* Added: Settings → Set Playback tab
  * Add band-leader-provided relay URLs for coordinated set playback
  * Generate a WebSocket relay URL to share with band members also using the app
  * Redeploy a Cloudflare Relay in the unlikely event that Cloudflare resource limits are reached
* Note: Creating a relay requires a free Cloudflare account and must be set up and logged in before launching the relay setup wizard. At the appropriate step, the wizard opens the system default browser to authenticate with Cloudflare. A relay can only be created after this authentication completes.

## Version 0.1.11b

* Added: Optional Part Renaming for Exported Sets using customizable pattern
* Added: Setlist export now optionally exports an ABC Player compatible playlist
* Added: String Find and Replace during CSV export to allow for shortening part names
* Added: CSV now exports with an appendix, listing players and required instruments for the set
* Fixed: Student Fiddle now properly named Student's Fiddle

## Version 0.1.10b

* Added part hinting to setlist editor:
  * Previous and next part numbers in player card headers
  * Tooltip on card indicating last instrument player used
  * When instrument differs from previous song that a player played in, part number is colored orange
* Tooltip over warning icon in setlist editor indicating what is triggering the warning to be present
* Fixed table column widths in setlist editor not always restoring correctly
* Fixed issue with window size and position not always returning to previous state

## Version 0.1.8b

* Fixes for Setlist not allowing delete of songs or setlist after files moved
* Setlist copy menu:
  * Clarified appending and prepending setlists by renaming them to append to/prepend to setlist
  * Added Prepend/append from setlist
  * Added Copy setlist
* Player level cap increased from 150 to 250 (some level of future-proofing)
* Song import process enhancements (further iteration planned after tester feedback)

## Version 0.1.7b

* Temporary icon set

## Version 0.1.6b

* Updated documentation to fix errors and include AI/LLM tool use transparency.

## Version 0.1.5b

* Further addressing of Setlist item move crash

## Version 0.1.4b

* Fixed a bug that was causing songs that were dragged and dropped in Setlist Editor to lose action column buttons
* Addressed a crash condition with setlist song drag and drop

## Version 0.1.3b

* Custom order (drag and drop) for bands
* Duplication of bands
* Schema documented in SCHEMA.md. Migration logic created for future updates to be able to port database forward across larger version gaps
* Minor bugs fixed.

## Version 0.1.2b

* Fixed: Status and Transcriber filters failed to open after first use.

## Version 0.1.1b – Initial Beta test
