"""게스트 가져오기의 가능 시간 합치기 (app/domain/meeting/service.py merge_time_slots)

- 같은 종류의 구간은 합집합이다. 겹치거나 맞닿은 구간은 하나가 된다
- 게스트 구간이 회원의 다른 종류 구간과 겹치면 회원의 답을 두고 게스트 구간에서 그 부분을 뺀다
- 어느 쪽도 답하지 않은 시간은 채우지 않는다
- 슬롯 수 제한은 보지 않는다
"""
from datetime import datetime

import pytest

from app.domain.meeting.schema.dto import TimeSlotCreate, subtract_intervals
from app.domain.meeting.service import merge_time_slots
from app.models.meeting import TimeSlotKind

AV, UN = TimeSlotKind.AVAILABLE, TimeSlotKind.UNAVAILABLE


def _at(day: int, hhmm: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    if hour == 24:
        return datetime(2099, 3, day + 1)
    return datetime(2099, 3, day, hour, minute)


def _s(day: int, start: str, end: str, kind=AV) -> TimeSlotCreate:
    return TimeSlotCreate(start_time=_at(day, start), end_time=_at(day, end), kind=kind)


def _answer(slots) -> list[tuple]:
    return [(slot.start_time, slot.end_time, slot.kind) for slot in slots]


class TestSameKind:
    def test_overlapping_and_touching_become_one(self):
        member = [_s(2, "09:00", "09:30"), _s(2, "10:30", "11:00")]
        guest = [_s(2, "09:15", "10:00"), _s(2, "10:00", "10:30")]

        assert _answer(merge_time_slots(member, guest)) == [(_at(2, "09:00"), _at(2, "11:00"), AV)]

    def test_disjoint_are_kept_apart_in_start_order(self):
        member = [_s(3, "09:00", "10:00")]
        guest = [_s(2, "10:00", "11:00"), _s(4, "09:00", "09:30")]

        assert _answer(merge_time_slots(member, guest)) == [
            (_at(2, "10:00"), _at(2, "11:00"), AV),
            (_at(3, "09:00"), _at(3, "10:00"), AV),
            (_at(4, "09:00"), _at(4, "09:30"), AV),
        ]

    def test_duplicates_collapse(self):
        slot = _s(2, "09:00", "10:00")

        assert _answer(merge_time_slots([slot, slot], [slot])) == [(_at(2, "09:00"), _at(2, "10:00"), AV)]

    def test_unavailable_union(self):
        member = [_s(2, "09:00", "10:00", UN), _s(2, "10:00", "11:00")]
        guest = [_s(2, "09:00", "11:00", UN), _s(3, "09:00", "11:00", UN)]

        assert _answer(merge_time_slots(member, guest)) == [
            (_at(2, "09:00"), _at(2, "10:00"), UN),
            (_at(2, "10:00"), _at(2, "11:00"), AV),
            (_at(3, "09:00"), _at(3, "11:00"), UN),
        ]

    @pytest.mark.parametrize("side", ["member", "guest"])
    def test_one_side_empty(self, side):
        slots = [_s(2, "09:00", "10:00"), _s(2, "09:30", "11:00"), _s(3, "09:00", "11:00", UN)]
        member, guest = (slots, []) if side == "member" else ([], slots)

        assert _answer(merge_time_slots(member, guest)) == [
            (_at(2, "09:00"), _at(2, "11:00"), AV),
            (_at(3, "09:00"), _at(3, "11:00"), UN),
        ]

    def test_both_empty(self):
        assert merge_time_slots([], []) == []


class TestOtherKind:
    def test_guest_available_is_trimmed_by_member_unavailable(self):
        member = [_s(2, "09:00", "10:00", UN), _s(2, "10:00", "11:00")]
        guest = [_s(2, "09:00", "11:00")]

        assert _answer(merge_time_slots(member, guest)) == [
            (_at(2, "09:00"), _at(2, "10:00"), UN),
            (_at(2, "10:00"), _at(2, "11:00"), AV),
        ]

    def test_guest_unavailable_is_trimmed_by_member_available(self):
        member = [_s(2, "09:00", "10:00")]
        guest = [_s(2, "09:00", "11:00", UN)]

        assert _answer(merge_time_slots(member, guest)) == [
            (_at(2, "09:00"), _at(2, "10:00"), AV),
            (_at(2, "10:00"), _at(2, "11:00"), UN),
        ]

    def test_guest_interval_is_split_around_member_interval(self):
        member = [_s(2, "09:00", "09:30"), _s(2, "09:30", "10:00", UN), _s(2, "10:00", "11:00")]
        guest = [_s(2, "08:00", "12:00")]

        assert _answer(merge_time_slots(member, guest)) == [
            (_at(2, "08:00"), _at(2, "09:30"), AV),
            (_at(2, "09:30"), _at(2, "10:00"), UN),
            (_at(2, "10:00"), _at(2, "12:00"), AV),
        ]

    def test_guest_interval_fully_inside_member_other_kind_disappears(self):
        member = [_s(2, "09:00", "11:00", UN)]
        guest = [_s(2, "09:30", "10:30")]

        assert _answer(merge_time_slots(member, guest)) == [(_at(2, "09:00"), _at(2, "11:00"), UN)]

    def test_touching_other_kind_is_kept(self):
        member = [_s(2, "09:00", "10:00", UN), _s(2, "10:00", "11:00")]
        guest = [_s(2, "11:00", "12:00", UN)]

        assert _answer(merge_time_slots(member, guest)) == [
            (_at(2, "09:00"), _at(2, "10:00"), UN),
            (_at(2, "10:00"), _at(2, "11:00"), AV),
            (_at(2, "11:00"), _at(2, "12:00"), UN),
        ]


class TestNothingIsFilled:
    """합친 답은 두 답뿐이다. 어느 쪽도 답하지 않은 시간은 어느 종류로도 채우지 않는다"""

    def test_partial_answers_keep_their_gaps(self):
        member = [_s(2, "09:00", "09:30", UN), _s(3, "10:00", "10:30")]
        guest = [_s(2, "10:30", "11:00", UN), _s(4, "09:00", "09:30")]

        assert _answer(merge_time_slots(member, guest)) == [
            (_at(2, "09:00"), _at(2, "09:30"), UN),
            (_at(2, "10:30"), _at(2, "11:00"), UN),
            (_at(3, "10:00"), _at(3, "10:30"), AV),
            (_at(4, "09:00"), _at(4, "09:30"), AV),
        ]

    def test_whole_day_answers_leave_other_days_unanswered(self):
        member = [_s(2, "00:00", "24:00", UN)]
        guest = [_s(4, "00:00", "24:00")]

        assert _answer(merge_time_slots(member, guest)) == [
            (_at(2, "00:00"), _at(3, "00:00"), UN),
            (_at(4, "00:00"), _at(5, "00:00"), AV),
        ]


def test_slot_count_is_not_limited():
    member = [_s(day, f"09:{m:02d}", f"09:{m + 5:02d}") for day in (2, 3, 4) for m in (0, 20, 40)]
    guest = [_s(day, f"10:{m:02d}", f"10:{m + 5:02d}") for day in (2, 3, 4) for m in (0, 20, 40)]

    assert len(merge_time_slots(member, guest)) == 18


class TestSubtractIntervals:
    def test_cuts_split_and_trim(self):
        intervals = [(_at(2, "09:00"), _at(2, "12:00")), (_at(3, "09:00"), _at(3, "10:00"))]
        cuts = [(_at(2, "10:30"), _at(2, "11:00")), (_at(2, "08:00"), _at(2, "09:30")), (_at(3, "09:30"), _at(3, "11:00"))]

        assert subtract_intervals(intervals, cuts) == [
            (_at(2, "09:30"), _at(2, "10:30")),
            (_at(2, "11:00"), _at(2, "12:00")),
            (_at(3, "09:00"), _at(3, "09:30")),
        ]

    def test_touching_cut_removes_nothing(self):
        interval = (_at(2, "09:00"), _at(2, "10:00"))

        assert subtract_intervals([interval], [(_at(2, "10:00"), _at(2, "11:00"))]) == [interval]

    def test_covering_cut_removes_everything(self):
        assert subtract_intervals([(_at(2, "09:00"), _at(2, "10:00"))], [(_at(2, "08:00"), _at(2, "10:00"))]) == []
