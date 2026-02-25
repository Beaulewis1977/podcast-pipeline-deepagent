"""Audio mix helpers — stinger placement and sidechain ducking for production sound kits.

Provides deterministic stinger insertion (intro, transition, outro) with optional
sidechain ducking via FFmpeg ``sidechaincompress``.

Key design decisions:
- Stingers are probed and re-normalized to a canonical PCM working format via
  ``ffprobe`` + ``aresample``/``aformat`` BEFORE entering the ducking filtergraph.
  This prevents VBR/container timing drift from destabilising the sidechain compressor.
- Missing assets degrade gracefully: a warning is logged and the stinger is skipped.
  Base exports are never blocked by absent optional sound files.
- All parameters flow through ``SoundKitConfig`` (config/settings.py) and the active
  ``BrandingProfile`` (models/branding.py).  No configuration is hard-coded here.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from podcast_pipeline.utils.ffmpeg import FFmpegError, run_ffmpeg, run_ffprobe

if TYPE_CHECKING:
    from podcast_pipeline.config.settings import SoundKitConfig

logger = structlog.get_logger(__name__)

# ──────────────────────────────────────────────────────────────
# Public constants
# ──────────────────────────────────────────────────────────────

#: Stinger types used in event-triggered placement logic.
STINGER_INTRO = "intro"
STINGER_TRANSITION = "transition"
STINGER_OUTRO = "outro"


# ──────────────────────────────────────────────────────────────
# Stinger normalization helpers
# ──────────────────────────────────────────────────────────────


def probe_audio_format(source_path: Path) -> dict[str, str | int | float]:
    """Probe audio stream metadata via ffprobe.

    Returns a mapping with keys: ``sample_rate``, ``channels``, ``codec_name``,
    ``duration``.  Returns an empty dict when probing fails (caller decides).

    Args:
        source_path: Path to the audio/video file to probe.

    Returns:
        Dict of audio stream metadata or empty dict on failure.
    """
    try:
        probe = run_ffprobe(source_path)
        streams = probe.get("streams", [])
        for stream in streams:
            if stream.get("codec_type") == "audio":
                return {
                    "sample_rate": int(stream.get("sample_rate", 0) or 0),
                    "channels": int(stream.get("channels", 0) or 0),
                    "codec_name": str(stream.get("codec_name", "")),
                    "duration": float(stream.get("duration", 0) or 0),
                }
    except Exception as exc:
        logger.warning("stinger_probe_failed", source=str(source_path), error=str(exc))

    return {}


def normalize_stinger(
    source_path: Path,
    output_dir: Path,
    kit_config: SoundKitConfig,
    stinger_type: str,
) -> Path | None:
    """Normalize a stinger to the canonical working audio format.

    Re-encodes the stinger to the configured sample rate, channel count, and
    sample format using FFmpeg ``aresample`` + ``aformat`` filters.  The output
    is written to ``output_dir`` as a flat PCM WAV file so that VBR/container
    timing quirks cannot destabilise the downstream sidechaincompress chain.

    Args:
        source_path: Original stinger asset (WAV/MP3/FLAC etc.)
        output_dir: Working directory where normalized file is written.
        kit_config: SoundKitConfig with canonical format settings.
        stinger_type: One of ``STINGER_INTRO``, ``STINGER_TRANSITION``,
            ``STINGER_OUTRO`` — used for output filename and log context.

    Returns:
        Path to the normalized WAV file, or ``None`` if normalization failed.
    """
    out_path = output_dir / f"__stinger_{stinger_type}_norm.wav"

    sr = kit_config.canonical_sample_rate
    ch = kit_config.canonical_channels
    fmt = kit_config.canonical_sample_fmt

    filter_chain = f"aresample={sr},aformat=sample_fmts={fmt}:channel_layouts={'stereo' if ch == 2 else 'mono'}"

    args = [
        "-y",
        "-i",
        str(source_path),
        "-af",
        filter_chain,
        "-ac",
        str(ch),
        str(out_path),
    ]

    try:
        run_ffmpeg(args)
        if not out_path.exists() or out_path.stat().st_size == 0:
            logger.warning(
                "stinger_normalize_empty_output",
                stinger=stinger_type,
                source=str(source_path),
            )
            return None
        logger.debug(
            "stinger_normalized",
            stinger=stinger_type,
            source=str(source_path),
            output=str(out_path),
            sample_rate=sr,
            channels=ch,
            sample_fmt=fmt,
        )
        return out_path
    except FFmpegError as exc:
        logger.warning(
            "stinger_normalize_failed",
            stinger=stinger_type,
            source=str(source_path),
            error=str(exc),
        )
        return None


# ──────────────────────────────────────────────────────────────
# Filtergraph builders
# ──────────────────────────────────────────────────────────────


def build_intro_filtergraph(
    stinger_duration_s: float,
    kit_config: SoundKitConfig,
    voice_label: str = "0:a",
    stinger_label: str = "1:a",
) -> tuple[str, str]:
    """Build a filter_complex string that mixes an intro stinger over the voice track.

    The stinger starts at t=0 and plays for ``stinger_duration_s``.  During
    stinger playback the voice track is ducked via ``sidechaincompress``.  After
    the stinger ends, voice plays normally.

    Args:
        stinger_duration_s: Duration (seconds) of the normalized intro stinger.
        kit_config: SoundKitConfig with ducking and volume settings.
        voice_label: FFmpeg input label for the main voice track (default ``0:a``).
        stinger_label: FFmpeg input label for the stinger (default ``1:a``).

    Returns:
        A ``(filter_complex, audio_out_label)`` tuple ready for use in an FFmpeg
        command with ``-filter_complex`` / ``-map`` flags.
    """
    duck = kit_config.ducking
    vol_db = duck.stinger_volume_db
    attack_ms = duck.attack_ms
    release_ms = duck.release_ms
    ratio = duck.ratio
    threshold_linear = 10.0 ** (duck.threshold_db / 20.0)

    # Build stinger chain: volume → optional ducking sidechain
    stinger_chain = f"[{stinger_label}]volume={vol_db}dB[stgr_adj]"

    if duck.enabled:
        sc_params = (
            f"threshold={threshold_linear:.6f}"
            f":ratio={ratio}"
            f":attack={attack_ms}"
            f":release={release_ms}"
        )
        sidechain = (
            f"[{voice_label}][stgr_adj]sidechaincompress={sc_params}[voice_ducked];"
            f"[voice_ducked][stgr_adj]amix=inputs=2:normalize=0[aout]"
        )
        filter_complex = f"{stinger_chain};{sidechain}"
    else:
        filter_complex = f"{stinger_chain};[{voice_label}][stgr_adj]amix=inputs=2:normalize=0[aout]"

    return filter_complex, "[aout]"


def build_outro_filtergraph(
    total_duration_s: float,
    outro_duration_s: float,
    kit_config: SoundKitConfig,
    voice_label: str = "0:a",
    stinger_label: str = "1:a",
) -> tuple[str, str]:
    """Build a filter_complex for an outro stinger that fades in during the last N seconds.

    Args:
        total_duration_s: Total duration of the main voice/video track.
        outro_duration_s: Duration (seconds) of the normalized outro stinger.
        kit_config: SoundKitConfig with ducking/fade settings.
        voice_label: FFmpeg input label for main voice.
        stinger_label: FFmpeg input label for outro stinger.

    Returns:
        ``(filter_complex, audio_out_label)`` tuple.
    """
    duck = kit_config.ducking
    vol_db = duck.stinger_volume_db
    attack_ms = duck.attack_ms
    release_ms = duck.release_ms
    ratio = duck.ratio
    threshold_linear = 10.0 ** (duck.threshold_db / 20.0)

    # Outro starts outro_trigger_s before end of content
    trigger_s = max(0.0, total_duration_s - kit_config.outro_trigger_s)

    # Fade the outro in over the first 0.5s of its audible window
    fade_dur = min(0.5, kit_config.outro_trigger_s / 2.0)
    outro_chain = (
        f"[{stinger_label}]"
        f"volume={vol_db}dB,"
        f"afade=t=in:st=0:d={fade_dur},"
        f"adelay={int(trigger_s * 1000)}|{int(trigger_s * 1000)}"
        f"[outro_placed]"
    )

    if duck.enabled:
        sc_params = (
            f"threshold={threshold_linear:.6f}"
            f":ratio={ratio}"
            f":attack={attack_ms}"
            f":release={release_ms}"
        )
        sidechain = (
            f"[{voice_label}][outro_placed]sidechaincompress={sc_params}[voice_ducked];"
            f"[voice_ducked][outro_placed]amix=inputs=2:normalize=0:duration=first[aout]"
        )
        filter_complex = f"{outro_chain};{sidechain}"
    else:
        filter_complex = (
            f"{outro_chain};"
            f"[{voice_label}][outro_placed]amix=inputs=2:normalize=0:duration=first[aout]"
        )

    return filter_complex, "[aout]"


def build_transition_filtergraph(
    cut_boundary_s: float,
    kit_config: SoundKitConfig,
    voice_label: str = "0:a",
    stinger_label: str = "1:a",
) -> tuple[str, str]:
    """Build a filter_complex to mix a transition stinger at a specific cut boundary.

    The transition stinger is delayed to ``cut_boundary_s`` and ducked against
    the voice track.

    Args:
        cut_boundary_s: Time offset (seconds) at which the stinger begins.
        kit_config: SoundKitConfig with ducking settings.
        voice_label: FFmpeg input label for main voice.
        stinger_label: FFmpeg input label for transition stinger.

    Returns:
        ``(filter_complex, audio_out_label)`` tuple.
    """
    duck = kit_config.ducking
    vol_db = duck.stinger_volume_db
    attack_ms = duck.attack_ms
    release_ms = duck.release_ms
    ratio = duck.ratio
    threshold_linear = 10.0 ** (duck.threshold_db / 20.0)

    delay_ms = int(cut_boundary_s * 1000)
    stinger_chain = f"[{stinger_label}]volume={vol_db}dB,adelay={delay_ms}|{delay_ms}[stgr_placed]"

    if duck.enabled:
        sc_params = (
            f"threshold={threshold_linear:.6f}"
            f":ratio={ratio}"
            f":attack={attack_ms}"
            f":release={release_ms}"
        )
        sidechain = (
            f"[{voice_label}][stgr_placed]sidechaincompress={sc_params}[voice_ducked];"
            f"[voice_ducked][stgr_placed]amix=inputs=2:normalize=0:duration=first[aout]"
        )
        filter_complex = f"{stinger_chain};{sidechain}"
    else:
        filter_complex = (
            f"{stinger_chain};"
            f"[{voice_label}][stgr_placed]amix=inputs=2:normalize=0:duration=first[aout]"
        )

    return filter_complex, "[aout]"


# ──────────────────────────────────────────────────────────────
# High-level stinger application helpers
# ──────────────────────────────────────────────────────────────


def apply_intro_stinger(
    video_path: Path,
    stinger_path: Path,
    output_path: Path,
    kit_config: SoundKitConfig,
    work_dir: Path | None = None,
) -> Path | None:
    """Apply an intro stinger to a video/audio file.

    Normalizes the stinger to canonical PCM format, then mixes it at t=0 with
    optional sidechain ducking.  Writes result to ``output_path``.

    Args:
        video_path: Main voice/video track.
        stinger_path: Raw intro stinger asset (WAV/MP3/FLAC).
        output_path: Destination file for the mixed output.
        kit_config: SoundKitConfig with ducking and normalization policy.
        work_dir: Temporary working directory.  Created and cleaned up internally
            when ``None``; caller controls lifecycle when provided.

    Returns:
        ``output_path`` on success, ``None`` on any failure (with warning logged).
    """
    if not stinger_path.exists():
        logger.warning(
            "stinger_file_missing",
            stinger=STINGER_INTRO,
            path=str(stinger_path),
        )
        return None

    def _run(tmp: Path) -> Path | None:
        norm = normalize_stinger(stinger_path, tmp, kit_config, STINGER_INTRO)
        if norm is None:
            return None

        meta = probe_audio_format(norm)
        stinger_dur = float(meta.get("duration", 0.0))

        filtergraph, out_label = build_intro_filtergraph(stinger_dur, kit_config)

        args = [
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(norm),
            "-filter_complex",
            filtergraph,
            "-map",
            "0:v?",
            "-map",
            out_label,
            "-c:v",
            "copy",
            str(output_path),
        ]
        try:
            run_ffmpeg(args)
            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.warning(
                    "stinger_mix_empty_output",
                    stinger=STINGER_INTRO,
                    output=str(output_path),
                )
                return None
            logger.info(
                "stinger_applied",
                stinger=STINGER_INTRO,
                output=str(output_path),
            )
            return output_path
        except FFmpegError as exc:
            logger.warning(
                "stinger_mix_failed",
                stinger=STINGER_INTRO,
                error=str(exc),
            )
            return None

    if work_dir is not None:
        return _run(work_dir)

    with tempfile.TemporaryDirectory(prefix="pod_stinger_intro_") as tmp_str:
        return _run(Path(tmp_str))


def apply_outro_stinger(
    video_path: Path,
    stinger_path: Path,
    output_path: Path,
    kit_config: SoundKitConfig,
    total_duration_s: float,
    work_dir: Path | None = None,
) -> Path | None:
    """Fade in an outro stinger during the last N seconds of a video/audio file.

    Args:
        video_path: Main voice/video track.
        stinger_path: Raw outro stinger asset.
        output_path: Destination file.
        kit_config: SoundKitConfig.
        total_duration_s: Total duration of the main track in seconds.
        work_dir: Optional working directory.

    Returns:
        ``output_path`` on success, ``None`` on failure.
    """
    if not stinger_path.exists():
        logger.warning(
            "stinger_file_missing",
            stinger=STINGER_OUTRO,
            path=str(stinger_path),
        )
        return None

    def _run(tmp: Path) -> Path | None:
        norm = normalize_stinger(stinger_path, tmp, kit_config, STINGER_OUTRO)
        if norm is None:
            return None

        meta = probe_audio_format(norm)
        outro_dur = float(meta.get("duration", 0.0))

        filtergraph, out_label = build_outro_filtergraph(total_duration_s, outro_dur, kit_config)

        args = [
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(norm),
            "-filter_complex",
            filtergraph,
            "-map",
            "0:v?",
            "-map",
            out_label,
            "-c:v",
            "copy",
            str(output_path),
        ]
        try:
            run_ffmpeg(args)
            if not output_path.exists() or output_path.stat().st_size == 0:
                logger.warning(
                    "stinger_mix_empty_output",
                    stinger=STINGER_OUTRO,
                    output=str(output_path),
                )
                return None
            logger.info(
                "stinger_applied",
                stinger=STINGER_OUTRO,
                output=str(output_path),
            )
            return output_path
        except FFmpegError as exc:
            logger.warning(
                "stinger_mix_failed",
                stinger=STINGER_OUTRO,
                error=str(exc),
            )
            return None

    if work_dir is not None:
        return _run(work_dir)

    with tempfile.TemporaryDirectory(prefix="pod_stinger_outro_") as tmp_str:
        return _run(Path(tmp_str))


def apply_transition_stingers(
    video_path: Path,
    stinger_path: Path,
    cut_boundaries_s: list[float],
    output_path: Path,
    kit_config: SoundKitConfig,
    work_dir: Path | None = None,
) -> Path | None:
    """Apply transition stingers at each cut boundary in the edit plan.

    Normalizes the transition stinger once, then for each boundary places a copy
    at the cut timestamp.  When multiple boundaries are present they are applied
    sequentially (one boundary per pass), chaining the output of each pass as
    input to the next.

    Args:
        video_path: Main voice/video track.
        stinger_path: Raw transition stinger asset.
        cut_boundaries_s: List of timestamps (seconds) where cut boundaries occur.
        output_path: Destination file.
        kit_config: SoundKitConfig.
        work_dir: Optional working directory.

    Returns:
        ``output_path`` on success, ``None`` if no boundaries or on failure.
    """
    if not stinger_path.exists():
        logger.warning(
            "stinger_file_missing",
            stinger=STINGER_TRANSITION,
            path=str(stinger_path),
        )
        return None

    if not cut_boundaries_s:
        logger.debug("transition_stingers_no_boundaries", count=0)
        return None

    def _run(tmp: Path) -> Path | None:
        norm = normalize_stinger(stinger_path, tmp, kit_config, STINGER_TRANSITION)
        if norm is None:
            return None

        current_input = video_path
        # Work through each boundary in order
        for idx, boundary in enumerate(cut_boundaries_s):
            is_last = idx == len(cut_boundaries_s) - 1
            pass_output = output_path if is_last else (tmp / f"__trans_pass_{idx}.mkv")

            filtergraph, out_label = build_transition_filtergraph(boundary, kit_config)

            args = [
                "-y",
                "-i",
                str(current_input),
                "-i",
                str(norm),
                "-filter_complex",
                filtergraph,
                "-map",
                "0:v?",
                "-map",
                out_label,
                "-c:v",
                "copy",
                str(pass_output),
            ]
            try:
                run_ffmpeg(args)
                if not pass_output.exists() or pass_output.stat().st_size == 0:
                    logger.warning(
                        "transition_stinger_pass_empty",
                        boundary=boundary,
                        pass_idx=idx,
                    )
                    return None
                current_input = pass_output
            except FFmpegError as exc:
                logger.warning(
                    "stinger_mix_failed",
                    stinger=STINGER_TRANSITION,
                    boundary=boundary,
                    error=str(exc),
                )
                return None

        logger.info(
            "transition_stingers_applied",
            count=len(cut_boundaries_s),
            output=str(output_path),
        )
        return output_path

    if work_dir is not None:
        return _run(work_dir)

    with tempfile.TemporaryDirectory(prefix="pod_stinger_trans_") as tmp_str:
        return _run(Path(tmp_str))


# ──────────────────────────────────────────────────────────────
# Resolve branding-profile sound paths
# ──────────────────────────────────────────────────────────────


def resolve_sound_kit_paths(
    profile_intro: Path | None,
    profile_transition: Path | None,
    profile_outro: Path | None,
    kit_config: SoundKitConfig,
    branding_dir: Path | None = None,
) -> tuple[Path | None, Path | None, Path | None]:
    """Resolve sound asset paths from BrandingProfile and SoundKitConfig.

    Priority: BrandingProfile paths (set by YAML author) take precedence over
    ``SoundKitConfig`` paths.  Relative paths are resolved relative to
    ``branding_dir`` when provided.

    Args:
        profile_intro: intro_sound from BrandingProfile (may be None).
        profile_transition: transition_sound from BrandingProfile.
        profile_outro: outro_sound from BrandingProfile.
        kit_config: SoundKitConfig with fallback intro/transition/outro paths.
        branding_dir: Directory that branding profiles live in — used to resolve
            relative paths.

    Returns:
        Tuple ``(intro_path, transition_path, outro_path)`` where each element
        is an absolute-or-resolved Path or ``None`` when not configured.
    """

    def _resolve(path: Path | None, branding_base: Path | None) -> Path | None:
        if path is None:
            return None
        if path.is_absolute():
            return path
        if branding_base is not None:
            return branding_base / path
        return path

    intro = _resolve(profile_intro, branding_dir) or _resolve(kit_config.intro_path, branding_dir)
    transition = _resolve(profile_transition, branding_dir) or _resolve(
        kit_config.transition_path, branding_dir
    )
    outro = _resolve(profile_outro, branding_dir) or _resolve(kit_config.outro_path, branding_dir)
    return intro, transition, outro
