"""
=========================================================
📦 AWS Lambda: VisitLog 데이터 자동 수집 파이프라인
---------------------------------------------------------
- VisitLog API 호출 → DAU 계산 → S3 업로드 → Slack 알림
- 평일: 전날 데이터 / 월요일: 주말(2일치) / 주말: skip
- 완전 서버리스 구조 (EventBridge + Lambda + S3 + Slack)
=========================================================
"""

import json
import boto3
import urllib.request
import urllib.error
import os
from datetime import datetime, timedelta


# =========================================================
# 1️⃣ 환경 변수 설정
# ---------------------------------------------------------
# 민감한 키값들은 Lambda 콘솔의 "환경 변수" 탭에서 관리:
#   - S3_BUCKET_NAME
#   - SLACK_WEBHOOK_URL
#   - VISITLOG_API_KEY
# =========================================================

VISITLOG_API_URL = "https://dataplore.net/api/visitlogs/"
API_KEY = os.environ["VISITLOG_API_KEY"]
SLACK_URL = os.environ["SLACK_WEBHOOK_URL"]
BUCKET_NAME = os.environ["S3_BUCKET_NAME"]

s3 = boto3.client("s3")


# =========================================================
# 2️⃣ VisitLog API 호출
# ---------------------------------------------------------
# 특정 날짜(date_str)의 전체 방문 로그를 페이지 단위로 수집
# 페이지네이션(pagination) 자동 처리
# =========================================================
def get_visitlog(date_str: str):
    url = f"{VISITLOG_API_URL}?date={date_str}&limit=1000"
    headers = {"X-API-Key": API_KEY}
    all_data = []

    while url:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                results = payload.get("results", [])
                all_data.extend(results)
                print(f"[DEBUG] {date_str}: {len(results)}건 수집 (누적 {len(all_data)})")
                url = payload.get("next")  # 다음 페이지 URL
        except urllib.error.HTTPError as e:
            raise Exception(f"HTTPError {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise Exception(f"URLError: {e.reason}")

    return all_data


# =========================================================
# 3️⃣ S3 업로드
# ---------------------------------------------------------
# 수집된 VisitLog 데이터를 날짜별 JSON 파일로 저장
# 예: s3://<bucket>/visitlog/date=2025-10-05/visitlog_2025-10-05.json
# =========================================================
def upload_to_s3(date_str, data):
    key = f"visitlog/date={date_str}/visitlog_{date_str}.json"
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(data, ensure_ascii=False),
        ContentType="application/json",
    )
    return f"s3://{BUCKET_NAME}/{key}"


# =========================================================
# 4️⃣ Slack 알림
# ---------------------------------------------------------
# Slack Webhook을 이용해 수집 결과 / 에러 상태를 알림으로 전송
# =========================================================
def send_slack(message: str):
    payload = {"text": message}
    req = urllib.request.Request(
        SLACK_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except urllib.error.URLError as e:
        print(f"[WARN] Slack 전송 실패: {e.reason}")


# =========================================================
# 5️⃣ Lambda 메인 핸들러
# ---------------------------------------------------------
# 실행 스케줄 (EventBridge 기반)
#  - 화~금: 전날 데이터 수집
#  - 월요일: 토·일 2일치 병합 수집
#  - 주말: skip
# =========================================================
def lambda_handler(event, context):
    today = datetime.now()
    weekday = today.weekday()  # 0=월, 6=일

    # 🔹 테스트용 target_date 직접 지정 가능
    if "target_date" in event:
        target_dates = [event["target_date"]]
    else:
        if weekday in [1, 2, 3, 4]:  # 화~금
            target_dates = [(today - timedelta(days=1)).strftime("%Y-%m-%d")]
        elif weekday == 0:  # 월요일
            target_dates = [
                (today - timedelta(days=2)).strftime("%Y-%m-%d"),  # 토요일
                (today - timedelta(days=1)).strftime("%Y-%m-%d"),  # 일요일
            ]
        else:
            send_slack("⏸ 주말은 데이터 수집을 건너뜁니다.")
            return {"status": "skipped", "date": today.strftime("%Y-%m-%d")}

    results = []
    for date_str in target_dates:
        # 수집 기간 제한 (10/01~10/22)
        if not ("2025-10-01" <= date_str <= "2025-10-22"):
            send_slack(f"⏸ {date_str}: 대상 기간(10/1~10/22) 아님.")
            continue

        try:
            data = get_visitlog(date_str)
            s3_path = upload_to_s3(date_str, data)
            count = len(data)

            send_slack(
                f"✅ VisitLog {date_str} 수집 완료\n"
                f"총 {count:,}건\n"
                f"S3 저장 경로: {s3_path}"
            )
            results.append({"date": date_str, "count": count})
        except Exception as e:
            send_slack(f"❌ {date_str} 수집 실패\n에러: {str(e)}")

    return {"status": "done", "results": results}


# =========================================================
# 6️⃣ Lambda 함수 권한 설정
# ---------------------------------------------------------
# Lambda 콘솔 → [구성] → [권한] → [실행 역할] → [인라인 정책 추가]
# 아래 IAM 정책(JSON) 추가:
#
# {
#   "Version": "2012-10-17",
#   "Statement": [
#     {
#       "Effect": "Allow",
#       "Action": ["s3:PutObject", "s3:PutObjectAcl"],
#       "Resource": "arn:aws:s3:::your-bucket-name/visitlog/*"
#     }
#   ]
# }
# =========================================================
