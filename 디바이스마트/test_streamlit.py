import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import streamlit as st
import openai
import matplotlib.pyplot as plt
import matplotlib
import re
import pandas as pd
import folium
from streamlit_folium import st_folium
import urllib.parse

matplotlib.rc('font', family='AppleGothic')  # 한글 폰트 설정

# ==== 세션 초기화 ====
if "analyzed" not in st.session_state:
    st.session_state["analyzed"] = None
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [{"role": "system", "content": "너는 유동인구, 부동산, 업종 데이터를 바탕으로 창업을 상담해주는 전문가야."}]

# ==== API 설정 ====
openai.api_key = st.secrets["OPENAI_API_KEY"]

# ==== JSON 데이터 불러오기 ====
with open("부동산.json", "r", encoding="utf-8") as f:
    gu_code_map = json.load(f)

with open("서울시 읍면동마스터 정보.json", "r", encoding="utf-8") as f:
    address_data = json.load(f)

# ==== 부동산 & 유동인구 API ====
REAL_ESTATE_API = "http://apis.data.go.kr/1613000/RTMSDataSvcNrgTrade/getRTMSDataSvcNrgTrade"
REAL_ESTATE_KEY = "KY6+sZJd4Nm01OKBmqKrAv/Ao/HM3mUBs5w+Yz2ojnNs7pUZZ+gMJA8y/U4lOJRPJyeaOd6NFLm72uuTFerGOw=="
POPULATION_API_KEY = "637a794770696d773835554e517467"
POPULATION_API = f"http://openapi.seoul.go.kr:8088/{POPULATION_API_KEY}/json/tpssPassengerCnt/1/1000"

# ==== 함수들 ====

def get_real_estate_by_dong(gu_name, dong_name):
    lawd_cd = gu_code_map.get(gu_name)
    if not lawd_cd:
        return []
    now = datetime.now()
    results = []
    for i in range(6):
        yyyymm = (now.replace(day=1) - pd.DateOffset(months=i)).strftime("%Y%m")
        params = {
            "serviceKey": REAL_ESTATE_KEY,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": yyyymm,
            "pageNo": "1",
            "numOfRows": "100",
            "type": "xml"
        }
        try:
            res = requests.get(REAL_ESTATE_API, params=params, timeout=10)
            root = ET.fromstring(res.content)
            items = root.find("body/items")
            for item in items.findall("item"):
                umd = item.findtext("umdNm", default="N/A")
                if dong_name in umd:
                    results.append({
                        "dealAmount": item.findtext("dealAmount", "N/A"),
                        "dealYear": int(item.findtext("dealYear", "0")),
                        "dealMonth": int(item.findtext("dealMonth", "0")),
                        "dealDay": int(item.findtext("dealDay", "0")),
                        "buildingType": item.findtext("buildingType", "N/A")
                    })
        except Exception as e:
            print("부동산 API 오류:", e)
            continue
    results.sort(key=lambda x: (x["dealYear"], x["dealMonth"], x["dealDay"]), reverse=True)
    return results[:30]

def get_passenger_info_by_dong(gu_name, dong_name):
    target_id = None
    for entry in address_data["DATA"]:
        if entry["cgg_nm"] == gu_name and entry["dong_nm"] == dong_name:
            if len(entry.get("dong_id", "")) == 8:
                target_id = entry["dong_id"]
                break

    if not target_id:
        print("⚠️ JSON에서 동을 찾지 못했습니다.")
        return None

    try:
        response = requests.get(POPULATION_API, timeout=10)
        if response.status_code == 200:
            data = response.json()
            rows = data.get("tpssPassengerCnt", {}).get("row", [])
            filtered = [row for row in rows if row.get("DONG_ID") == target_id]
            if filtered:
                return filtered[0]
            else:
                print("해당 DONG_ID 데이터 없음.")
    except Exception as e:
        print("❌ 유동인구 API 오류:", e)

def get_similar_business_info_gpt(gu_name, dong_name, business_type):
    prompt = f"""
서울시 {gu_name} {dong_name} 지역에 '{business_type}' 업종과 관련된 경쟁 업종 종류와 대략적인 개수를 알려줘.
"""
    try:
        messages = [
            {"role": "system", "content": "너는 지역 상권 분석 전문가야."},
            {"role": "user", "content": prompt}
        ]
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
        answer = response.choices[0].message["content"]
        number_match = re.search(r'\d+', answer.replace(',', ''))
        count = int(number_match.group()) if number_match else 0
        return {"description": answer, "count": count}
    except Exception as e:
        st.error(f"GPT 유사 업종 추정 오류: {e}")
        return {"description": "GPT 분석 실패", "count": 0}

def get_gpt_business_recommendation(gu, dong, population, estate_data):
    try:
        pop_value = population.get('PSNG_NO', '정보 없음') if population else '정보 없음'
        estate_count = len(estate_data) if estate_data else 0
        prompt = f"""
서울시 {gu} {dong} 지역에서 유동인구가 약 {pop_value}명이고, 최근 {estate_count}건의 부동산 거래가 발생했어.
이 조건을 바탕으로 창업에 적합한 업종을 하나 추천해줘.
"""
        messages = [
            {"role": "system", "content": "너는 창업 전략가야."},
            {"role": "user", "content": prompt}
        ]
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
        return response.choices[0].message["content"]
    except Exception as e:
        st.error(f"GPT 업종 추천 오류: {e}")
        return "GPT 추천 실패"

def evaluate_suitability(pop, estate_data, similar_count):
    score = 0
    if pop:
        try:
            total = int(pop.get("RIDE_PASGR_NUM", 0)) + int(pop.get("ALIGHT_PASGR_NUM", 0))
            if total > 5000:
                score += 1
        except:
            pass
    if estate_data:
        try:
            recent = [int(x["dealAmount"].replace(",", "")) for x in estate_data if x["dealAmount"] != "N/A"]
            if recent and sum(recent)/len(recent) < 120000:
                score += 1
        except:
            pass
    if similar_count < 10:
        score += 1
    if score == 3:
        return "✅ 매우 적합한 입지예요! 👍"
    elif score == 2:
        return "⚠️ 나쁘진 않지만 경쟁을 고려하세요."
    else:
        return "❌ 다소 불리한 입지입니다."

def plot_population_by_hour(data):
    hours = list(range(24))
    values = [data.get(f"PSNG_NO_{str(h).zfill(2)}", 0) for h in hours]
    fig, ax = plt.subplots()
    ax.plot(hours, values, marker='o')
    ax.set_title("시간대별 유동인구")
    ax.set_xlabel("시간")
    ax.set_ylabel("인구 수")
    ax.grid(True)
    st.pyplot(fig)

def plot_real_estate_trend(data):
    df = pd.DataFrame(data)
    if df.empty:
        return
    df['날짜'] = pd.to_datetime(df['dealYear'].astype(str) + '-' + df['dealMonth'].astype(str) + '-' + df['dealDay'].astype(str))
    df['가격'] = df['dealAmount'].str.replace(',', '').astype(float)
    df = df.sort_values('날짜')
    fig, ax = plt.subplots()
    ax.plot(df['날짜'], df['가격'], marker='o')
    ax.set_title('부동산 거래 가격 추세')
    ax.set_xlabel('날짜')
    ax.set_ylabel('가격(만원)')
    st.pyplot(fig)


def get_lat_lng_from_kakao(gu, dong):
    try:
        address = f"서울특별시 {gu} {dong}"
        headers = {
            "Authorization": f"KakaoAK {st.secrets['KAKAO_REST_API_KEY']}"
        }
        url = f"https://dapi.kakao.com/v2/local/search/address.json?query={urllib.parse.quote(address)}"
        res = requests.get(url, headers=headers)

        if res.status_code == 200:
            data = res.json()
            documents = data.get("documents")
            if documents:
                lat = float(documents[0]["y"])
                lng = float(documents[0]["x"])
                return lat, lng
            else:
                st.warning("📍 Kakao API에서 주소 결과를 찾지 못했어요.")
        else:
            st.error(f"❌ Kakao API 오류: {res.status_code}")
    except Exception as e:
        st.error(f"📡 Kakao 주소 변환 오류: {e}")
    return None, None


def show_map(gu, dong):
    lat, lng = get_lat_lng_from_kakao(gu, dong)
    if lat is not None and lng is not None:
        m = folium.Map(location=[lat, lng], zoom_start=15)

        # 👉 커스텀 귀여운 마커
        icon = folium.CustomIcon(
            icon_image='https://cdn-icons-png.flaticon.com/512/4712/4712027.png',
            icon_size=(40, 40)
        )

        folium.Marker(
            [lat, lng],
            tooltip=f"{gu} {dong} (AI 마커)",
            icon=icon
        ).add_to(m)

        st_folium(m, width=700, height=400)
    else:
        st.info("위치를 찾지 못했어요.")




# ✅ HUFF 모델 분석 함수
def get_huff_analysis_with_gpt(gu_name, dong_name, item_name, population, estate_data, similar_desc):
    try:
        pop_value = population.get('PSNG_NO', '정보 없음') if population else '정보 없음'
        recent_count = len(estate_data) if estate_data else 0
        prompt = f"""
서울시 {gu_name} {dong_name} 지역에 대해 HUFF 모델을 사용해서 '{item_name}' 업종의 입지 적합성을 분석해줘.

다음과 같은 정보를 참고할 수 있어:
- 유동인구: {pop_value}명
- 부동산 거래 건수: {recent_count}
- 유사 업종 정보: {similar_desc}

필요하다면 합리적인 가정을 통해 데이터를 보완해서 HUFF 모델 기반 분석을 해줘. 분석 결과를 바탕으로 창업 적합성을 평가해줘.
"""
        messages = [{"role": "system", "content": "너는 HUFF 모델 기반 상권 분석 전문가야."},
                    {"role": "user", "content": prompt}]
        response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=messages)
        return response.choices[0].message["content"]
    except Exception as e:
        return f"HUFF 모델 분석 실패: {e}"

# ==== Streamlit 앱 ====
st.title("💬 창업 상담 챗봇")

with st.form("지역입력"):
    gu = st.text_input("자치구 (예: 용산구)")
    dong = st.text_input("행정동 (예: 한남동)")
    item = st.text_input("업종 (예: 카페, 편의점 등)")
    submit = st.form_submit_button("🔍 분석 시작!")

if submit:
    if "gpt_location" in st.session_state:
        del st.session_state["gpt_location"]

    with st.spinner("🔍 분석 중입니다..."):
        estate = get_real_estate_by_dong(gu, dong)
        pop = get_passenger_info_by_dong(gu, dong)
        similar = get_similar_business_info_gpt(gu, dong, item)
        score = evaluate_suitability(pop, estate, similar["count"])
        recommendation = get_gpt_business_recommendation(gu, dong, pop, estate)
        huff_analysis = get_huff_analysis_with_gpt(gu, dong, item, pop, estate, similar["description"])

        st.session_state["analyzed"] = {
            "gu": gu, "dong": dong, "item": item,
            "population": pop, "estate": estate,
            "similar_cnt": similar["count"],
            "similar_desc": similar["description"],
            "suitability": score,
            "recommendation": recommendation,
            "huff_analysis": huff_analysis  # ✅ 여기에 포함시킴
        }

if st.session_state["analyzed"]:
    a = st.session_state["analyzed"]
    st.subheader("📍 지역 위치")
    show_map(a["gu"], a["dong"])

    st.subheader("🏠 부동산 거래 내역")
    if a["estate"]:
        for e in a["estate"]:
            st.write(f"{e['dealYear']}년 {e['dealMonth']}월 {e['dealDay']}일 - {e['dealAmount']}원 / {e['buildingType']}")
        plot_real_estate_trend(a["estate"])
    else:
        st.write("📭 거래 내역 없음")

    st.subheader("🚶 유동인구 정보")
    if a["population"]:
        st.write(f"총 유동인구: {int(a['population'].get('PSNG_NO', 0)):,}명")
        plot_population_by_hour(a["population"])

    st.subheader("🧭 유사 업종 현황")
    st.write(a["similar_desc"])

    st.subheader("📊 창업 적합도 분석")
    st.success(a["suitability"])

    st.subheader("🧠 GPT 추천 업종")
    st.info(a["recommendation"])

    st.subheader("📐 HUFF 모델 기반 분석")
    st.markdown(a["huff_analysis"])

# === GPT 자유 상담 챗봇 영역 ===
st.markdown("---")
st.subheader("💬 GPT와 자유롭게 상담해보세요")
user_input = st.text_input("질문해보세요")
if user_input:
    if st.session_state["analyzed"]:
        a = st.session_state["analyzed"]
        context = f"""
- 지역: {a['gu']} {a['dong']}
- 업종: {a['item']}
- 유동인구: {a['population'].get('PSNG_NO', '정보 없음'):,}명
- 거래 건수: {len(a['estate'])}
- 유사 업종 수: {a['similar_cnt']}개
- 관련 업종 설명: {a['similar_desc']}
- 적합도 평가: {a['suitability']}
- 추천 업종: {a['recommendation']}
"""
        st.session_state.chat_history.append({"role": "user", "content": context + "\n\n" + user_input})
    else:
        st.session_state.chat_history.append({"role": "user", "content": user_input})

    try:
        res = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=st.session_state.chat_history)
        reply = res.choices[0].message["content"]
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.markdown(f"🤖 **GPT:**\n\n{reply}")
    except Exception as e:
        st.error(f"GPT 응답 오류: {e}")