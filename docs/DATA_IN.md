# Data in — how each source reaches the daily page

For Joe. Everything here works only after V0 activation (migrations 0091–0096 applied;
see V0_BACKEND_ACTIVATION). Before that, the page signs in but cannot load days.

| Today card | How it gets data | Your effort |
|---|---|---|
| Check-ins, Meals, Workouts | You type them in the home-screen app (Add tab) | Seconds per entry |
| Health | Apple Health export dropped into `~/PersonalOS_Drop/` | About 2 min, weekly |
| Spending | Chase CSV imported with one command | About 2 min, when you want |
| Places | Overland app on the iPhone, in the background | One-time setup |

## 1. Install the app (once)

Open the published page in Safari on the iPhone → Share → **Add to Home Screen**. Sign in with
your owner email; the link must open in that same app/browser. `?demo=1` tries it without saving.

Use the app, not the old iOS Shortcuts ("Log", food, workout, night). Those still send to the
old `ingest_capture` path, and what they log **does not appear** on the Today cards.

## 2. Apple Health (weekly)

1. iPhone: Health → your picture → **Export All Health Data** → share the `export.zip` to the Mac
   (AirDrop to Downloads is fine).
2. Move it into `~/PersonalOS_Drop/` (keep the name `export.zip`).
3. From `~/PERSONAL_OS_V2`: `PYTHONPATH=. python3 tools/import_drop.py` (preview, writes nothing),
   then the same with `--commit`. The file moves to `_done/`. Dropping the same file again is a no-op.

Proven locally: a synthetic export goes through this importer into the day read with native
units, device and both timestamps (`tests/test_v1_health_flow.py`). Steps show a daily total
only if the `steps` metric has a registered aggregation in production; otherwise the card says
"recorded, but no daily total is set up". Checking that is part of activation.

A daily scheduled import exists (`ops/capture_schedule.py --emit-launchd` prints the job);
it is not installed. Install it only after the first manual import succeeds.

## 3. Chase card (when you want)

Do **not** put the Chase CSV in the drop folder: the drop folder's generic bank importer does not
support your Chase files. Instead:

1. Once: run `uuidgen` and save the value as your card's account ID (reuse it forever for this card).
2. chase.com → card → Download account activity → CSV.
3. Validate (no database): `PYTHONPATH=. python3 -m tools.import_v0_card --file <csv> --account <id>`
4. Save: the same command with `--apply`. Rows the importer cannot match show review buttons
   in the Spending card. Payments are not income; nothing is summed in the app.

## 4. Places (one-time setup)

Install **Overland** on the iPhone. Endpoint:
`https://cykviouklidnbsbgdgdo.supabase.co/functions/v1/location-ingest`. Put the location-ingest
token in Overland's Access Token field only (never in the URL). Settings: All Data logging, batch
size ≤ 1000, default JSON. Visits are derived hourly by the `extract` workflow; the card shows
"not processed yet" until the first refresh after data arrives. The deployed edge function
revision and token must be checked during activation.

## Old jobs still running on this Mac (decision needed)

Inspected 2026-09-26, read-only:

| launchd job | What it does | Recommendation |
|---|---|---|
| `com.personal-os.daily-briefing` | Old *Personal Survilance* briefing, 07:00 | **Remove.** It has failed every day: macOS blocks it from Documents (exit 78). |
| `com.personal-os.edge-physiology` | 03:30 nightly: re-sends ~8k derived health rows from a pre-Sep-9 export to production via the old `ingest-history` function | **Unload.** Writes stale derived data to legacy tables the new app does not read. |
| `com.personal-os.edge-activitywatch` | Every 6 h: ActivityWatch export | **Unload.** ActivityWatch is not running; it skips every time. |

Unloading is reversible (`launchctl bootout gui/$(id -u) <plist>`; the plist files stay). Say
which to unload and it will be done; nothing has been changed.
