import requests
import pandas as pd
import time
import os
import sys
from datetime import datetime
from urllib.parse import quote
import xml.etree.ElementTree as ET

# ---------------------------------------------------------
# API 키: GitHub Secrets(SEOUL_API_KEY)에서 읽어옴.
# 로컬 테스트 시에는 환경변수로 직접 지정해서 실행하면 됩니다.
#   예) SEOUL_API_KEY=발급받은키 python collect.py
# ---------------------------------------------------------
API_KEY = os.environ.get("SEOUL_API_KEY")
if not API_KEY:
    print("ERROR: 환경변수 SEOUL_API_KEY 가 설정되지 않았습니다.")
    sys.exit(1)

AREA_LIST = [
    "DDP(동대문디자인플라자)","DMC(디지털미디어시티)","가락시장","가로수길","가산디지털단지역",
    "강남 MICE 관광특구","강남역","강서한강공원","건대입구역","경복궁",
    "고덕역","고속터미널역","고척돔","광나루한강공원","광장(전통)시장",
    "광화문·덕수궁","광화문광장","교대역","구로디지털단지역","구로역",
    "국립중앙박물관·용산가족공원","군자역","김포공항","난지한강공원","남대문시장",
    "남산공원","노들섬","노량진","대림역","덕수궁길·정동길",
    "동대문 관광특구","동대문역","뚝섬역","뚝섬한강공원","망원한강공원",
    "명동 관광특구","미아사거리역","반포한강공원","발산역","보라매공원",
    "보신각","북서울꿈의숲","북창동 먹자골목","북촌한옥마을","사당역",
    "삼각지역","서대문독립공원","서리풀공원·몽마르뜨공원","서울 암사동 유적","서울대공원",
    "서울대입구역","서울숲공원","서울식물원·마곡나루역","서울역","서촌",
    "선릉역","성수카페거리","성신여대입구역","송리단길·호수단길","송현녹지광장",
    "수유역","숭례문","시의회 앞","신논현역·논현역","신도림역",
    "신림역","신정네거리역","신촌 스타광장","신촌·이대역","쌍문역",
    "아차산","안양천","압구정로데오거리","양재역","양화한강공원",
    "어린이대공원","여의도","여의도한강공원","여의서로","역삼역",
    "연남동","연신내역","영등포 타임스퀘어","오목교역·목동운동장","올림픽공원",
    "왕십리역","용리단길","용산역","월드컵공원","응봉산",
    "이촌한강공원","이태원 관광특구","이태원 앤틱가구거리","이태원역","익선동",
    "인사동","잠실 관광특구","잠실롯데타워·석촌호수","잠실새내역","잠실역",
    "잠실종합운동장","잠실한강공원","잠원한강공원","장지역","장한평역",
    "종로·청계 관광특구","창덕궁·종묘","창동 신경제 중심지","천호역","청계산",
    "청담동 명품거리","청량리 제기동 일대 전통시장","총신대입구(이수)역","충정로역","합정역",
    "해방촌·경리단길","혜화역","홍대 관광특구","홍대입구역(2호선)","홍제폭포","회기역"
]

CSV_FILE = "seoul_population_log.csv"
MAX_RETRIES = 2          # 지역별 실패 시 재시도 횟수
RETRY_WAIT_SECONDS = 2   # 재시도 전 대기
REQUEST_TIMEOUT = 15
SLEEP_BETWEEN_REQUESTS = 0.3  # API 서버 부담 방지

# 이번 실행에서 수집된 모든 행은 "같은 수집시간"으로 기록한다.
# 예정된 30분 정각이 아니라 실제로 이 스크립트가 실행된 시각을 그대로 기록하므로,
# GitHub Actions가 지연되더라도 데이터 자체의 시각 정보는 항상 정확하다.
COLLECTED_AT = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def fetch_area_population(area_name: str) -> dict:
    url = (
        f"http://openapi.seoul.go.kr:8088/"
        f"{API_KEY}/xml/citydata_ppltn/1/5/{quote(area_name)}"
    )

    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            res = requests.get(url, timeout=REQUEST_TIMEOUT)
            res.raise_for_status()

            root = ET.fromstring(res.text)
            code = root.findtext(".//CODE")
            message = root.findtext(".//MESSAGE")

            if code and code != "INFO-000":
                raise RuntimeError(f"{code} / {message}")

            return {
                "수집시간": COLLECTED_AT,
                "지역명": area_name,
                "API지역명": root.findtext(".//AREA_NM"),
                "혼잡도": root.findtext(".//AREA_CONGEST_LVL"),
                "혼잡도메시지": root.findtext(".//AREA_CONGEST_MSG"),
                "최소인구": root.findtext(".//AREA_PPLTN_MIN"),
                "최대인구": root.findtext(".//AREA_PPLTN_MAX"),
                "업데이트시간": root.findtext(".//PPLTN_TIME"),
            }

        except Exception as e:  # noqa: BLE001
            last_error = e
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_WAIT_SECONDS)

    raise last_error


def save_rows(rows: list[dict]) -> None:
    df = pd.DataFrame(rows)

    df["최소인구"] = pd.to_numeric(df["최소인구"], errors="coerce")
    df["최대인구"] = pd.to_numeric(df["최대인구"], errors="coerce")
    df["중앙추정인구"] = (df["최소인구"] + df["최대인구"]) / 2

    file_exists = os.path.exists(CSV_FILE)

    df.to_csv(
        CSV_FILE,
        mode="a",
        header=not file_exists,
        index=False,
        encoding="utf-8-sig",
    )


def main() -> None:
    print("=" * 60)
    print("수집 시작 (실제 실행 시각):", COLLECTED_AT)

    rows = []
    failed_areas = []

    for area in AREA_LIST:
        try:
            row = fetch_area_population(area)
            rows.append(row)
            print(f"성공: {area} | {row['혼잡도']} | {row['최소인구']}~{row['최대인구']}")
        except Exception as e:  # noqa: BLE001
            failed_areas.append(area)
            print(f"실패: {area} | {e}")
        time.sleep(SLEEP_BETWEEN_REQUESTS)

    if rows:
        save_rows(rows)
        print(f"\n{len(rows)}개 지역 저장 완료 ({len(failed_areas)}개 실패)")
    else:
        print("\n수집된 데이터가 없어 저장하지 않음")

    if failed_areas:
        print("실패한 지역 목록:", ", ".join(failed_areas))

    # rows가 하나도 없으면(=API 전체 장애 등) 워크플로우가 실패로 표시되도록 종료 코드 반환
    if not rows:
        sys.exit(1)


if __name__ == "__main__":
    main()
