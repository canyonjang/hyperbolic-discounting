import streamlit as st
import pandas as pd
import numpy as np
from supabase import create_client

# --- 수파베이스 연결 ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

try:
    supabase = init_connection()
except Exception as e:
    supabase = None

# --- 상태 관리 초기화 ---
if 'role' not in st.session_state:
    st.session_state.role = None
if 'nickname' not in st.session_state:
    st.session_state.nickname = ""
if 'current_scenario' not in st.session_state:
    st.session_state.current_scenario = 0
if 'step' not in st.session_state:
    st.session_state.step = 0
if 'low' not in st.session_state:
    st.session_state.low = 0
if 'high' not in st.session_state:
    st.session_state.high = 0

# 실험 시나리오 (금액, 지연개월수)
scenarios = [(10000, 1), (10000, 6), (10000, 12), (10000, 24),
             (1000000, 1), (1000000, 6), (1000000, 12), (1000000, 24)]
MAX_STEPS = 4

# --- 버튼 클릭 시 화면 갱신 전에 논리부터 처리하는 함수 ---
def make_choice(choice):
    amount, delay = scenarios[st.session_state.current_scenario]
    current_offer = int((st.session_state.low + st.session_state.high) / 2)

    if choice == 'now':
        st.session_state.high = current_offer
    else:
        st.session_state.low = current_offer

    st.session_state.step += 1

    # 4번의 질문이 끝났을 때 데이터 저장 및 다음 라운드 준비
    if st.session_state.step >= MAX_STEPS:
        indifference_point = int((st.session_state.low + st.session_state.high) / 2)
        if supabase:
            supabase.table("discount_results").insert({
                "nickname": st.session_state.nickname,
                "amount": amount,
                "delay_months": delay,
                "indifference_point": indifference_point,
                "passed_attention_check": True
            }).execute()
        
        st.session_state.current_scenario += 1
        st.session_state.step = 0
        st.session_state.low = 0
        if st.session_state.current_scenario < len(scenarios):
            st.session_state.high = scenarios[st.session_state.current_scenario][0]

def get_class_stage():
    if supabase:
        res = supabase.table('class_state').select('stage').eq('id', 1).execute()
        return res.data[0]['stage']
    return 'wait'

# --- 1. 로그인 화면 ---
if st.session_state.role is None:
    st.title("⏳ 시간과 보상 시뮬레이터")
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("👨‍🎓 학생 입장")
        nickname_input = st.text_input("별명을 입력하세요 (실명 금지):")
        if st.button("참여하기"):
            if nickname_input:
                st.session_state.nickname = nickname_input
                st.session_state.role = 'student'
                st.session_state.high = scenarios[0][0]
                st.rerun()
            else:
                st.warning("별명을 입력해주세요.")
                
    with col2:
        st.subheader("👨‍🏫 교수 입장")
        admin_pw = st.text_input("관리자 비밀번호:", type="password")
        if st.button("교수 화면 열기"):
            if admin_pw == "3383": 
                st.session_state.role = 'professor'
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")

# --- 2. 교수 제어 화면 ---
elif st.session_state.role == 'professor':
    st.title("👨‍🏫 교수 제어 대시보드")
    current_stage = get_class_stage()
    
    st.info(f"현재 강의실 상태: **{current_stage.upper()}**")
    
    # 통제 버튼 모음
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("1. 대기시키기", use_container_width=True):
            supabase.table('class_state').update({'stage': 'wait'}).eq('id', 1).execute()
            st.rerun()
    with c2:
        if st.button("2. 실험 시작", use_container_width=True):
            supabase.table('class_state').update({'stage': 'experiment'}).eq('id', 1).execute()
            st.rerun()
    with c3:
        if st.button("3. 결과 공개", use_container_width=True):
            supabase.table('class_state').update({'stage': 'result'}).eq('id', 1).execute()
            st.rerun()
            
    st.divider()
    
    # --- 추가 요청 기능 1: 현황 패널에 별명과 k값(평균) 함께 표시 ---
    st.subheader("👨‍🎓 실험 종료 학생 현황")
    if st.button("현황 새로고침"):
        data = supabase.table('discount_results').select('*').execute().data
        if data:
            df_status = pd.DataFrame(data)
            
            # 현황판에서 k값을 즉시 보여주기 위한 사전 계산
            df_status['V'] = df_status['indifference_point'].clip(lower=1)
            df_status['d'] = df_status['delay_months'] / 12.0
            df_status['k_val'] = (df_status['amount'] / df_status['V'] - 1) / df_status['d']
            
            counts = df_status['nickname'].value_counts()
            
            finished_students = counts[counts >= 8].index.tolist()
            in_progress_students = counts[counts < 8].index.tolist()
            
            if finished_students:
                # 완료한 학생들의 전체 평균 k값 도출
                finished_df = df_status[df_status['nickname'].isin(finished_students)]
                k_means = finished_df.groupby('nickname')['k_val'].mean()
                
                # 출력 텍스트 포맷팅: 별명 (k=0.00)
                finished_display = [f"{nick} (k={k_means[nick]:.2f})" for nick in finished_students]
                st.success(f"✅ 완료 학생 ({len(finished_students)}명): " + ", ".join(finished_display))
            else:
                st.success("✅ 완료 학생 (0명): 아직 없습니다.")
                
            if in_progress_students:
                st.warning(f"🏃 진행 중 학생 ({len(in_progress_students)}명): " + ", ".join(in_progress_students))
        else:
            st.info("아직 제출을 시작한 학생이 없습니다.")
            
    st.divider()
    
    # 결과 분석 및 r, k 계산
    if current_stage == 'result':
        st.subheader("📊 실시간 할인율 분석 결과")
        data = supabase.table('discount_results').select('*').execute().data
        
        if data:
            df = pd.DataFrame(data)
            df = df[df['passed_attention_check'] == True]
            
            if not df.empty:
                df['V'] = df['indifference_point'].clip(lower=1)
                df['A'] = df['amount']
                df['d'] = df['delay_months'] / 12.0
                
                df['r_value'] = (df['A'] / df['V']) ** (1 / df['d']) - 1
                df['k_value'] = (df['A'] / df['V'] - 1) / df['d']
                
                # --- 평균 선 그래프 영역 ---
                summary = df.groupby(['amount', 'delay_months'])[['V', 'r_value', 'k_value']].mean().reset_index()
                
                st.write("#### 💰 1만원 보상 조건 분석 (전체 평균)")
                df_10k = summary[summary['amount'] == 10000]
                
                col_chart1, col_chart2 = st.columns(2)
                with col_chart1:
                    st.write("**기간별 계산된 지수형 할인율 (r값)**")
                    st.line_chart(df_10k.set_index('delay_months')['r_value'], color="#FF4B4B")
                with col_chart2:
                    st.write("**기간별 계산된 쌍곡형 할인율 (k값)**")
                    st.line_chart(df_10k.set_index('delay_months')['k_value'], color="#1f77b4")
                
                st.divider()
                
                st.write("#### 💰 100만원 보상 조건 분석 (전체 평균)")
                df_1000k = summary[summary['amount'] == 1000000]
                
                col_chart3, col_chart4 = st.columns(2)
                with col_chart3:
                    st.write("**기간별 계산된 지수형 할인율 (r값)**")
                    st.line_chart(df_1000k.set_index('delay_months')['r_value'], color="#FF4B4B")
                with col_chart4:
                    st.write("**기간별 계산된 쌍곡형 할인율 (k값)**")
                    st.line_chart(df_1000k.set_index('delay_months')['k_value'], color="#1f77b4")
                
                st.divider()

                # --- 추가 요청 기능 2: 학생 개인별 평균 k값 분포 시각화 (히스토그램) ---
                st.write("#### 👥 반 전체 학생들의 충동성(k값) 분포")
                st.caption("학생 개인별 평균 k값을 나타낸 분포도입니다. 오른쪽으로 갈수록(k값이 클수록) 당장의 유혹에 약하고 충동적인 학생입니다.")
                
                # 학생별 전체 시나리오의 평균 k값 계산
                student_k_mean = df.groupby('nickname')['k_value'].mean()
                
                # 데이터를 10개의 구간(bin)으로 나누어 히스토그램 데이터 생성
                hist_counts, bin_edges = np.histogram(student_k_mean, bins=10)
                
                # 스트림릿 막대 차트에 넣기 위해 데이터프레임으로 변환
                # 가로축 라벨 예시: "0.5~2.1"
                hist_df = pd.DataFrame(
                    {'학생 수(명)': hist_counts},
                    index=[f"{bin_edges[i]:.1f} ~ {bin_edges[i+1]:.1f}" for i in range(len(bin_edges)-1)]
                )
                
                # 막대그래프 렌더링
                st.bar_chart(hist_df, color="#2ca02c")

            else:
                st.write("유효한 데이터가 부족합니다.")

# --- 3. 학생 참여 화면 ---
elif st.session_state.role == 'student':
    current_stage = get_class_stage()
    
    if current_stage == 'wait':
        st.title("☕ 대기실")
        st.write("교수님께서 실험을 시작하실 때까지 기다려주세요.")
        if st.button("상태 새로고침"):
            st.rerun()
            
    elif current_stage == 'result':
        st.title("✅ 실험 종료")
        st.write("앞의 스크린을 통해 전체 분석 결과를 확인해 보세요.")
        
    elif current_stage == 'experiment':
        if st.session_state.current_scenario >= len(scenarios):
            st.success("내 응답이 완료되었습니다. 다른 학생들을 위해 잠시 대기해 주세요.")
            if st.button("현재 상태 확인"):
                st.rerun()
        else:
            amount, delay = scenarios[st.session_state.current_scenario]
            current_offer = int((st.session_state.low + st.session_state.high) / 2)
            
            st.progress((st.session_state.current_scenario) / len(scenarios), text=f"전체 진행률 ({st.session_state.current_scenario + 1}/{len(scenarios)})")
            
            st.subheader(f"Q. 다음 중 하나를 선택하세요. (현재 {amount:,}원 세트)")
            st.write(f"지연 기간: **{delay}개월 뒤**")
            
            col1, col2 = st.columns(2)
            with col1:
                st.button(f"👇 **지금 당장** {current_offer:,}원 받기", on_click=make_choice, args=('now',), use_container_width=True)
            with col2:
                st.button(f"⏳ **{delay}개월 뒤에** {amount:,}원 받기", on_click=make_choice, args=('later',), use_container_width=True)
