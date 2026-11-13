# Linux audio settings

**Verified against the linked desktop and audio-server documentation:
2026-11-11.** Linux distributions use different desktop environments, PipeWire
or PulseAudio configurations, drivers, and players. There is no single menu
path for every system.

## Baseline

- Stereo headphones or stereo earbuds with separate left/right playback are
  required for the intended binaural/channel-separated audio. Speakers, mono
  mixing, or a single earpiece are not equivalent delivery of that audio. If you
  cannot use this setup, use the written guide or an edition-matched transcript
  if available, or skip the audio; no equivalent effects are promised.
- Select the intended stereo output profile and keep left/right balance centered
  unless you use an accessibility adjustment.
- Start at a comfortable, clearly audible level and use normal playback speed
  (1.0x). Turn off unwanted repeat, shuffle, crossfade, EQ, and effects.
- Do not raise volume to chase a perceived effect. Accessibility and comfortable
  listening take priority over a specific stereo presentation.

## Desktop output and optional effects

In your desktop's sound settings, select the stereo headphone output profile and
inspect its channel balance and mono accessibility option. Mono mixes the
left/right channels and is not equivalent delivery of the intended
binaural/channel-separated audio. Keep accessibility settings you rely on; use
the written guide or an edition-matched transcript if available, or skip the
audio. GNOME's menu labels can vary by release; see [Red Hat's GNOME sound
configuration guide](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/9/html/customizing_the_gnome_desktop_environment/configuring-sound-in-gnome_configuring-sound-in-gnome).

On systems using PipeWire or PulseAudio, tools such as `pavucontrol` may expose
output profiles and per-channel balance. Optional EasyEffects, PulseEffects, or
other equalizers/spatial effects can change the presentation; disable them only
if you do not rely on them. See the [PipeWire audio documentation](https://docs.pipewire.org/page_audio.html).

## Troubleshooting

If sound appears mono, check the output profile, player channel controls, and
left/right balance. Settings and names differ across distributions; use the
distribution's current documentation rather than applying a command from
another system. A transcript may be available for the selected published edition.
