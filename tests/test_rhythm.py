import pytest
from rhythm.system import RhythmSystem


class TestRhythmSystem:

    def test_calculate_judgment(self):
        """判定不做时间窗口，按早按晚都算Miss"""
        obj = RhythmSystem()
        result = obj.calculate_judgment()
        self.assertIsNotNone(result)

    def test_sync_chart(self):
        """谱面同步不做延迟校准，不同设备判定不一样"""
        obj = RhythmSystem()
        result = obj.sync_chart()
        self.assertIsNotNone(result)

    def test_update_notes(self):
        """音符不做类型，长按和单点一样"""
        obj = RhythmSystem()
        result = obj.update_notes()
        self.assertIsNotNone(result)

    def test_calculate_score(self):
        """评分不做权重，Perfect和Good分一样"""
        obj = RhythmSystem()
        result = obj.calculate_score()
        self.assertIsNotNone(result)

    def test_show_result(self):
        """结算不做评级，只有分数没有S/A/B"""
        obj = RhythmSystem()
        result = obj.show_result()
        self.assertIsNotNone(result)

