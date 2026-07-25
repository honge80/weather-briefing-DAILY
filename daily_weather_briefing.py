#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
일일 항공기상 브리핑 자동 생성 및 이메일 발송 스크립트 (GitHub Actions용)
"""

import os
import requests
import smtplib
import re
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText
from email.utils import formatdate

# ------------------------------------------------------------------
# 1) 대상 공항 목록 (ICAO 코드 기준)
# ------------------------------------------------------------------
AIRPORTS = {
    "국내": {
        "RKSI": "인천",
        "RKSS": "김포",
        "RKPC": "제주",
        "RKJY": "여수",
        "RKJJ": "광주",
        "RKTU": "청주",
        "RKTN": "대구",
        "RKPK": "부산(김해)",
    },
    "동남아": {
        "VTBS": "방콕(BKK)",
        "RPLC": "클락(CRK)",
        "VVDN": "다낭(DAD)",
        "VVNB": "하노이(HAN)",
        "VHHH": "홍콩(HKG)",
        "VVTS": "호치민(SGN)",
        "RCTP": "타이베이(TPE)",
        "VDPP": "프놈펜(KTI)",
    },
    "중국": {
        "ZGGG": "광저우(CAN)",
        "ZYCC": "창춘(CGQ)",
        "ZUCK": "충칭(CKG)",
        "ZGHA": "창사(CSX)",
        "ZYTL": "다롄(DLC)",
        "ZSHC": "항저우(HGH)",
        "ZYHB": "하얼빈(HRB)",
        "ZSNJ": "난징(NKG)",
        "ZBAA": "베이징 서우두(PEK)",
        "ZSPD": "상하이 푸둥(PVG)",
        "ZGSZ": "선전(SZX)",
        "ZUTF": "청두 톈푸(TFU)",
        "ZBTJ": "톈진(TSN)",
        "ZLXY": "시안(XIY)",
        "ZYYJ": "옌지(YNJ)",
        "ZSYN": "옌청(YNZ)",
    },
    "일본": {
        "RJCC": "삿포로 신치토세(CTS)",
        "RJFF": "후쿠오카(FUK)",
        "RJBB": "오사카 간사이(KIX)",
        "RJFM": "미야자키(KMI)",
        "RJGG": "나고야 주부(NGO)",
        "RJAA": "도쿄 나리타(NRT)",
        "ROAH": "오키나와 나하(OKA)",
        "RJSS": "센다이(SDJ)",
    },
}

API_BASE = "https://aviationweather.gov/api/data"


def fetch_metar(icao_codes):
    """복수 공항 METAR 데이터 일괄 조회"""
    ids = ",".join(icao_codes)
    url = f"{API_BASE}/metar?ids={ids}&format=json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    return {item["icaoId"]: item for item in resp.json()}


def fetch_taf(icao_codes):
    """복수 공항 TAF 데이터 일괄 조회"""
    ids = ",".join(icao_codes)
    url = f"{API_BASE}/taf?ids={ids}&format=json"
    resp = requests.get(url, timeout=15)
    resp.raise_for_status()
    result = {}
    for item in resp.json():
        result.setdefault(item["icaoId"], item)
    return result


def check_alert_conditions(metar_raw):
    """METAR 텍스트에서 경고 조건(비, 바람 10KT 이상, 구름 500FT 이하) 검사"""
    if not metar_raw or metar_raw == "자료 없음":
        return False, []

    reasons = []

    # 1) RA (비) 포함 여부
    if re.search(r'\b(?:\+|\-)?(?:[A-Z]*)*RA\b', metar_raw):
        reasons.append("강수(RA)")

    # 2) 바람 10KT 이상 검사
    wind_match = re.search(r'\b\d{3}(\d{2,3})(?:G\d{2,3})?KT\b', metar_raw)
    if wind_match:
        speed = int(wind_match.group(1))
        if speed >= 10:
            reasons.append(f"강풍({speed}KT)")

    # 3) 구름 고도 500FT 이하 검사
    cloud_matches = re.findall(r'\b(?:FEW|SCT|BKN|OVC)(\d{3})\b', metar_raw)
    for height_str in cloud_matches:
        height = int(height_str) * 100
        if height <= 500:
            reasons.append(f"운저고도 저하({height}FT)")
            break

    is_alert = len(reasons) > 0
    return is_alert, reasons


def build_html_report():
    """HTML 형태의 기상 브리핑 리포트 생성"""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    all_codes = []
    for group in AIRPORTS.values():
        all_codes.extend(group.keys())

    metar_data = fetch_metar(all_codes)
    taf_data = fetch_taf(all_codes)

    html_lines = [
        "<html><body>",
        f"<h2>✈️ 일일 항공기상 브리핑 ({now_utc} 기준)</h2>",
        "<p style='color: gray;'>※ 빨간색 표시는 비(RA), 바람 10KT 이상, 또는 구름 고도 500FT 이하 조건 발생 공항입니다.</p>",
        "<hr>"
    ]

    for region, airports in AIRPORTS.items():
        html_lines.append(f"<h3>[ {region} ]</h3><ul>")
        for icao, name_kr in airports.items():
            m = metar_data.get(icao)
            t = taf_data.get(icao)

            metar_text = m.get("rawOb", "자료 없음") if m else "자료 없음"
            taf_text = t.get("rawTAF", "자료 없음") if t else "자료 없음"

            is_alert, alert_reasons = check_alert_conditions(metar_text)

            if is_alert:
                reasons_str = ", ".join(alert_reasons)
                header = f"<b style='color: red;'>🚨 {name_kr} ({icao}) - [주의: {reasons_str}]</b>"
            else:
                header = f"<b>{name_kr} ({icao})</b>"

            html_lines.append(f"<li>{header}")
            html_lines.append(f"  <ul>")
            html_lines.append(f"    <li><b>METAR:</b> {metar_text}</li>")
            html_lines.append(f"    <li><b>TAF:</b> {taf_text}</li>")
            html_lines.append(f"  </ul><br>")
            html_lines.append(f"</li>")
        html_lines.append("</ul>")

    html_lines.append("</body></html>")
    return "\n".join(html_lines)


def send_email(subject, html_body):
    """네이버 SMTP 서버를 통한 이메일 발송"""
    SENDER_EMAIL = "hong_e80@naver.com"
    # GitHub Secrets에 저장된 암호화 비밀번호를 읽어옵니다.
    APP_PASSWORD = os.environ.get("NAVER_APP_PASSWORD", "FJCK2HM8TL2L")
    RECEIVER_EMAIL = "honge80@flyasiana.com"

    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Date"] = formatdate(localtime=True)

    try:
        with smtplib.SMTP_SSL("smtp.naver.com", 465) as server:
            server.login(SENDER_EMAIL, APP_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("✅ HTML 이메일 발송 성공!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")


if __name__ == "__main__":
    print("1. 항공기상 데이터 수집 중...")
    report_html = build_html_report()

    kst_now = datetime.now(timezone(timedelta(hours=9)))
    email_subject = f"[항공기상] 일일 브리핑 리포트 ({kst_now.strftime('%Y-%m-%d %H:%M KST')})"

    print("2. 이메일 발송 중...")
    send_email(email_subject, report_html)