"""
Todo Domain Constants
"""
from datetime import datetime, timedelta

# Todo를 식별하는 유닉스 타임스탬프 (917초)
TODO_TIMESTAMP = 917

# Todo의 start_time/end_time에 사용되는 datetime
# 1970-01-01T00:15:17Z (UTC)
TODO_DATETIME = datetime(1970, 1, 1, 0, 15, 17)

# Todo의 end_time에 사용되는 datetime (start_time + TODO_TIMESTAMP 초)
# validation 통과를 위해 start_time보다 큰 값 필요
TODO_DATETIME_END = TODO_DATETIME + timedelta(seconds=TODO_TIMESTAMP)

