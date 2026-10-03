"""
pairwise-rhythm-system - RhythmSystem

This module contains a deliberately broken implementation.
Fix all bugs so that tests pass.
"""


class RhythmSystem:
    def __init__(self):
        self.state = {}

    def calculate_judgment(self, *args, **kwargs):
        """BUG: 判定不做时间窗口，按早按晚都算Miss"""
        return None

    def sync_chart(self, *args, **kwargs):
        """BUG: 谱面同步不做延迟校准，不同设备判定不一样"""
        return None

    def update_notes(self, *args, **kwargs):
        """BUG: 音符不做类型，长按和单点一样"""
        return None

    def calculate_score(self, *args, **kwargs):
        """BUG: 评分不做权重，Perfect和Good分一样"""
        return None

    def show_result(self, *args, **kwargs):
        """BUG: 结算不做评级，只有分数没有S/A/B"""
        return None

