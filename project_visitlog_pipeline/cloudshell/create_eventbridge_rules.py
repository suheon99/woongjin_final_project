#!/bin/bash
# =========================================================
# CloudShell Script : 22개의 EventBridge Rule 생성
# ---------------------------------------------------------
# 10월 1일 ~ 22일까지 매일 VisitLog Lambda 실행
# - 3분 간격 순차 실행
# - 주말/공휴일 병합 규칙 반영
# - CloudWatch Logs → S3 Export 가능
# =========================================================

# 🔹 Lambda 설정
LAMBDA_ARN="arn:aws:lambda:ap-northeast-2:180528248114:function:get_visitlogapi"

# 🔹 실행 간격 (3분)
INTERVAL_MIN=3

# 🔹 시작 날짜 (YYYY-MM-DD)
START_DATE="2025-10-01"
END_DATE="2025-10-22"

# 🔹 공휴일 병합 규칙 (병합할 구간 → 실제 실행일)
declare -A MERGE_RULES=(
  ["2025-10-03_to_2025-10-09"]="2025-10-10"
  ["2025-10-10_to_2025-10-12"]="2025-10-13"
  ["2025-10-17_to_2025-10-19"]="2025-10-20"
)

# =========================================================
# 1️⃣ 10월 1일 ~ 22일까지 규칙 자동 생성
# =========================================================
echo "✅ EventBridge 규칙 생성 시작..."

for i in $(seq 1 22); do
  DAY=$(printf "%02d" $i)
  RULE_NAME="run_seq_dau_202510${DAY}_0940"
  TARGET_ID="lambda-target-${DAY}"

  # UTC 변환 (KST 09:40 → UTC 00:40)
  SCHEDULE="cron(40 0 ${DAY} 10 ? 2025)"

  echo "📅 생성 중: $RULE_NAME ($SCHEDULE)"

  # Rule 생성
  aws events put-rule \
    --name "$RULE_NAME" \
    --schedule-expression "$SCHEDULE" \
    --state ENABLED \
    --description "Run sequential DAU (2025-10-${DAY}), 3min interval, holiday merge"

  # Lambda 권한 부여
  aws lambda add-permission \
    --function-name "$LAMBDA_ARN" \
    --statement-id "AllowExec_${DAY}" \
    --action "lambda:InvokeFunction" \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:ap-northeast-2:180528248114:rule/$RULE_NAME" \
    >/dev/null 2>&1

  # Lambda 실행 인자 (기간/간격/병합 규칙)
  INPUT_JSON=$(jq -n \
    --arg start "$START_DATE" \
    --arg end "$END_DATE" \
    --argjson interval "$INTERVAL_MIN" \
    --argjson merge "$(jq -n '{
      "2025-10-03_to_2025-10-09": "2025-10-10",
      "2025-10-10_to_2025-10-12": "2025-10-13",
      "2025-10-17_to_2025-10-19": "2025-10-20"
    }')" \
    '{start_date: $start, end_date: $end, interval_minutes: 3, merge_rules: $merge}')

  # Lambda 타깃 등록
  aws events put-targets \
    --rule "$RULE_NAME" \
    --targets "[{\"Id\":\"$TARGET_ID\",\"Arn\":\"$LAMBDA_ARN\",\"Input\":\"$INPUT_JSON\"}]"
done

echo " 모든 22개 EventBridge 규칙 생성 완료!"
echo "---------------------------------------------------------"
echo " 확인: AWS Console → EventBridge → 규칙 이름(run_seq_dau_...)"
echo "---------------------------------------------------------"


# =========================================================
# 2️⃣ CloudWatch Logs → S3 Export (선택)
# ---------------------------------------------------------
# 22일 동안의 실행 로그를 S3로 백업하려면 아래를 실행
# (S3 버킷은 미리 생성되어 있어야 함)
# =========================================================

LOG_GROUP="/aws/lambda/get_visitlogapi"
EXPORT_BUCKET="project-visitlogapi-logbackup"
EXPORT_PREFIX="eventbridge_logs"

# 예시: 2025년 10월 1일 ~ 22일 로그 내보내기
# START_TIME=$(date -d "2025-10-01T00:00:00Z" +%s)000
# END_TIME=$(date -d "2025-10-22T23:59:59Z" +%s)000
# TASK_NAME="export_oct_1_22"

# aws logs create-export-task \
#   --task-name "$TASK_NAME" \
#   --log-group-name "$LOG_GROUP" \
#   --from "$START_TIME" \
#   --to "$END_TIME" \
#   --destination "$EXPORT_BUCKET" \
#   --destination-prefix "$EXPORT_PREFIX"

# echo " CloudWatch Logs → S3 Export 작업 제출 완료!"
