#!/bin/bash

# Python 버전 호환성 테스트 스크립트
# 사용법: ./scripts/test-python-versions.sh [버전...]
#
# 예시:
#   ./scripts/test-python-versions.sh              # 모든 버전 테스트
#   ./scripts/test-python-versions.sh 3.12 3.13    # 특정 버전만 테스트

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 기본 테스트 버전
DEFAULT_VERSIONS=("3.15" "3.14" "3.13" "3.12" "3.11")

# 인자가 있으면 해당 버전만, 없으면 기본 버전 모두 테스트
if [ $# -gt 0 ]; then
    VERSIONS=("$@")
else
    VERSIONS=("${DEFAULT_VERSIONS[@]}")
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║          Python Version Compatibility Test Suite           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Testing versions: ${YELLOW}${VERSIONS[*]}${NC}"
echo ""

# 결과 저장 배열
declare -A RESULTS

# 각 버전 테스트
for VERSION in "${VERSIONS[@]}"; do
    SERVICE_NAME="python${VERSION//./}"
    
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Testing Python ${VERSION}...${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    # Docker Compose로 테스트 실행
    if docker compose -f docker-compose.python-matrix.yaml up --build --abort-on-container-exit "$SERVICE_NAME" 2>&1; then
        RESULTS[$VERSION]="PASS"
        echo -e "${GREEN}✅ Python ${VERSION}: PASSED${NC}"
    else
        RESULTS[$VERSION]="FAIL"
        echo -e "${RED}❌ Python ${VERSION}: FAILED${NC}"
    fi
    
    # 컨테이너 정리
    docker compose -f docker-compose.python-matrix.yaml down --volumes --remove-orphans 2>/dev/null || true
    
    echo ""
done

# 최종 결과 요약
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                      Test Summary                          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

PASS_COUNT=0
FAIL_COUNT=0

for VERSION in "${VERSIONS[@]}"; do
    RESULT=${RESULTS[$VERSION]}
    if [ "$RESULT" == "PASS" ]; then
        echo -e "  Python ${VERSION}: ${GREEN}✅ PASSED${NC}"
        ((PASS_COUNT++))
    else
        echo -e "  Python ${VERSION}: ${RED}❌ FAILED${NC}"
        ((FAIL_COUNT++))
    fi
done

echo ""
echo -e "${BLUE}────────────────────────────────────────────────────────────${NC}"
echo -e "  Total: ${GREEN}${PASS_COUNT} passed${NC}, ${RED}${FAIL_COUNT} failed${NC}"
echo -e "${BLUE}────────────────────────────────────────────────────────────${NC}"
echo ""

# 이미지 정리 (선택사항)
read -p "Clean up Docker images? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "Cleaning up..."
    docker compose -f docker-compose.python-matrix.yaml down --volumes --rmi local 2>/dev/null || true
    echo "Done."
fi

# 실패가 있으면 exit code 1
if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
fi
