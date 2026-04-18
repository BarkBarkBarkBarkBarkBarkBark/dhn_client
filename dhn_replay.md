# NRD Replay Instructions

> **Note:** NRD does not apply the same filters/manipulations that you see on `.NCS` files.

---

## Required Files

1. `RawData.nrd`
2. Config file (e.g. `p98cs_replay_sc.cfg`) — file paths at the top of the script must be updated

---

## Step 1: Prepare the Config File

Use `Replay_Atlas_generic.cfg` as the template to create your config file.

1. Create a separate folder inside `nrd_replay/` and place both the `.nrd` and `.cfg` files inside it.
2. In the config file, update the following:
   - `SetDataDirectory "C:\dataReplay\XXXX"` → change to the new folder location
   - `RawDataFile "XXX-SPECIFY.nrd"` → change to the specific `.nrd` filename (copy address as text)
3. Delete extraneous content between `-SetNetComDataBufferSize Events 3000` and `-CreateCscAcqEnt`.
4. Copy/paste the `-CreateCscAcqEnt` block to match the number of CSC channels:
   - Channels `0–255` or `1–256` are all macros for UC Davis data
5. Delete any overlap between micro and macro channel definitions, then save.
   - Delete macros if necessary.

### Channel Settings

| Channel Type | `SetSubSamplingInterleave` | Sample Rate | Notes |
|---|---|---|---|
| **Micros** | `1` | 32 kHz | Do not subsample micro channels |
| **Macros** | `16` | ~2 kHz | SubSampling of 16 corresponds to 2k Hz |

> **Important:** After saving, upload the config file into the folder you just created and verify the file's modified timestamp is current.

---

## Step 2: Set Up Software

### Pegasus
- Open Pegasus and start with a **new data file/setup** (skip the license file — not needed for replay).

### MATLAB Script (`NetCom_expStarter_ATLAS_AC.m`)
- This script interfaces with Pegasus via NetCom.
- It calls NLX helper files from the `neuralynxNetcom201/` package folder (inside `nrd_replay/`). **Add this folder to the MATLAB path.**
- If you re-download `NetCom_expStarter_ATLAS_AC.m` (Nov 26, 2024 version):
  - Comment out **lines 17 and 24**
  - Update the timestamps in the code as usual

---

## Step 3: Configure Pegasus Playback

Navigate to **Pegasus > Raw Data File Playback Properties**:

- **Filename** — set to match the path in your config file
- **Continuous file playback** — **uncheck this**
- **Playback speed** — set to the **slowest** setting (to avoid dropped samples)
- **Timestamp range** — note the values shown here; update **line 23** of the MATLAB script to match

---

## Step 4: Configure Display

Navigate to **Pegasus > Add Window > Time Window > Display > Add Plots** and add ~15 CSC rows.

Then go to **View > Acquisition Entities and Display Properties > Entities**. CSC numbers should align with the config file.

| Setting | Micros | Macros |
|---|---|---|
| Sample frequency | 32 kHz | — |
| Input range | 3000 µV | 10000 µV |
| Sub-sampling interleave | 1 | 16 |
| Low cut | 0.1 Hz | — |
| High cut | None | None (remove if present) |

---

## Step 5: Run the Replay

1. Run the MATLAB script.
2. In Pegasus, **ACQ** should turn green and **REC** should turn purple.
   - If both are gray, manually click the **REC** button until both are green/purple.
3. Drag the `expStarter` file into the new data folder.

---

## Output

When replay is complete, a folder named with the current date/time will be generated containing:

- `.NCS` files (one per channel)
- An event file (for TTLs)
