---
title: HOA map attachments in the water committee's Drive
created: 2026-10-30
item: sd:6690
branch: build/sd-282
---

# Design — hoa-attachments

The item's row holds status, progress and decisions; this page holds the shape.

## Problem

The HOA map shows 47 water assets: 30 valves, 14 hydrants, 2 wells and 1 tank.
Their documents and pictures live in the water committee's Drive, in a Water System folder.
The map's Details pane cannot show them, and nobody can add one from the map.

The operator asked for both Upload and Reference (note #34609).
Uploads go into the asset's Drive folder, only when the operator presses Upload (note #34610, hoa sd:6692).

## Approach

Add no store. An asset's attachments are its Drive folder's listing.

- **Settings.** `hoa.water_system_folder` holds the Water System folder id (ruling on note #36030).
  `hoa.google_account` already names the account workspace-mcp reads as.
  The id stays in the database, never in this public tree.
- **Folders, found by name.** A valve or hydrant is `Main/<asset id>`, made on its first attachment.
  `WELL-A1` and `WELL-A2` are `Well A1` and `Well A2`; the tank is `Cistern`.
- **Credential.** Every Drive call goes through workspace-mcp over HTTP, as Import to Slides does.
  The dashboard holds no Google token, and nothing copies one.
- **List.** `GET /api/hoa/attachments?asset=<id>` lists the folder.
  A `.url` file is a Reference; its target is read from its text and kept only when it is a Drive or Docs link.
  A missing asset folder is an empty list, and a read makes no folder.
- **Pictures.** The dashboard's CSP allows images from itself only.
  `GET /api/hoa/attachments/picture?id=<file>` asks workspace-mcp for a download URL and returns the bytes.
  The server fetches only from workspace-mcp's own host, and sends only an `image/*` type, never SVG.
- **Upload.** The page stages the bytes at `POST /api/hoa/attach/file`, the Sources tab's staging with HOA's suffixes.
  `POST /api/hoa/attach {"asset", "sha256", "name"}` then writes the file into the folder, base64 with its sha256.
  The cap is 20 MB: the bytes ride in one workspace-mcp call.
- **Reference.** `POST /api/hoa/attach {"asset", "link", "name"}` writes `<name>.url` naming the link (ruling on note #36031).
  workspace-mcp cannot make a Drive shortcut.
- **Details.** The pane lists each file: pictures as thumbnails, the rest as links that open Drive in a new tab.
  It holds an Upload file field and a Reference link field.

## Non-goals

- No thumbnail cache: each Details read downloads the asset's pictures again.
  Add one when an asset holds enough pictures that Details is slow.
- No delete or rename from the map: Drive does that.
- No other Water System folders (Submarine, Diesel Generator): no map asset names them.

## Failure table

| Step | State moved | Failure | Recovery | Test |
| --- | --- | --- | --- | --- |
| Read settings | none | `hoa.water_system_folder` unset | 503 names `sd config set`; nothing sent | `test_failures_are_named_never_an_empty_list` |
| Find subfolder | none | Cistern renamed or gone | 503 names the folder; nothing written | same |
| Find subfolder | none | two folders of one name | 503 names both ids; merge in Drive | same |
| Any call | none | workspace-mcp down or token expired | 503 "Nothing was written"; re-login in workspace-mcp | `test_each_failure_says_whether_drive_holds_the_file` |
| Stage bytes | a staged file | upload cut short | `stage` removes the part file | `test_an_upload_that_drips_is_stopped_at_its_whole_bound` (`test_source_intake`) |
| Stage bytes | none | wrong suffix or over 20 MB | 400 names the rule | `test_a_staging_refusal_names_the_suffixes_and_the_cap` |
| Make asset folder | a Drive folder | two first uploads race | one lock per server; a second server's race shows as two folders, then the row above | `test_the_first_upload_to_a_valve_makes_its_folder_once_and_writes_the_bytes` |
| Make asset folder | a Drive folder | the upload after it fails | the next press finds the folder and reuses it | `test_the_first_upload_to_a_valve_makes_its_folder_once_and_writes_the_bytes` |
| Write file | a Drive file | refused | 503 "Nothing was written"; the staged copy stays | `test_each_failure_says_whether_drive_holds_the_file` |
| Write file | a Drive file, maybe | no answer | 504 "not known; look in the folder before you press again" | same |
| Write file | a Drive file, maybe | an answer naming no created file of that name | 504, as no answer; the staged copy stays | `test_an_answer_naming_no_created_file_is_not_known` |
| Write file | none | staged copy aged out | 400 "no longer staged"; nothing sent | same |
| Picture | none | URL on another host | 502; nothing fetched | `test_a_picture_comes_from_workspace_mcps_own_host_only` |

## Acceptance criteria

- Details of the tank lists the Cistern folder: pictures as thumbnails, documents and References as links.
- A valve's first Upload makes `Main/<id>` once and writes the file there; a second reuses the folder.
- A Reference writes a `.url` file for a Drive or Docs link only.
- Every failure says whether Drive holds the file.

## Risks

- The setting key must be declared in the hoa checkout's `sd-plugin.json` before `sd config set` takes it.
  Until then the list answers 503 naming the key.
- The listing's text shape is workspace-mcp's; a change there reads as an empty folder.
  The tests pin the shape the server printed on 2026-10-30.
