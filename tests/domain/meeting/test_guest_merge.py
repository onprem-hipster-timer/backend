"""게스트 가져오기의 가능 시간 합치기 (app/domain/meeting/service.py merge_time_slots)

- 같은 종류의 구간은 합집합이다. 겹치거나 맞닿은 구간은 하나가 된다
- 게스트 구간이 회원의 다른 종류 구간과 겹치면 회원의 답을 두고 게스트 구간에서 그 부분을 뺀다
- 합친 답은 겹침 규칙과 하루 범위 규칙을 지킨다. 하루 범위를 채워야 하는 날의 빈 시간은 unavailable로 채운다
- 슬롯 수 제한은 보지 않는다
"""
from datetime import date, datetime, time

import pytest

from app.domain.meeting.schema.dto import TimeSlotCreate, _validate_kinds_do_not_overlap, subtract_intervals
from app.domain.meeting.service import _first_uncovered_day, merge_time_slots
from app.models.meeting import Meeting, MeetingMode, TimeSlotKind

AV, UN = TimeSlotKind.AVAILABLE, TimeSlotKind.UNAVAILABLE


def _meeting(mode=MeetingMode.HOURLY, start=time(9), end=time(11), days=(2, 4), excluded=()) -> Meeting:
    return Meeting(
        owner_id="owner",
        title="t",
        start_date=date(2099, 3, days[0]),
        end_date=date(2099, 3, days[1]),
        excluded_dates=[date(2099, 3, d) for d in excluded],
        timezone="UTC",
        mode=mode,
        start_time=start,
        end_time=end,
        time_slot_minutes=60,
    )


def _at(day: int, hhmm: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    if hour == 24:
        return datetime(2099, 3, day + 1)
    return datetime(2099, 3, day, hour, minute)


def _s(day: int, start: str, end: str, kind=AV, end_day: int | None = None) -> TimeSlotCreate:
    return TimeSlotCreate(start_time=_at(day, start), end_time=_at(end_day or day, end), kind=kind)


def _answer(slots) -> list[tuple]:
    return [(slot.start_time, slot.end_time, slot.kind) for slot in slots]


def _valid(meeting: Meeting, slots) -> bool:
    _validate_kinds_do_not_overlap(slots)
    return _first_uncovered_day(meeting, slots) is None


class TestSameKind:
    def test_overlapping_and_touching_become_one(self):
        meeting = _meeting()
        member = [_s(2, "09:00", "09:30"), _s(2, "10:30", "11:00")]
        guest = [_s(2, "09:15", "10:00"), _s(2, "10:00", "10:30")]

        assert _answer(merge_time_slots(meeting, member, guest)) == [(_at(2, "09:00"), _at(2, "11:00"), AV)]

    def test_disjoint_are_kept_apart_in_start_order(self):
        meeting = _meeting()
        member = [_s(3, "09:00", "10:00")]
        guest = [_s(2, "10:00", "11:00"), _s(4, "09:00", "09:30")]

        assert _answer(merge_time_slots(meeting, member, guest)) == [
            (_at(2, "10:00"), _at(2, "11:00"), AV),
            (_at(3, "09:00"), _at(3, "10:00"), AV),
            (_at(4, "09:00"), _at(4, "09:30"), AV),
        ]

    def test_duplicates_collapse(self):
        meeting = _meeting()
        slot = _s(2, "09:00", "10:00")

        assert _answer(merge_time_slots(meeting, [slot, slot], [slot])) == [(_at(2, "09:00"), _at(2, "10:00"), AV)]

    def test_unavailable_union(self):
        meeting = _meeting()
        member = [_s(2, "09:00", "10:00", UN), _s(2, "10:00", "11:00")]
        guest = [_s(2, "09:00", "11:00", UN), _s(3, "09:00", "11:00", UN)]

        assert _answer(merge_time_slots(meeting, member, guest)) == [
            (_at(2, "09:00"), _at(2, "10:00"), UN),
            (_at(2, "10:00"), _at(2, "11:00"), AV),
            (_at(3, "09:00"), _at(3, "11:00"), UN),
        ]

    @pytest.mark.parametrize("side", ["member", "guest"])
    def test_one_side_empty(self, side):
        meeting = _meeting()
        slots = [_s(2, "09:00", "10:00"), _s(2, "09:30", "11:00"), _s(3, "09:00", "11:00", UN)]
        member, guest = (slots, []) if side == "member" else ([], slots)

        assert _answer(merge_time_slots(meeting, member, guest)) == [
            (_at(2, "09:00"), _at(2, "11:00"), AV),
            (_at(3, "09:00"), _at(3, "11:00"), UN),
        ]

    def test_both_empty(self):
        assert merge_time_slots(_meeting(), [], []) == []


class TestOtherKind:
    def test_guest_available_is_trimmed_by_member_unavailable(self):
        meeting = _meeting()
        member = [_s(2, "09:00", "10:00", UN), _s(2, "10:00", "11:00")]
        guest = [_s(2, "09:00", "11:00")]

        assert _answer(merge_time_slots(meeting, member, guest)) == [
            (_at(2, "09:00"), _at(2, "10:00"), UN),
            (_at(2, "10:00"), _at(2, "11:00"), AV),
        ]

    def test_guest_unavailable_is_trimmed_by_member_available(self):
        meeting = _meeting()
        member = [_s(2, "09:00", "10:00")]
        guest = [_s(2, "09:00", "11:00", UN)]

        assert _answer(merge_time_slots(meeting, member, guest)) == [
            (_at(2, "09:00"), _at(2, "10:00"), AV),
            (_at(2, "10:00"), _at(2, "11:00"), UN),
        ]

    def test_guest_interval_is_split_around_member_interval(self):
        meeting = _meeting()
        member = [_s(2, "09:00", "09:30"), _s(2, "09:30", "10:00", UN), _s(2, "10:00", "11:00")]
        guest = [_s(2, "08:00", "12:00")]

        assert _answer(merge_time_slots(meeting, member, guest)) == [
            (_at(2, "08:00"), _at(2, "09:30"), AV),
            (_at(2, "09:30"), _at(2, "10:00"), UN),
            (_at(2, "10:00"), _at(2, "12:00"), AV),
        ]

    def test_guest_interval_fully_inside_member_other_kind_disappears(self):
        meeting = _meeting()
        member = [_s(2, "09:00", "11:00", UN)]
        guest = [_s(2, "09:30", "10:30")]

        assert _answer(merge_time_slots(meeting, member, guest)) == [(_at(2, "09:00"), _at(2, "11:00"), UN)]

    def test_touching_other_kind_is_kept(self):
        meeting = _meeting()
        member = [_s(2, "09:00", "10:00", UN), _s(2, "10:00", "11:00")]
        guest = [_s(2, "11:00", "12:00", UN)]

        assert _answer(merge_time_slots(meeting, member, guest)) == [
            (_at(2, "09:00"), _at(2, "10:00"), UN),
            (_at(2, "10:00"), _at(2, "11:00"), AV),
            (_at(2, "11:00"), _at(2, "12:00"), UN),
        ]


class TestDayCoverage:
    """두 답이 저장할 때의 규칙을 지켰으면 합친 답도 지킨다. 저장 뒤 미팅이 바뀌어 규칙을 어기게 된 답은 빈 시간을 채운다"""

    @pytest.mark.parametrize("member, guest", [
        # hourly: 날마다 따로 본다
        ([_s(2, "09:00", "10:00")], [_s(2, "09:00", "11:00", UN)]),
        ([_s(2, "09:00", "10:00", UN), _s(2, "10:00", "11:00")], [_s(2, "09:00", "11:00"), _s(3, "09:00", "10:00")]),
        ([_s(3, "09:00", "11:00", UN)], [_s(2, "09:30", "10:00"), _s(3, "10:00", "11:00")]),
        ([_s(2, "09:00", "10:00", UN), _s(2, "10:00", "11:00")], [_s(2, "09:00", "10:30", UN), _s(2, "10:30", "11:00")]),
    ])
    def test_hourly_answers_that_follow_the_rule_stay_valid_without_fill(self, member, guest):
        meeting = _meeting()

        merged = merge_time_slots(meeting, member, guest)

        assert _valid(meeting, merged)
        assert _covered(merged) == _covered(member + guest)

    @pytest.mark.parametrize("member, guest", [
        # daily: 답 전체로 본다 (2099-03-02~04, 하루 전체)
        ([_s(2, "00:00", "24:00", UN), _s(3, "00:00", "24:00", end_day=4)],
         [_s(2, "00:00", "24:00"), _s(3, "00:00", "24:00"), _s(4, "00:00", "24:00", UN)]),
        ([_s(3, "00:00", "24:00")],
         [_s(2, "00:00", "24:00"), _s(3, "00:00", "24:00"), _s(4, "00:00", "24:00", UN)]),
        ([_s(3, "00:00", "24:00")], [_s(2, "00:00", "24:00", UN, end_day=4), _s(4, "00:00", "24:00", UN)]),
    ])
    def test_daily_answers_that_follow_the_rule_stay_valid_without_fill(self, member, guest):
        meeting = _meeting(MeetingMode.DAILY, time(0), time(0))

        merged = merge_time_slots(meeting, member, guest)

        assert _valid(meeting, merged)
        assert _covered(merged) == _covered(member + guest)

    def test_hourly_day_left_uncovered_is_filled_with_unavailable(self):
        """회원은 하루 범위가 09–11일 때 답했고, 범위가 09–12로 늘었다"""
        meeting = _meeting(end=time(12))
        member = [_s(2, "09:00", "10:00", UN), _s(2, "10:00", "11:00")]
        guest = [_s(3, "09:00", "10:00")]

        merged = merge_time_slots(meeting, member, guest)

        assert _answer(merged) == [
            (_at(2, "09:00"), _at(2, "10:00"), UN),
            (_at(2, "10:00"), _at(2, "11:00"), AV),
            (_at(2, "11:00"), _at(2, "12:00"), UN),
            (_at(3, "09:00"), _at(3, "10:00"), AV),
        ]
        assert _valid(meeting, merged)

    def test_hourly_fill_comes_from_the_guest_side_too(self):
        """게스트가 범위가 늘기 전에 답했고 회원은 다른 날에 답했다"""
        meeting = _meeting(start=time(8))
        member = [_s(3, "09:00", "10:00")]
        guest = [_s(2, "09:00", "11:00", UN)]

        merged = merge_time_slots(meeting, member, guest)

        assert _answer(merged) == [
            (_at(2, "08:00"), _at(2, "11:00"), UN),
            (_at(3, "09:00"), _at(3, "10:00"), AV),
        ]
        assert _valid(meeting, merged)

    def test_daily_every_day_left_uncovered_is_filled_with_unavailable(self):
        """회원은 hourly일 때 첫날만 불가능으로 답했고, 미팅이 daily로 바뀌었다"""
        meeting = _meeting(MeetingMode.DAILY, time(0), time(0))
        member = [_s(2, "00:00", "24:00", UN)]
        guest = [_s(3, "00:00", "24:00")]

        merged = merge_time_slots(meeting, member, guest)

        assert _answer(merged) == [
            (_at(2, "00:00"), _at(3, "00:00"), UN),
            (_at(3, "00:00"), _at(4, "00:00"), AV),
            (_at(4, "00:00"), _at(5, "00:00"), UN),
        ]
        assert _valid(meeting, merged)

    def test_weekly_is_judged_like_daily(self):
        meeting = _meeting(MeetingMode.WEEKLY, time(0), time(0), days=(2, 8))
        member = [_s(2, "00:00", "24:00", UN)]
        guest = []

        merged = merge_time_slots(meeting, member, guest)

        assert _answer(merged) == [(_at(2, "00:00"), _at(9, "00:00"), UN)]
        assert _valid(meeting, merged)

    def test_available_only_answers_are_not_filled(self):
        meeting = _meeting()
        member = [_s(2, "09:00", "09:30")]
        guest = [_s(3, "10:00", "10:30")]

        assert _answer(merge_time_slots(meeting, member, guest)) == [
            (_at(2, "09:00"), _at(2, "09:30"), AV),
            (_at(3, "10:00"), _at(3, "10:30"), AV),
        ]

    def test_excluded_dates_and_outside_ranges_are_not_filled(self):
        meeting = _meeting(days=(2, 4), excluded=(3,))
        member = [_s(2, "09:00", "11:00", UN), _s(3, "09:00", "09:30", UN), _s(2, "20:00", "21:00", UN)]

        merged = merge_time_slots(meeting, member, [])

        assert _answer(merged) == [
            (_at(2, "09:00"), _at(2, "11:00"), UN),
            (_at(2, "20:00"), _at(2, "21:00"), UN),
            (_at(3, "09:00"), _at(3, "09:30"), UN),
        ]
        assert _valid(meeting, merged)


def test_slot_count_is_not_limited():
    meeting = _meeting()  # 칸 6개
    member = [_s(day, f"09:{m:02d}", f"09:{m + 5:02d}") for day in (2, 3, 4) for m in (0, 20, 40)]
    guest = [_s(day, f"10:{m:02d}", f"10:{m + 5:02d}") for day in (2, 3, 4) for m in (0, 20, 40)]

    assert len(merge_time_slots(meeting, member, guest)) == 18


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


def _covered(slots) -> set:
    """구간이 덮는 분(minute) 단위 시각들"""
    from datetime import timedelta

    minutes = set()
    for slot in slots:
        current = slot.start_time
        while current < slot.end_time:
            minutes.add(current)
            current += timedelta(minutes=1)
    return minutes
