# AWS 서버리스 파이프라인으로 VisitLog 데이터 자동 수집 시스템 구축하기

##  프로젝트 개요
이 프로젝트는 **VisitLog API**에서 방문 데이터를 자동으로 수집하고,  
**DAU(Daily Active Users)** 를 계산한 후 **S3**에 저장하며,  
결과를 **Slack**으로 알림받는 완전 자동화된 **서버리스 파이프라인**입니다.

### 주요 특징
- **완전 서버리스 아키텍처**: Lambda 기반, 서버 관리 불필요  
- **스마트 스케줄링**: 평일/주말/공휴일 구분 실행  
- **실시간 모니터링**: Slack Webhook 알림  
- **안정적인 저장**: 날짜별 JSON 파일을 S3에 자동 적재  

---

##  시스템 아키텍처
전체 파이프라인은 아래와 같은 AWS 서비스로 구성됩니다.

| 구성 요소 | 역할 |
|------------|------|
| **Amazon S3** | 수집된 VisitLog 데이터를 날짜별 JSON으로 저장 |
| **AWS Lambda** | VisitLog API 호출 → DAU 계산 → S3 업로드 → Slack 전송 |
| **EventBridge Scheduler** | 평일/주말 구분, 날짜별 자동 실행 관리 |
| **CloudWatch Logs** | Lambda 실행 결과 및 에러 로그 저장 |
| **Slack Webhook** | 수집 결과를 실시간 알림으로 전송 |

S3 경로 구조 예시:  
`s3://project-visitlogapi/visitlog/date=YYYY-MM-DD/visitlog_YYYY-MM-DD.json`

---

##  Lambda 핵심 코드 요약
```python
def lambda_handler(event, context):
    today = datetime.now()
    weekday = today.weekday()

    if "target_date" in event:
        target_dates = [event["target_date"]]
    elif weekday in [1,2,3,4]:
        target_dates = [(today - timedelta(days=1)).strftime("%Y-%m-%d")]
    elif weekday == 0:
        target_dates = [
            (today - timedelta(days=2)).strftime("%Y-%m-%d"),
            (today - timedelta(days=1)).strftime("%Y-%m-%d"),
        ]
    else:
        send_slack("⏸ 주말은 데이터 수집을 건너뜁니다.")
        return

    for date_str in target_dates:
        data = get_visitlog(date_str)
        s3_path = upload_to_s3(date_str, data)
        send_slack(f"✅ {date_str} 수집 완료 ({len(data):,}건)\n{s3_path}")
```

**핵심 기능**
- 평일: 전날 데이터 수집  
- 월요일: 주말(2일치) 일괄 수집  
- 10/1~10/22 기간만 처리  
- 수집 완료 및 실패 모두 Slack 알림  

---

##  배포 및 운영

###  Lambda 함수 생성 및 환경 변수 설정

Lambda 콘솔에서 함수 생성 후,  
아래와 같이 **환경 변수(Environment Variables)** 를 등록합니다.

| 키 | 설명 |
|----|------|
| `S3_BUCKET_NAME` | 수집 데이터를 저장할 S3 버킷명 |
| `SLACK_WEBHOOK_URL` | Slack Webhook URL |
| `VISITLOG_API_KEY` | VisitLog API 인증 키 |

**권한 설정**  
- Lambda 상단 메뉴 → [구성] → [권한] → [실행 역할] → 인라인 정책 추가  
- 아래 JSON 정책을 붙여넣습니다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:PutObjectAcl"],
      "Resource": "arn:aws:s3:::your-bucket-name/visitlog/*"
    }
  ]
}
```

---

###  CloudShell에서 EventBridge 스케줄 생성

아래 스크립트는 **10월 1일~22일 기간** 동안  
3분 간격으로 순차 실행되도록 **EventBridge 규칙**을 생성합니다.

```bash
# 환경 변수 설정
LAMBDA_ARN="arn:aws:lambda:ap-northeast-2:180528248114:function:get_visitlogapi"
RULE_NAME="run_seq_dau_20251028_0940"
TARGET_ID="lambda-target-0940"

# UTC 00:40 = KST 09:40
SCHEDULE="cron(40 0 28 10 ? 2025)"

# EventBridge 규칙 생성
aws events put-rule \
  --name "$RULE_NAME" \
  --schedule-expression "$SCHEDULE" \
  --state ENABLED \
  --description "Run sequential DAU (Oct 1–22) 3min interval"

# Lambda 실행 권한 부여
aws lambda add-permission \
  --function-name "$LAMBDA_ARN" \
  --statement-id "AllowExecutionFromEventBridgeOnce0940" \
  --action "lambda:InvokeFunction" \
  --principal events.amazonaws.com \
  --source-arn "arn:aws:events:ap-northeast-2:180528248114:rule/$RULE_NAME"

# Lambda 실행 인자 설정 (주말 및 공휴일 병합 규칙 포함)
aws events put-targets \
  --rule "$RULE_NAME" \
  --targets '[{"Id":"'"$TARGET_ID"'","Arn":"'"$LAMBDA_ARN"'","Input":"{\"start_date\": \"2025-10-01\", \"end_date\": \"2025-10-22\", \"interval_minutes\": 3, \"merge_rules\": {\"2025-10-03_to_2025-10-09\": \"2025-10-10\", \"2025-10-10_to_2025-10-12\": \"2025-10-13\", \"2025-10-17_to_2025-10-19\": \"2025-10-20\"}}"}]'
```

**핵심 포인트**
- 3분 간격 순차 실행으로 API 부하 방지  
- 공휴일 데이터는 평일에 병합 수집  
- 모든 규칙은 `EventBridge 콘솔`에서 확인 가능  

---

###  Slack 알림으로 결과 수신

Lambda 실행이 완료되면 Slack으로 자동 알림이 전송됩니다.

```
✅ VisitLog 2025-10-10 수집 완료
총 3,842건
S3 저장 경로: s3://project-visitlogapi/visitlog/date=2025-10-10/visitlog_2025-10-10.json
```

실패 시:
```
❌ VisitLog 2025-10-11 수집 실패
에러: HTTPError 403: Forbidden
```

| 항목 | 설명 |
|------|------|
| ✅ / ❌ | 성공 여부 |
| 날짜 | 수집 대상 일자 |
| 총 건수 | VisitLog API 수집 데이터 수 |
| S3 경로 | 업로드 완료된 파일 위치 |


**Slack 설정 주의**
- Webhook URL이 올바른지 확인  
- Lambda 환경 변수에 정확히 등록  
- Slack 앱에 `Incoming Webhooks` 권한 필요  

---

###  CloudWatch 로그 확인

- **로그 그룹명:** `/aws/lambda/get_visitlogapi`  
- 각 실행 결과의 상세 로그 및 Slack 응답 메시지 확인 가능  
- `"DEBUG"` 로그를 통해 API 페이지별 수집 상태 추적 가능  

---

## 💡 시스템 장점
1. **완전 서버리스 구조**  
   서버 관리 없이 운영 가능, 사용량 기반 과금  
2. **스마트 스케줄링**  
   평일/주말/공휴일 구분 실행 + 부하 제어  
3. **실시간 모니터링**  
   Slack으로 즉각적인 알림 수신  
4. **안정적인 데이터 관리**  
   S3 파티셔닝 구조로 효율적 접근  
5. **확장성 높은 설계**  
   다른 API 또는 데이터 소스 추가 용이  

---

## 📊 예상 비용 (월 기준)
| 항목 | 비용(USD) |
|------|------------|
| AWS Lambda | 0.10 |
| Amazon S3 | 0.01 |
| EventBridge | 0.01 |
| CloudWatch Logs | 0.05 |
| **총합** | **약 $0.20 (≈ 270원)** |

---

## 🎯 결론
✅ 서버 관리 없는 자동화 파이프라인 구축  
✅ 실시간 Slack 모니터링으로 즉각적인 대응  
✅ 일자별 S3 저장 구조로 데이터 신뢰성 확보  
✅ 낮은 운영 비용 대비 높은 확장성 확보  

이 시스템은 AWS 서버리스 생태계를 활용한  
**데이터 자동화 파이프라인의 대표적인 구축 사례**입니다.

---

## 📚 참고 자료
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)  
- [Amazon EventBridge Scheduler](https://docs.aws.amazon.com/eventbridge/latest/userguide/scheduler.html)  
- [Amazon S3 Developer Guide](https://docs.aws.amazon.com/AmazonS3/latest/dev/Welcome.html)  
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)

---

**태그:** `#AWS` `#Lambda` `#Serverless` `#S3` `#EventBridge` `#Slack` `#Automation` `#DataPipeline`
