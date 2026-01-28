"""
라우트 중복 검증 테스트

모든 API 라우터에서 동일한 경로와 메서드를 가진 중복 라우트가 없는지 검증합니다.
FastAPI는 첫 번째 매칭되는 라우트만 실행하므로, 중복 라우트가 있으면
두 번째 이후의 라우트는 도달 불가능한 데드 코드가 됩니다.
"""
from collections import defaultdict
from typing import List, Tuple

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute

from app.main import app


def get_all_routes(application: FastAPI) -> List[Tuple[str, str, str]]:
    """
    앱의 모든 라우트를 (method, path, endpoint_name) 튜플 리스트로 반환
    """
    routes = []
    for route in application.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                routes.append((method, route.path, route.endpoint.__name__))
    return routes


def find_duplicate_routes(application: FastAPI) -> List[dict]:
    """
    중복된 라우트(동일 method + path)를 찾아서 반환
    
    Returns:
        List of dicts with:
        - method: HTTP 메서드
        - path: 라우트 경로
        - endpoints: 중복된 엔드포인트 이름 리스트
    """
    route_map = defaultdict(list)

    for route in application.routes:
        if isinstance(route, APIRoute):
            for method in route.methods:
                key = (method, route.path)
                route_map[key].append(route.endpoint.__name__)

    duplicates = []
    for (method, path), endpoints in route_map.items():
        if len(endpoints) > 1:
            duplicates.append({
                "method": method,
                "path": path,
                "endpoints": endpoints,
            })

    return duplicates


class TestNoDuplicateRoutes:
    """라우트 중복 없음 검증 테스트"""

    def test_no_duplicate_routes_in_app(self):
        """
        전체 앱에서 중복 라우트가 없어야 함
        
        중복 라우트가 있으면 FastAPI는 첫 번째 매칭되는 라우트만 실행하고
        나머지는 도달 불가능한 데드 코드가 됩니다.
        """
        duplicates = find_duplicate_routes(app)

        if duplicates:
            error_messages = []
            for dup in duplicates:
                error_messages.append(
                    f"  - {dup['method']} {dup['path']}: "
                    f"endpoints = {dup['endpoints']}"
                )

            pytest.fail(
                f"중복된 라우트가 발견되었습니다:\n" +
                "\n".join(error_messages) +
                "\n\n첫 번째 라우트만 실행되고 나머지는 도달 불가능합니다."
            )

    def test_timers_routes_unique(self):
        """타이머 라우터의 라우트가 고유해야 함"""
        timer_routes = [
            (method, path, name)
            for method, path, name in get_all_routes(app)
            if "/timers" in path
        ]

        # 경로별 엔드포인트 그룹화
        route_map = defaultdict(list)
        for method, path, name in timer_routes:
            route_map[(method, path)].append(name)

        # 중복 확인
        for (method, path), names in route_map.items():
            assert len(names) == 1, (
                f"타이머 라우트 중복: {method} {path} has {len(names)} handlers: {names}"
            )

    def test_schedules_routes_unique(self):
        """스케줄 라우터의 라우트가 고유해야 함"""
        schedule_routes = [
            (method, path, name)
            for method, path, name in get_all_routes(app)
            if "/schedules" in path
        ]

        route_map = defaultdict(list)
        for method, path, name in schedule_routes:
            route_map[(method, path)].append(name)

        for (method, path), names in route_map.items():
            assert len(names) == 1, (
                f"스케줄 라우트 중복: {method} {path} has {len(names)} handlers: {names}"
            )

    def test_todos_routes_unique(self):
        """Todo 라우터의 라우트가 고유해야 함"""
        todo_routes = [
            (method, path, name)
            for method, path, name in get_all_routes(app)
            if "/todos" in path
        ]

        route_map = defaultdict(list)
        for method, path, name in todo_routes:
            route_map[(method, path)].append(name)

        for (method, path), names in route_map.items():
            assert len(names) == 1, (
                f"Todo 라우트 중복: {method} {path} has {len(names)} handlers: {names}"
            )

    def test_tags_routes_unique(self):
        """태그 라우터의 라우트가 고유해야 함"""
        tag_routes = [
            (method, path, name)
            for method, path, name in get_all_routes(app)
            if "/tags" in path
        ]

        route_map = defaultdict(list)
        for method, path, name in tag_routes:
            route_map[(method, path)].append(name)

        for (method, path), names in route_map.items():
            assert len(names) == 1, (
                f"태그 라우트 중복: {method} {path} has {len(names)} handlers: {names}"
            )

    def test_friends_routes_unique(self):
        """친구 라우터의 라우트가 고유해야 함"""
        friend_routes = [
            (method, path, name)
            for method, path, name in get_all_routes(app)
            if "/friends" in path
        ]

        route_map = defaultdict(list)
        for method, path, name in friend_routes:
            route_map[(method, path)].append(name)

        for (method, path), names in route_map.items():
            assert len(names) == 1, (
                f"친구 라우트 중복: {method} {path} has {len(names)} handlers: {names}"
            )

    def test_all_routes_have_unique_method_path_combination(self):
        """
        모든 라우트가 고유한 (method, path) 조합을 가져야 함
        
        이 테스트는 새로운 라우터가 추가되더라도 자동으로 검증합니다.
        """
        all_routes = get_all_routes(app)

        route_map = defaultdict(list)
        for method, path, name in all_routes:
            route_map[(method, path)].append(name)

        duplicates = [
            (method, path, names)
            for (method, path), names in route_map.items()
            if len(names) > 1
        ]

        assert len(duplicates) == 0, (
            f"중복 라우트 발견: {duplicates}\n"
            "각 (method, path) 조합은 하나의 엔드포인트만 가져야 합니다."
        )


class TestRouteConfiguration:
    """라우트 설정 검증 테스트"""

    def test_expected_timer_routes_exist(self):
        """필수 타이머 라우트가 모두 존재해야 함
        
        [WebSocket 전환 - 2026-01-28]
        타이머 생성/일시정지/재개/종료는 WebSocket으로 이동됨:
        - WebSocket 엔드포인트: /ws/timers
        - REST API는 조회/업데이트/삭제만 지원
        """
        timer_routes = {
            (method, path)
            for method, path, _ in get_all_routes(app)
            if "/timers" in path
        }

        # REST API 라우트 (조회/업데이트/삭제)
        expected_routes = [
            ("GET", "/v1/timers"),
            ("GET", "/v1/timers/active"),
            ("GET", "/v1/timers/{timer_id}"),
            ("PATCH", "/v1/timers/{timer_id}"),
            ("DELETE", "/v1/timers/{timer_id}"),
            # Schedule 연관 타이머 조회
            ("GET", "/v1/schedules/{schedule_id}/timers"),
            ("GET", "/v1/schedules/{schedule_id}/timers/active"),
            # Todo 연관 타이머 조회
            ("GET", "/v1/todos/{todo_id}/timers"),
            ("GET", "/v1/todos/{todo_id}/timers/active"),
        ]

        # WebSocket으로 이동된 라우트 (더 이상 REST API에 없음):
        # - POST /v1/timers (타이머 생성)
        # - PATCH /v1/timers/{timer_id}/pause (일시정지)
        # - PATCH /v1/timers/{timer_id}/resume (재개)
        # - POST /v1/timers/{timer_id}/stop (종료)

        for method, path in expected_routes:
            assert (method, path) in timer_routes, (
                f"필수 타이머 라우트 누락: {method} {path}"
            )

    def test_expected_schedule_routes_exist(self):
        """필수 스케줄 라우트가 모두 존재해야 함"""
        schedule_routes = {
            (method, path)
            for method, path, _ in get_all_routes(app)
            if "/schedules" in path
        }

        expected_routes = [
            ("POST", "/v1/schedules"),
            ("GET", "/v1/schedules"),
            ("GET", "/v1/schedules/{schedule_id}"),
            ("PATCH", "/v1/schedules/{schedule_id}"),
            ("DELETE", "/v1/schedules/{schedule_id}"),
        ]

        for method, path in expected_routes:
            assert (method, path) in schedule_routes, (
                f"필수 스케줄 라우트 누락: {method} {path}"
            )

    def test_expected_todo_routes_exist(self):
        """필수 Todo 라우트가 모두 존재해야 함"""
        todo_routes = {
            (method, path)
            for method, path, _ in get_all_routes(app)
            if "/todos" in path
        }

        expected_routes = [
            ("POST", "/v1/todos"),
            ("GET", "/v1/todos"),
            ("GET", "/v1/todos/{todo_id}"),
            ("PATCH", "/v1/todos/{todo_id}"),
            ("DELETE", "/v1/todos/{todo_id}"),
        ]

        for method, path in expected_routes:
            assert (method, path) in todo_routes, (
                f"필수 Todo 라우트 누락: {method} {path}"
            )
