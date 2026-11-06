# romklang

romklang adds virtual surround and headphone EQ to PipeWire on Linux, in the same way
[HeSuVi](https://sourceforge.net/projects/hesuvi/) does on Windows. You pick an HRIR and a
headphone EQ from the full HeSuVi lists, and you can switch while music plays.

*Romklang* is Norwegian for the sound of a room.

## What it does

- **HRIRs (virtual speakers):** It reads all of HeSuVi's HRIR files: the 14-channel and
  7-channel ones, the 44.1 kHz set, and the "measured heads" set. Each one shows HeSuVi's own
  description.
- **Headphone EQ:** It reads the AutoEq GraphicEQ files that come with HeSuVi (about 1,350
  headphones) and turns each one into an 8,192-tap minimum-phase FIR. You can also add your
  own FIR filters as WAV files.
- **Upmix:** It applies HeSuVi's stereo to 7.1 matrix. *Auto* turns it off for the HRIRs
  whose description says not to use upmix.
- **Switching:** A window (`romklang gui`) and a CLI (`romklang set`). Music keeps playing
  while you switch, and your apps stay on the same sink.

romklang folds the HRIR, upmix and EQ into one 4-path stereo filter (left to left ear, left to
right ear, right to left ear, right to right ear). It runs it with PipeWire's built-in
convolver, so CPU use stays low.

## How it works

```
apps -> "Virtual surround (romklang)"   stable sink, a loopback in the main PipeWire daemon
     -> romklang_input                  hidden convolver sink, run by romklang@a or romklang@b
     -> your DAC or headphones
```

There are two convolver slots, `romklang@a.service` and `romklang@b.service`, and one runs at
a time. A switch builds the new filter into the idle slot and starts it. It then moves the
stable sink's stream to the new slot through WirePlumber's `target.object` metadata, and
stops the old slot. Both slots name their sink `romklang_input`, so after the old one stops,
the stream's own target finds the new one, and romklang removes the metadata again.
`romklang.service` starts the current slot at login.

If no convolver runs, the stable sink waits for one, because of `node.dont-fallback` and
`node.linger`. Without those two settings the sink would fall back to the default sink,
which is the sink itself, and feed back.

## Requirements

- PipeWire 1.0 or newer with WirePlumber 0.5. Tested on PipeWire 1.6 and WirePlumber 0.5.18
  (Arch Linux).
- Python 3 with `numpy` and `scipy`. `PySide6` is needed for the window only.
  On Arch: `pacman -S python-numpy python-scipy pyside6`.
- The HeSuVi data files. romklang does not include them. Get them from a HeSuVi install
  on Windows (`C:\Program Files\EqualizerAPO\config\HeSuVi`) or from the
  [HeSuVi download](https://sourceforge.net/projects/hesuvi/) (a 7z archive).

## Install

```sh
git clone https://github.com/oysteinkrog/romklang ~/projects/romklang
~/projects/romklang/install.sh                 # links the command, the service and the menu entry
romklang import /path/to/HeSuVi                 # copies hrir/ and eq/ to ~/.local/share/romklang
romklang list outputs                           # find your real output device
romklang setup --output alsa_output.usb-...     # writes the sink, builds the filter, starts the service
systemctl --user restart pipewire               # once, to load the new sink
```

Then pick "Virtual surround (romklang)" as the output in your desktop.

`setup --no-sink` skips the stable sink, if you write your own. Its playback side must target
`romklang_input`, and it needs `node.dont-fallback = true` and `node.linger = true`.

## Use

```sh
romklang gui                                    # the picker window
romklang list hrir atmos                        # search HRIRs and their descriptions
romklang list eq sennheiser hd 6                # every word must match
romklang set --hrir dh- --eq "HD 650"
romklang set --upmix off --gain -3
romklang set --reset gain_db                    # back to the default
romklang status
```

### Level

At gain 0 dB, the loudest steady tone in the worst case (both channels in phase into one ear)
just reaches full scale. Music with sharp transients can still peak above that. So if you
hear distortion, lower the gain. Raise it if the result is too quiet next to the plain device.

### Custom FIR filters

Put a folder with `44100.wav` and `48000.wav` (1 or 2 channels, the headphone correction
only) in `~/.local/share/romklang/fir/NAME/` or `~/.config/romklang/fir/NAME/`. It shows
in the EQ list as "NAME (FIR)". A folder with one rate only is resampled for the other.

### Defaults

`~/.config/romklang/defaults.json` can hold any of `hrir`, `eq`, `upmix`, `gain_db` and
`output`. This is useful for a machine profile kept in a dotfiles repo. `state.json` holds
only the values you set yourself, and those win. A value you never set follows the
defaults file, even if the file changes later.

## Files

| Path | What |
|---|---|
| `~/.local/share/romklang/hrir/`, `eq/` | HeSuVi data, from `romklang import` |
| `~/.local/share/romklang/active-a/`, `active-b/` | each slot's filter: `ir-48000.wav`, `ir-44100.wav`, `built-from.json` |
| `~/.local/share/romklang/slot` | which slot is current |
| `~/.config/romklang/state.json`, `defaults.json` | your choices, and optional defaults |
| `~/.config/pipewire/romklang-a.conf`, `romklang-b.conf` | each slot's convolver config, generated by romklang |
| `~/.config/pipewire/pipewire.conf.d/romklang-sink.conf` | the stable sink, from `romklang setup` |

## Limits

- Input is stereo. A 5.1 or 7.1 stream is mixed down by PipeWire first, then upmixed again
  by the HeSuVi matrix. Discrete surround from games and films is lost.
- The layout of 7-channel HRIR files (left speakers and centre, mirrored for the right) was
  worked out from the energy and timing of each channel, not from HeSuVi's source.
- A switch moves the stream from one convolver to the other without a crossfade. You may
  hear a small click at the moment it moves.
- GraphicEQ files are turned into FIR filters here. The result is close to Equalizer APO's
  GraphicEQ, but not bit-identical.

## Tests

```sh
python3 -m pytest tests
```

## License

MIT. HeSuVi's HRIRs and the AutoEq data have their own licenses, and romklang does not
include them.
