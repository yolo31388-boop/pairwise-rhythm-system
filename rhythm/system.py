"""RhythmSystem - 音乐节奏游戏核心系统。

包含判定、谱面同步、音符更新、评分与结算。
"""

import time


class RhythmSystem:
    # 判定时间窗口（秒）：|命中时间差| 落在窗口内即获得对应评级
    JUDGMENT_WINDOWS = {
        "perfect": 0.045,
        "great": 0.090,
        "good": 0.135,
    }
    # 各判定等级的分数权重
    SCORE_WEIGHTS = {
        "perfect": 1.0,
        "great": 0.65,
        "good": 0.3,
        "miss": 0.0,
    }
    BASE_NOTE_SCORE = 100
    # 每达到该连击数的倍数，连击加成提升一档
    COMBO_BONUS_STEP = 10
    COMBO_BONUS_RATE = 0.05
    MAX_COMBO_BONUS = 0.5
    # 结算评级阈值（按准确率）
    GRADE_THRESHOLDS = [
        (0.95, "S"),
        (0.85, "A"),
        (0.70, "B"),
        (0.0, "C"),
    ]
    NOTE_TYPES = ("tap", "hold", "slide", "double")

    def __init__(self):
        self.state = {}
        # 判定 / 连击状态
        self.combo = 0
        self.max_combo = 0
        self.judgment_history = []
        # 回放：记录每一次判定事件
        self.replay = []
        # 谱面同步状态
        self.latency_offset = 0.0
        self.audio_position = 0.0
        self.paused = False
        self.chart = []
        self._last_sync_monotonic = None

    # ------------------------------------------------------------------
    # 判定
    # ------------------------------------------------------------------
    def calculate_judgment(self, note_time=0.0, hit_time=None, input_offset=None):
        """根据时间窗口计算判定等级，并维护连击。

        返回 dict：judgment / time_diff / combo / max_combo / combo_broken。
        """
        offset = self.latency_offset if input_offset is None else input_offset

        if hit_time is None:
            judgment = "miss"
            time_diff = None
        else:
            time_diff = (hit_time - offset) - note_time
            abs_diff = abs(time_diff)
            judgment = "miss"
            for grade, window in self.JUDGMENT_WINDOWS.items():
                if abs_diff <= window:
                    judgment = grade
                    break

        combo_broken = False
        if judgment == "miss":
            combo_broken = self.combo > 0
            self.combo = 0
        else:
            self.combo += 1
            self.max_combo = max(self.max_combo, self.combo)

        event = {
            "judgment": judgment,
            "note_time": note_time,
            "hit_time": hit_time,
            "time_diff": time_diff,
            "combo": self.combo,
            "combo_broken": combo_broken,
        }
        self.judgment_history.append(judgment)
        self.replay.append(event)

        return {
            "judgment": judgment,
            "time_diff": time_diff,
            "combo": self.combo,
            "max_combo": self.max_combo,
            "combo_broken": combo_broken,
        }

    # ------------------------------------------------------------------
    # 谱面同步
    # ------------------------------------------------------------------
    def sync_chart(self, chart=None, latency=None, audio_position=None,
                   paused=None, dt=None):
        """同步谱面：延迟校准 + 以音频位置为时钟 + 暂停支持。

        - latency: 设备输入/输出延迟（秒），用于校准判定与谱面。
        - audio_position: 音频实际播放位置（秒），优先于内部计时器。
        - paused: 暂停时谱面与音频位置停止推进。
        """
        if latency is not None:
            self.latency_offset = float(latency)
        if paused is not None:
            self.paused = bool(paused)
        if chart is not None:
            self.chart = list(chart)

        if audio_position is not None:
            # 以音频时钟为准，不用计时器
            self.audio_position = float(audio_position)
            self._last_sync_monotonic = time.monotonic()
        elif not self.paused:
            advance = 0.0
            if dt is not None:
                advance = float(dt)
            elif self._last_sync_monotonic is not None:
                now = time.monotonic()
                advance = now - self._last_sync_monotonic
                self._last_sync_monotonic = now
            self.audio_position += advance
        # 暂停时：audio_position 保持不变，谱面不再前进

        synced_notes = []
        for note in self.chart:
            note = dict(note)
            note_time = note.get("time", 0.0)
            # 延迟校准：把谱面时间平移到本设备的判定时间轴上
            note["calibrated_time"] = note_time + self.latency_offset
            note["visible"] = note["calibrated_time"] >= self.audio_position
            synced_notes.append(note)

        return {
            "audio_position": self.audio_position,
            "latency_offset": self.latency_offset,
            "paused": self.paused,
            "notes": synced_notes,
        }

    # ------------------------------------------------------------------
    # 音符更新
    # ------------------------------------------------------------------
    def update_notes(self, notes=None, inputs=None, dt=None):
        """按音符类型处理输入：tap / hold / slide / double（双押）。

        notes:  [{type, time, duration?, direction?, keys?}, ...]
        inputs: [{key, time, release_time?, direction?}, ...]
        返回每个音符的判定结果列表。
        """
        if dt is not None and not self.paused:
            self.audio_position += float(dt)
        notes = notes or []
        inputs = list(inputs or [])
        used_inputs = set()
        results = []

        def take_input(pred):
            for idx, inp in enumerate(inputs):
                if idx in used_inputs:
                    continue
                if pred(inp):
                    used_inputs.add(idx)
                    return inp
            return None

        for note in notes:
            note_type = note.get("type", "tap")
            if note_type not in self.NOTE_TYPES:
                note_type = "tap"
            note_time = note.get("time", 0.0)
            window = self.JUDGMENT_WINDOWS["good"]

            if note_type == "double":
                # 双押：两个键必须同时按下，各自独立判定
                keys = note.get("keys") or [None, None]
                sub_results = []
                for key in keys[:2]:
                    inp = take_input(
                        lambda i, k=key: (k is None or i.get("key") == k)
                        and abs(i.get("time", 0.0) - note_time) <= window
                    )
                    sub_results.append(self.calculate_judgment(
                        note_time, None if inp is None else inp.get("time")))
                results.append({
                    "type": "double",
                    "note": note,
                    "judgments": [r["judgment"] for r in sub_results],
                    "hits": sum(1 for r in sub_results
                                if r["judgment"] != "miss"),
                })
                continue

            inp = take_input(
                lambda i: abs(i.get("time", 0.0) - note_time) <= window)

            if note_type == "hold":
                # 长按：按下后需保持到 duration 结束
                duration = note.get("duration", 0.0)
                held = (
                    inp is not None
                    and inp.get("release_time", inp.get("time", 0.0))
                    >= note_time + duration - window
                )
                result = self.calculate_judgment(
                    note_time, inp.get("time") if held else None)
                result["type"] = "hold"
                result["held_duration"] = (
                    max(0.0, inp.get("release_time", inp.get("time", 0.0))
                        - note_time) if inp is not None else 0.0)
            elif note_type == "slide":
                # 滑动：按下且滑动方向匹配才算命中
                direction = note.get("direction")
                slid = (
                    inp is not None
                    and (direction is None
                         or inp.get("direction") == direction)
                )
                result = self.calculate_judgment(
                    note_time, inp.get("time") if slid else None)
                result["type"] = "slide"
                result["direction"] = direction
            else:  # tap
                result = self.calculate_judgment(
                    note_time, None if inp is None else inp.get("time"))
                result["type"] = "tap"

            result["note"] = note
            results.append(result)

        return {
            "audio_position": self.audio_position,
            "results": results,
            "combo": self.combo,
            "max_combo": self.max_combo,
        }

    # ------------------------------------------------------------------
    # 评分
    # ------------------------------------------------------------------
    def calculate_score(self, judgments=None):
        """按权重计分 + 连击加成 + 准确率。

        judgments: 判定等级列表（默认使用历史判定）。
        """
        judgments = list(judgments) if judgments is not None else list(
            self.judgment_history)

        score = 0.0
        combo = 0
        max_combo = 0
        weighted_sum = 0.0
        counts = {grade: 0 for grade in self.SCORE_WEIGHTS}

        for judgment in judgments:
            if isinstance(judgment, dict):
                judgment = judgment.get("judgment", "miss")
            weight = self.SCORE_WEIGHTS.get(judgment, 0.0)
            counts[judgment] = counts.get(judgment, 0) + 1
            weighted_sum += weight

            if judgment == "miss":
                combo = 0
            else:
                combo += 1
                max_combo = max(max_combo, combo)

            combo_bonus = min(
                self.MAX_COMBO_BONUS,
                (combo // self.COMBO_BONUS_STEP) * self.COMBO_BONUS_RATE,
            )
            score += self.BASE_NOTE_SCORE * weight * (1.0 + combo_bonus)

        total = len(judgments)
        accuracy = weighted_sum / total if total else 0.0

        self.max_combo = max(self.max_combo, max_combo)
        return {
            "score": int(round(score)),
            "accuracy": accuracy,
            "max_combo": max_combo,
            "counts": counts,
        }

    # ------------------------------------------------------------------
    # 结算
    # ------------------------------------------------------------------
    def show_result(self, judgments=None):
        """结算：评级（S/A/B/C）+ 最大连击 + 回放数据。"""
        stats = self.calculate_score(judgments)

        grade = "C"
        for threshold, name in self.GRADE_THRESHOLDS:
            if stats["accuracy"] >= threshold:
                grade = name
                break

        return {
            "score": stats["score"],
            "grade": grade,
            "accuracy": stats["accuracy"],
            "max_combo": max(self.max_combo, stats["max_combo"]),
            "counts": stats["counts"],
            "replay": list(self.replay),
        }
