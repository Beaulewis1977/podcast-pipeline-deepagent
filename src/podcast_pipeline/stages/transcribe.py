"""Transcribe stage: Speech-to-text with filler detection and multi-track support."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from faster_whisper import WhisperModel

from podcast_pipeline.config import Config
from podcast_pipeline.models.job import Job
from podcast_pipeline.models.transcript import FillerCut, Segment, TranscriptResult, Word
from podcast_pipeline.stages.base import Stage, StageResult
from podcast_pipeline.utils.ffmpeg import get_video_metadata, run_ffmpeg
from podcast_pipeline.utils.logging import get_logger
from podcast_pipeline.utils.time import seconds_to_srt_timestamp, seconds_to_vtt_timestamp

logger = get_logger(__name__)


class TranscribeStage(Stage):
    """Transcribe audio using faster-whisper with filler detection."""

    name = "transcribe"

    def __init__(self, config: Config):
        super().__init__(config)
        self._model = None

    def _get_model(self) -> WhisperModel:
        """Lazy load the Whisper model."""
        if self._model is None:
            from faster_whisper import WhisperModel

            model_size = self.config.transcription.model
            device = self.config.transcription.device
            compute_type = self.config.transcription.compute_type

            self.logger.info(
                "loading_whisper_model",
                model=model_size,
                device=device,
                compute_type=compute_type,
            )

            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
            )

        return self._model

    def run(self, job: Job, job_dir: Path) -> StageResult:
        """Execute transcription stage.

        Creates:
            - analysis/transcript.json
            - analysis/filler_cuts.json
            - output/transcripts/transcript.txt
            - output/transcripts/transcript.srt
            - output/transcripts/transcript.vtt
        """
        track_count = self._get_audio_track_count(job_dir)
        if track_count > 1:
            self.logger.info("multi_track_detected", tracks=track_count)
            return self.transcribe_multi_track(job, job_dir)

        if track_count > 0:
            self.logger.info("single_track_detected", tracks=track_count)
        else:
            self.logger.info("audio_track_count_unknown", defaulting="single_track")

        return self._run_single_track(job, job_dir)

    def _run_single_track(self, job: Job, job_dir: Path) -> StageResult:
        """Execute single-track transcription."""
        audio_path = job_dir / "intermediate" / "audio.wav"

        if not audio_path.exists():
            return StageResult(
                success=False,
                error=f"Audio file not found: {audio_path}. Run ingest stage first.",
            )

        # Create directories
        analysis_dir = job_dir / "analysis"
        transcripts_dir = job_dir / "output" / "transcripts"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        transcripts_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[str] = []

        try:
            # Load model and transcribe
            model = self._get_model()

            self.logger.info("transcribing", audio=str(audio_path))

            segments_iter, info = model.transcribe(
                str(audio_path),
                word_timestamps=True,
                vad_filter=True,  # Filter out non-speech
                vad_parameters={"min_silence_duration_ms": 500},
            )

            self.logger.info(
                "transcription_info",
                language=info.language,
                language_probability=info.language_probability,
                duration=info.duration,
            )

            # Process segments
            transcript_segments: list[Segment] = []
            all_text_parts: list[str] = []

            for segment in segments_iter:
                words = []
                if segment.words:
                    for word_info in segment.words:
                        words.append(
                            Word(
                                word=word_info.word.strip(),
                                start=word_info.start,
                                end=word_info.end,
                                confidence=word_info.probability,
                            )
                        )

                transcript_segments.append(
                    Segment(
                        start=segment.start,
                        end=segment.end,
                        text=segment.text.strip(),
                        words=words,
                    )
                )
                all_text_parts.append(segment.text.strip())

            full_text = " ".join(all_text_parts)

            # Detect filler words
            filler_cuts = self._detect_fillers(transcript_segments)
            self.logger.info("fillers_detected", count=len(filler_cuts))

            # Create transcript result
            result = TranscriptResult(
                text=full_text,
                segments=transcript_segments,
                filler_cuts=filler_cuts,
                language=info.language,
                duration=info.duration,
            )

            # Save transcript JSON
            transcript_path = analysis_dir / "transcript.json"
            transcript_path.write_text(result.model_dump_json(indent=2))
            outputs.append(str(transcript_path.relative_to(job_dir)))

            # Save filler cuts JSON
            filler_path = analysis_dir / "filler_cuts.json"
            filler_data = [f.model_dump() for f in filler_cuts]
            filler_path.write_text(json.dumps(filler_data, indent=2))
            outputs.append(str(filler_path.relative_to(job_dir)))

            # Export transcript formats
            txt_path = transcripts_dir / "transcript.txt"
            txt_path.write_text(full_text)
            outputs.append(str(txt_path.relative_to(job_dir)))

            srt_path = transcripts_dir / "transcript.srt"
            srt_content = self._generate_srt(transcript_segments)
            srt_path.write_text(srt_content)
            outputs.append(str(srt_path.relative_to(job_dir)))

            vtt_path = transcripts_dir / "transcript.vtt"
            vtt_content = self._generate_vtt(transcript_segments)
            vtt_path.write_text(vtt_content)
            outputs.append(str(vtt_path.relative_to(job_dir)))

            self.logger.info(
                "transcription_complete",
                segments=len(transcript_segments),
                words=sum(len(s.words) for s in transcript_segments),
                filler_cuts=len(filler_cuts),
            )

            return StageResult(
                success=True,
                outputs=outputs,
                data={"transcript": result.model_dump()},
            )

        except ImportError as e:
            return StageResult(
                success=False,
                error=f"faster-whisper not installed: {e}",
            )
        except Exception as e:
            self.logger.exception("transcription_failed")
            return StageResult(
                success=False,
                error=str(e),
                outputs=outputs,
            )

    def _find_input_video(self, job_dir: Path) -> Path | None:
        """Locate the raw input video for the job."""
        input_dir = job_dir / "input"
        for ext in [".mp4", ".mov", ".mkv", ".avi", ".webm"]:
            candidate = input_dir / f"raw{ext}"
            if candidate.exists():
                return candidate
        return None

    def _get_audio_track_count(self, job_dir: Path) -> int:
        """Get audio track count from metadata or fallback detection."""
        metadata_path = job_dir / "intermediate" / "metadata.json"
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text())
                if "audio_track_count" in metadata:
                    return int(metadata["audio_track_count"])
                streams = metadata.get("streams", [])
                return sum(1 for stream in streams if stream.get("codec_type") == "audio")
            except Exception as e:
                self.logger.warning("metadata_track_parse_failed", error=str(e))

        video_path = self._find_input_video(job_dir)
        if not video_path:
            return 0

        return len(self._detect_audio_tracks(video_path))

    def _detect_fillers(self, segments: list[Segment]) -> list[FillerCut]:
        """Detect filler words in transcript."""
        filler_words = {self._normalize_filler_token(w) for w in self.config.fillers.words}
        single_word_fillers = {w for w in filler_words if " " not in w}
        multi_word_fillers = {
            tuple(self._normalize_filler_token(token) for token in w.split())
            for w in filler_words
            if " " in w
        }
        min_confidence = self.config.fillers.min_confidence
        min_duration_ms = self.config.fillers.min_duration_ms
        padding_ms = self.config.fillers.padding_ms

        filler_cuts: list[FillerCut] = []

        for segment in segments:
            words = segment.words
            i = 0
            while i < len(words):
                word = words[i]
                word_text = self._normalize_filler_token(word.word)
                duration_ms = (word.end - word.start) * 1000

                # Check if it's a filler word
                is_filler = word_text in single_word_fillers

                # Also check two-word fillers like "you know"
                if i + 1 < len(words):
                    next_word = words[i + 1]
                    next_text = self._normalize_filler_token(next_word.word)
                    phrase = (word_text, next_text)
                    phrase_duration_ms = (next_word.end - word.start) * 1000
                    phrase_confidence = min(word.confidence, next_word.confidence)

                    if (
                        phrase in multi_word_fillers
                        and phrase_confidence >= min_confidence
                        and phrase_duration_ms >= min_duration_ms
                    ):
                        start = max(0, word.start - padding_ms / 1000)
                        end = next_word.end + padding_ms / 1000
                        filler_cuts.append(
                            FillerCut(
                                start=start,
                                end=end,
                                word=f"{word_text} {next_text}",
                                confidence=phrase_confidence,
                            )
                        )
                        i += 2
                        continue

                if is_filler and word.confidence >= min_confidence:
                    if duration_ms >= min_duration_ms:
                        # Add padding
                        start = max(0, word.start - padding_ms / 1000)
                        end = word.end + padding_ms / 1000

                        filler_cuts.append(
                            FillerCut(
                                start=start,
                                end=end,
                                word=word.word,
                                confidence=word.confidence,
                            )
                        )
                i += 1

        return filler_cuts

    @staticmethod
    def _normalize_filler_token(word: str) -> str:
        """Normalize transcript token text for filler matching."""
        token = word.lower().strip()
        token = re.sub(r"^[^\w']+|[^\w']+$", "", token)
        return token

    def _generate_srt(self, segments: list[Segment]) -> str:
        """Generate SRT subtitle content."""
        lines = []
        for i, segment in enumerate(segments, 1):
            start = seconds_to_srt_timestamp(segment.start)
            end = seconds_to_srt_timestamp(segment.end)
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(segment.text)
            lines.append("")
        return "\n".join(lines)

    def _generate_vtt(self, segments: list[Segment]) -> str:
        """Generate VTT subtitle content."""
        lines = ["WEBVTT", ""]
        for segment in segments:
            start = seconds_to_vtt_timestamp(segment.start)
            end = seconds_to_vtt_timestamp(segment.end)
            lines.append(f"{start} --> {end}")
            lines.append(segment.text)
            lines.append("")
        return "\n".join(lines)

    def _detect_audio_tracks(self, video_path: Path) -> list[dict[str, Any]]:
        """Detect all audio tracks in the video file.

        Args:
            video_path: Path to video file

        Returns:
            List of audio track info dictionaries
        """
        try:
            metadata = get_video_metadata(video_path)
            audio_tracks = []

            for stream in metadata.get("streams", []):
                if stream.get("codec_type") == "audio":
                    audio_tracks.append(
                        {
                            "index": stream.get("index"),
                            "codec_name": stream.get("codec_name"),
                            "sample_rate": stream.get("sample_rate"),
                            "channels": stream.get("channels"),
                            "channel_layout": stream.get("channel_layout", ""),
                        }
                    )

            self.logger.info("audio_tracks_detected", count=len(audio_tracks))
            return audio_tracks

        except Exception as e:
            self.logger.warning("audio_track_detection_failed", error=str(e))
            return []

    def _extract_audio_track(
        self,
        video_path: Path,
        output_path: Path,
        track_index: int = 0,
        sample_rate: int = 16000,
    ) -> Path:
        """Extract a specific audio track from video.

        Args:
            video_path: Path to video file
            output_path: Path for output audio
            track_index: Audio stream index
            sample_rate: Output sample rate

        Returns:
            Path to extracted audio
        """
        args = [
            "-i",
            str(video_path),
            "-map",
            f"0:a:{track_index}",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            "1",
            str(output_path),
        ]

        run_ffmpeg(args)
        return output_path

    def transcribe_multi_track(
        self,
        job: Job,
        job_dir: Path,
    ) -> StageResult:
        """Transcribe multiple audio tracks separately.

        This is useful for podcasts with separate tracks for host/guest.
        Creates per-track transcripts and a merged transcript.

        Args:
            job: Job instance
            job_dir: Job directory path

        Returns:
            Stage result
        """
        # Find input video
        video_path = self._find_input_video(job_dir)

        if not video_path:
            return StageResult(
                success=False,
                error="Input video not found",
            )

        # Detect audio tracks
        tracks = self._detect_audio_tracks(video_path)

        if len(tracks) <= 1:
            # Single track - use standard transcription
            self.logger.info("single_track_detected", falling_back="standard")
            return self._run_single_track(job, job_dir)

        # Create directories
        analysis_dir = job_dir / "analysis"
        intermediate_dir = job_dir / "intermediate"
        transcripts_dir = job_dir / "output" / "transcripts"
        analysis_dir.mkdir(parents=True, exist_ok=True)
        intermediate_dir.mkdir(parents=True, exist_ok=True)
        transcripts_dir.mkdir(parents=True, exist_ok=True)

        outputs: list[str] = []
        all_transcripts: list[TranscriptResult] = []

        try:
            model = self._get_model()

            # Transcribe each track
            for i, track in enumerate(tracks):
                self.logger.info(
                    "transcribing_track",
                    track_index=i,
                    channels=track.get("channels"),
                )

                # Extract track audio
                track_audio = intermediate_dir / f"audio_track_{i}.wav"
                self._extract_audio_track(video_path, track_audio, i)

                # Transcribe track
                segments_iter, info = model.transcribe(
                    str(track_audio),
                    word_timestamps=True,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 500},
                )

                # Process segments
                transcript_segments: list[Segment] = []
                all_text_parts: list[str] = []

                for segment in segments_iter:
                    words = []
                    if segment.words:
                        for word_info in segment.words:
                            words.append(
                                Word(
                                    word=word_info.word.strip(),
                                    start=word_info.start,
                                    end=word_info.end,
                                    confidence=word_info.probability,
                                )
                            )

                    # Add speaker label
                    speaker_label = f"Speaker {i + 1}"

                    transcript_segments.append(
                        Segment(
                            start=segment.start,
                            end=segment.end,
                            text=segment.text.strip(),
                            words=words,
                            speaker=speaker_label,
                        )
                    )
                    all_text_parts.append(f"[{speaker_label}] {segment.text.strip()}")

                full_text = " ".join(all_text_parts)
                filler_cuts = self._detect_fillers(transcript_segments)

                track_result = TranscriptResult(
                    text=full_text,
                    segments=transcript_segments,
                    filler_cuts=filler_cuts,
                    language=info.language,
                    duration=info.duration,
                    speaker=f"Speaker {i + 1}",
                    track_index=i,
                )

                all_transcripts.append(track_result)

                # Save per-track transcript
                track_path = analysis_dir / f"transcript_track_{i}.json"
                track_path.write_text(track_result.model_dump_json(indent=2))
                outputs.append(str(track_path.relative_to(job_dir)))

            # Merge transcripts
            merged = self._merge_transcripts(all_transcripts)

            # Save merged transcript
            transcript_path = analysis_dir / "transcript.json"
            transcript_path.write_text(merged.model_dump_json(indent=2))
            outputs.append(str(transcript_path.relative_to(job_dir)))

            # Save combined filler cuts
            all_fillers = []
            for t in all_transcripts:
                all_fillers.extend(t.filler_cuts)
            all_fillers.sort(key=lambda x: x.start)

            filler_path = analysis_dir / "filler_cuts.json"
            filler_data = [f.model_dump() for f in all_fillers]
            filler_path.write_text(json.dumps(filler_data, indent=2))
            outputs.append(str(filler_path.relative_to(job_dir)))

            # Export transcript formats
            txt_path = transcripts_dir / "transcript.txt"
            txt_path.write_text(merged.text)
            outputs.append(str(txt_path.relative_to(job_dir)))

            srt_path = transcripts_dir / "transcript.srt"
            srt_content = self._generate_srt_with_speakers(merged.segments)
            srt_path.write_text(srt_content)
            outputs.append(str(srt_path.relative_to(job_dir)))

            vtt_path = transcripts_dir / "transcript.vtt"
            vtt_content = self._generate_vtt_with_speakers(merged.segments)
            vtt_path.write_text(vtt_content)
            outputs.append(str(vtt_path.relative_to(job_dir)))

            self.logger.info(
                "multi_track_transcription_complete",
                tracks=len(tracks),
                segments=len(merged.segments),
            )

            return StageResult(
                success=True,
                outputs=outputs,
                data={
                    "tracks": len(tracks),
                    "transcript": merged.model_dump(),
                },
            )

        except Exception as e:
            self.logger.exception("multi_track_transcription_failed")
            return StageResult(
                success=False,
                error=str(e),
                outputs=outputs,
            )

    def _merge_transcripts(
        self,
        transcripts: list[TranscriptResult],
    ) -> TranscriptResult:
        """Merge multiple track transcripts into one.

        Args:
            transcripts: List of per-track transcripts

        Returns:
            Merged transcript with speaker labels
        """
        # Combine all segments
        all_segments: list[Segment] = []
        for t in transcripts:
            all_segments.extend(t.segments)

        # Sort by start time
        all_segments.sort(key=lambda x: x.start)

        # Build merged text
        text_parts = []
        for seg in all_segments:
            speaker = seg.speaker or "Unknown"
            text_parts.append(f"[{speaker}] {seg.text}")

        full_text = " ".join(text_parts)

        # Combine filler cuts
        all_fillers: list[FillerCut] = []
        for t in transcripts:
            all_fillers.extend(t.filler_cuts)
        all_fillers.sort(key=lambda x: x.start)

        # Get language and duration from first transcript
        first = transcripts[0] if transcripts else None

        return TranscriptResult(
            text=full_text,
            segments=all_segments,
            filler_cuts=all_fillers,
            language=first.language if first else "en",
            duration=first.duration if first else 0.0,
            speaker="multiple",
            track_index=-1,  # Indicates merged
        )

    def _generate_srt_with_speakers(self, segments: list[Segment]) -> str:
        """Generate SRT with speaker labels."""
        lines = []
        for i, segment in enumerate(segments, 1):
            start = seconds_to_srt_timestamp(segment.start)
            end = seconds_to_srt_timestamp(segment.end)

            speaker = segment.speaker or ""
            text = f"[{speaker}] {segment.text}" if speaker else segment.text

            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)

    def _generate_vtt_with_speakers(self, segments: list[Segment]) -> str:
        """Generate VTT with speaker labels."""
        lines = ["WEBVTT", ""]
        for segment in segments:
            start = seconds_to_vtt_timestamp(segment.start)
            end = seconds_to_vtt_timestamp(segment.end)

            speaker = segment.speaker or ""
            text = f"[{speaker}] {segment.text}" if speaker else segment.text

            lines.append(f"{start} --> {end}")
            lines.append(text)
            lines.append("")
        return "\n".join(lines)
