"""
pairwise-rhythm-system - RhythmSystem

Rhythm-game engine core providing:

- calculate_judgment: timing-window judgment levels (Perfect/Great/Good/Bad/Miss)
  with live combo, max-combo and combo-break reporting.
- sync_chart: chart synchronisation driven by audio position, with device
  latency calibration and pause/resume support.
- update_notes: typed notes (tap / hold / slide), swipe-required slides and
  per-lane chord (double-press) matching.
- calculate_score: weighted scoring, combo bonus and accuracy.
- show_result: S/A/B/C/D rating, max combo and a replay of the run.
"""

import time


class RhythmSystem:
    # Timing windows in seconds (|hit_time - note_time - latency_offset|).
    JUDGMENT_WINDOWS = {
        "Perfect": 0.050,
        "Great": 0.100,
        "Good": 0.150,
        "Bad": 0.200,
    }
    JUDGMENTS = ("Perfect", "Great", "Good", "Bad", "Miss")

    # Accuracy weight for each judgment level.
    JUDGMENT_WEIGHTS = {
        "Perfect": 1.0,
        "Great": 0.8,
        "Good": 0.5,
        "Bad": 0.2,
        "Miss": 0.0,
    }

    # Base points for each judgment level.
    BASE_SCORE = {
        "Perfect": 300,
        "Great": 200,
        "Good": 100,
        "Bad": 50,
        "Miss": 0,
    }

    NOTE_TYPES = ("tap", "hold", "slide")

    # +1% score per combo step, capped at +100%.
    COMBO_BONUS_RATE = 0.01
    COMBO_BONUS_CAP = 100

    # Rating thresholds by accuracy percent.
    RATINGS = (
        (95.0, "S"),
        (90.0, "A"),
        (80.0, "B"),
        (70.0, "C"),
        (0.0, "D"),
    )

    def __init__(self, latency_offset=0.0):
        self.state = {}
        self.latency_offset = float(latency_offset)
        self.combo = 0
        self.max_combo = 0
        self.judgment_counts = {name: 0 for name in self.JUDGMENTS}
        self.judgment_history = []
        self.replay = []
        self.paused = False
        self._audio_position = 0.0
        self._last_clock = time.monotonic()

    def reset(self):
        """Reset all gameplay state (calibration is kept)."""
        self.state = {}
        self.combo = 0
        self.max_combo = 0
        self.judgment_counts = {name: 0 for name in self.JUDGMENTS}
        self.judgment_history = []
        self.replay = []
        self.paused = False
        self._audio_position = 0.0
        self._last_clock = time.monotonic()

    # ------------------------------------------------------------------
    # Judgment: timing windows + judgment levels + combo
    # ------------------------------------------------------------------
    def calculate_judgment(self, time_diff=0.0, *, note_time=None, hit_time=None):
        """Judge a hit by timing window and update combo.

        ``time_diff`` is the raw hit-vs-note offset in seconds. It may instead
        be derived from ``note_time``/``hit_time``; in that case the calibrated
        device latency is removed so every device judges consistently.
        """
        if note_time is not None and hit_time is not None:
            time_diff = (hit_time - self.latency_offset) - note_time

        abs_diff = abs(float(time_diff))
        judgment = "Miss"
        for level, window in self.JUDGMENT_WINDOWS.items():
            if abs_diff <= window:
                judgment = level
                break

        combo_broken = False
        lost_combo = 0
        if judgment == "Miss":
            combo_broken = self.combo > 0
            lost_combo = self.combo
            self.combo = 0
        else:
            self.combo += 1
            if self.combo > self.max_combo:
                self.max_combo = self.combo

        self.judgment_counts[judgment] += 1
        result = {
            "judgment": judgment,
            "time_diff": float(time_diff),
            "combo": self.combo,
            "max_combo": self.max_combo,
            "combo_broken": combo_broken,
            "lost_combo": lost_combo,
        }
        self.judgment_history.append(result)
        self._record_event("judgment", result)
        return result

    # ------------------------------------------------------------------
    # Chart sync: latency calibration + audio position + pause
    # ------------------------------------------------------------------
    def calibrate_latency(self, offset):
        """Store the device input/output latency offset in seconds."""
        self.latency_offset = float(offset)
        return self.latency_offset

    def _advance_audio(self, audio_position=None, dt=None):
        """Advance audio time. Time freezes while paused."""
        now = time.monotonic()
        if not self.paused:
            if audio_position is not None:
                self._audio_position = float(audio_position)
            elif dt is not None:
                self._audio_position += float(dt)
            else:
                self._audio_position += now - self._last_clock
        self._last_clock = now
        return self._audio_position

    def get_audio_position(self, audio_position=None):
        """Current audio position in seconds (frozen while paused)."""
        return self._advance_audio(audio_position)

    def pause(self):
        """Pause chart/audio playback; sync position stops advancing."""
        self._advance_audio()
        self.paused = True
        return self.paused

    def resume(self):
        """Resume chart/audio playback."""
        self.paused = False
        self._last_clock = time.monotonic()
        return self.paused

    def sync_chart(self, chart=None, *, audio_position=None, latency_offset=None,
                   dt=None):
        """Synchronise chart notes to the audio position.

        - latency calibration: a stored offset shifts the chart so hits are
          judged at the same moment on every device.
        - audio position: synchronisation is driven by the real audio clock
          (``audio_position``) instead of a free-running timer.
        - pause: while paused the audio position and chart do not move.
        """
        if latency_offset is not None:
            self.calibrate_latency(latency_offset)

        position = self._advance_audio(audio_position, dt)
        chart_position = position - self.latency_offset

        synced_notes = []
        for note in chart or []:
            note_time = float(note.get("time", 0.0))
            synced = dict(note)
            synced["time_until_hit"] = note_time - chart_position
            synced_notes.append(synced)

        return {
            "position": chart_position,
            "audio_position": position,
            "latency_offset": self.latency_offset,
            "paused": self.paused,
            "notes": synced_notes,
        }

    # ------------------------------------------------------------------
    # Notes: types + slide + double press (chords)
    # ------------------------------------------------------------------
    def _find_input(self, inputs, used, lane, target_time, input_types,
                    direction=None, window=None):
        """Find an unused matching input (per lane, so chords each count)."""
        if window is None:
            window = self.JUDGMENT_WINDOWS["Bad"]
        for index, entry in enumerate(inputs):
            if index in used:
                continue
            if entry.get("lane", 0) != lane:
                continue
            if entry.get("type", "press") not in input_types:
                continue
            if abs(float(entry.get("time", target_time)) - target_time) > window:
                continue
            if direction is not None and entry.get("direction") != direction:
                continue
            return index
        return None

    def _judge_note(self, note, input_index, inputs, target_time):
        used_diff = (
            float(inputs[input_index].get("time", target_time)) - target_time
        )
        judgment = self.calculate_judgment(
            used_diff - self.latency_offset
        )
        return judgment["judgment"]

    def _update_hold(self, note, inputs, used, current_time):
        lane = note.get("lane", 0)
        start = float(note.get("time", 0.0))
        duration = float(note.get("duration", 0.0))
        end = start + duration
        holds = self.state.setdefault("holds", {})
        key = note.get("id", (lane, start, duration))
        state = holds.setdefault(key, {"started": False, "released": False})

        if not state["started"]:
            press = self._find_input(inputs, used, lane, start, {"press"})
            if press is not None:
                used.add(press)
                state["started"] = True

        if state["started"] and not state["released"]:
            release = self._find_input(inputs, used, lane, end, {"release"})
            if release is not None:
                used.add(release)
                state["released"] = True

        if state["started"] and state["released"]:
            holds.pop(key, None)
            return {"state": "hit", "judgment": "Perfect"}
        if state["started"]:
            return {"state": "holding", "judgment": None}
        if current_time is not None and current_time - start > self.JUDGMENT_WINDOWS["Bad"]:
            holds.pop(key, None)
            return {"state": "miss", "judgment": "Miss"}
        return {"state": "pending", "judgment": None}

    def _update_note(self, note, inputs, used, current_time):
        note_type = note.get("type", "tap")
        lane = note.get("lane", 0)
        target_time = float(note.get("time", 0.0))

        if note_type == "hold":
            outcome = self._update_hold(note, inputs, used, current_time)
        elif note_type == "slide":
            # Slides need a swipe in the right direction; a plain press fails.
            match = self._find_input(
                inputs, used, lane, target_time, {"swipe"},
                direction=note.get("direction"),
            )
            if match is not None:
                used.add(match)
                outcome = {
                    "state": "hit",
                    "judgment": self._judge_note(note, match, inputs, target_time),
                }
            elif current_time is not None and current_time - target_time > self.JUDGMENT_WINDOWS["Bad"]:
                outcome = {"state": "miss", "judgment": "Miss"}
            else:
                outcome = {"state": "pending", "judgment": None}
        else:
            match = self._find_input(
                inputs, used, lane, target_time, {"press"}
            )
            if match is not None:
                used.add(match)
                outcome = {
                    "state": "hit",
                    "judgment": self._judge_note(note, match, inputs, target_time),
                }
            elif current_time is not None and current_time - target_time > self.JUDGMENT_WINDOWS["Bad"]:
                outcome = {"state": "miss", "judgment": "Miss"}
            else:
                outcome = {"state": "pending", "judgment": None}

        result = {
            "id": note.get("id"),
            "type": note_type,
            "lane": lane,
            "time": target_time,
            "state": outcome["state"],
            "judgment": outcome["judgment"],
        }
        self._record_event("note", result)
        return result

    def update_notes(self, notes=None, inputs=None, *, current_time=None):
        """Update typed notes against player inputs.

        - tap: a press inside the timing window.
        - hold: a press at the start plus a release after ``duration``.
        - slide: a swipe input in the note's required direction.
        - double press: matching is per input/per lane, so two simultaneous
          notes both register.
        """
        notes = notes or []
        inputs = inputs or []
        used = set()
        results = []
        for note in notes:
            results.append(self._update_note(note, inputs, used, current_time))
        return results

    # ------------------------------------------------------------------
    # Score: weights + combo bonus + accuracy
    # ------------------------------------------------------------------
    @staticmethod
    def _counts_from_sequence(sequence):
        counts = {name: 0 for name in RhythmSystem.JUDGMENTS}
        for judgment in sequence:
            if judgment in counts:
                counts[judgment] += 1
        return counts

    def calculate_score(self, judgments=None):
        """Calculate weighted score, combo bonus and accuracy.

        Accepts a sequence of judgments, a counts mapping, or nothing (uses the
        judgments accumulated by this run).
        """
        max_combo = 0
        if judgments is None:
            sequence = [entry["judgment"] for entry in self.judgment_history]
            counts = dict(self.judgment_counts)
            max_combo = self.max_combo
        elif isinstance(judgments, dict):
            counts = {name: int(judgments.get(name, 0)) for name in self.JUDGMENTS}
            sequence = [
                judgment
                for judgment, count in counts.items()
                for _ in range(count)
            ]
        else:
            sequence = list(judgments)
            counts = self._counts_from_sequence(sequence)

        score = 0.0
        combo_bonus_total = 0.0
        combo = 0
        for judgment in sequence:
            base = self.BASE_SCORE.get(judgment, 0)
            if judgment == "Miss":
                combo = 0
                continue
            combo += 1
            if combo > max_combo:
                max_combo = combo
            multiplier = 1.0 + self.COMBO_BONUS_RATE * min(
                combo, self.COMBO_BONUS_CAP
            )
            gained = base * multiplier
            score += gained
            combo_bonus_total += gained - base

        total = sum(counts.values())
        if total:
            weighted = sum(
                self.JUDGMENT_WEIGHTS[level] * counts[level]
                for level in self.JUDGMENTS
            )
            accuracy = weighted / total * 100.0
        else:
            accuracy = 0.0

        return {
            "score": int(round(score)),
            "accuracy": round(accuracy, 2),
            "combo_bonus": int(round(combo_bonus_total)),
            "max_combo": max_combo,
            "counts": counts,
        }

    # ------------------------------------------------------------------
    # Result: rating + max combo + replay
    # ------------------------------------------------------------------
    def rate(self, accuracy):
        """Map an accuracy percent to an S/A/B/C/D rating."""
        for threshold, rating in self.RATINGS:
            if accuracy >= threshold:
                return rating
        return "D"

    def _record_event(self, event_type, data):
        self.replay.append({
            "audio_position": self._audio_position,
            "type": event_type,
            "data": data,
        })

    def get_replay(self):
        """Return the recorded replay of judgments and note updates."""
        return list(self.replay)

    def show_result(self, judgments=None):
        """Build the result screen: score, rating, max combo and replay."""
        score_info = self.calculate_score(judgments)
        max_combo = max(self.max_combo, score_info["max_combo"])
        result = {
            "score": score_info["score"],
            "accuracy": score_info["accuracy"],
            "rating": self.rate(score_info["accuracy"]),
            "max_combo": max_combo,
            "combo_bonus": score_info["combo_bonus"],
            "counts": score_info["counts"],
            "replay": self.get_replay(),
        }
        self._record_event("result", {
            "score": result["score"],
            "rating": result["rating"],
            "max_combo": max_combo,
        })
        return result
