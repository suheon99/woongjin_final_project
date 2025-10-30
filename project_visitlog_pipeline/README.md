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

##  실행 및 스케줄링
- **EventBridge Scheduler**를 통해 날짜별 Lambda 호출 자동화  
- **3분 간격 순차 실행**으로 API 부하 제어  
- **공휴일 병합 규칙** 설정으로 비효율적인 실행 최소화  
- **CloudWatch Logs**에서 각 실행 결과 모니터링 가능  

---

##  시스템 장점
1. **완전 서버리스 구조**  
   서버 관리 없이 운영 가능, 사용량 기반 과금  
2. **스마트 스케줄링**  
   평일/주말/공휴일 구분 실행 + 부하 조절  
3. **실시간 모니터링**  
   Slack으로 즉각적인 알림 수신  
4. **안정적인 데이터 관리**  
   S3 파티셔닝 구조로 분석 효율성 확보  
5. **확장성 높은 설계**  
   다른 API 또는 소스 추가 시 손쉬운 확장 가능  

---

## 📊 예상 비용 (월 기준)
| 항목 | 예상비용(USD) |
|------|----------------|
| AWS Lambda | 0.10 |
| S3 스토리지 | 0.01 |
| EventBridge | 0.01 |
| CloudWatch Logs | 0.05 |
| **총합** | **약 $0.20 (≈ 270원)** |

---

##  결론
- ✅ 서버 관리 없는 자동화 파이프라인 구축  
- ✅ 실시간 Slack 모니터링으로 신속한 대응  
- ✅ 일자별 S3 저장 구조로 데이터 신뢰성 확보  
- ✅ 낮은 운영 비용 대비 높은 확장성 확보  

이 프로젝트는 **AWS 서버리스 생태계 기반 데이터 자동화의 모범 사례**로,  
향후 다양한 데이터 수집 및 분석 파이프라인에 적용할 수 있습니다.

---

## 📚 참고 자료
- [AWS Lambda Developer Guide](https://docs.aws.amazon.com/lambda/latest/dg/welcome.html)  
- [Amazon EventBridge Scheduler](https://docs.aws.amazon.com/eventbridge/latest/userguide/scheduler.html)  
- [Amazon S3 Developer Guide](https://docs.aws.amazon.com/AmazonS3/latest/dev/Welcome.html)  
- [Slack Incoming Webhooks](https://api.slack.com/messaging/webhooks)

---

**태그:** `#AWS` `#Lambda` `#Serverless` `#S3` `#EventBridge` `#Slack` `#DataPipeline` `#Automation`
