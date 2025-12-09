from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os
import json
import re
from dotenv import load_dotenv

# 환경 변수 로드
load_dotenv()

app = Flask(__name__)
CORS(app)  # CORS 허용 (프론트엔드에서 API 호출 가능하도록)

# OpenAI API 키 설정 (환경 변수에서 읽기)
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY 환경 변수가 설정되지 않았습니다. .env 파일을 확인해주세요.")

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY)

# 캠퍼스 시설 데이터 로드
def load_campus_data():
    """data.json 파일에서 캠퍼스 시설 정보를 로드합니다."""
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print("Warning: data.json 파일을 찾을 수 없습니다.")
        return None
    except json.JSONDecodeError:
        print("Warning: data.json 파일의 형식이 올바르지 않습니다.")
        return None

# 앱 시작 시 캠퍼스 데이터 로드
campus_data = load_campus_data()

def get_system_prompt():
    """시스템 프롬프트를 생성합니다."""
    base_prompt = """당신은 동양미래대학교 캠퍼스 안내 챗봇입니다. 사용자가 캠퍼스 내 위치, 시설, 건물 등에 대해 질문하면 친절하고 정확하게 답변하세요.

출력 형식(숫자는 출력하지 마세요):
- 제목: (건물명 또는 시설명만 넣기)
- 설명: (해당 위치를 간단히 설명)
- 추가 정보: (관련된 층 정보나 시설 목록 제공)

중요 규칙:
- 반드시 JSON 데이터에 있는 정보만 사용
- 건물명, 층수, 시설명은 JSON의 값과 정확히 일치
- JSON에 없는 정보라면 "해당 정보를 찾을 수 없습니다"라고 답변
- '1. 제목' 같은 숫자나 예시 문구는 절대 출력하지 않기
- 숫자 리스트 형식(1., 2., 3. 등)을 사용하지 마세요
- 건물명은 정확히 일치시켜주세요 (예: "1호관", "2호관", "도서관")
- 층수는 JSON 데이터에 명시된 형식 그대로 사용하세요 (예: "1F", "2F", "B1F")
- 시설명도 JSON 데이터에 있는 정확한 이름을 사용하세요

출력 예시:
제목: 3호관 2F
설명: 컴퓨터공학부 사무실은 3호관 2F에 위치해 있습니다.
추가 정보: 2F에는 전산실습실도 있습니다.
"""
    
    if campus_data:
        # JSON 데이터를 문자열로 변환하여 프롬프트에 추가
        data_str = json.dumps(campus_data, ensure_ascii=False, indent=2)
        base_prompt += f"""

다음은 동양미래대학교 캠퍼스 시설 정보입니다. 이 정보를 기반으로 정확하게 답변해주세요:

{data_str}

위 JSON 데이터를 참고하여 사용자의 질문에 정확하게 답변해주세요. 반드시 위 데이터에 있는 정보만 사용하고, 데이터에 없는 정보는 제공하지 마세요.
"""
    
    return base_prompt

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_message = data.get('message', '')
        
        if not user_message:
            return jsonify({'error': '메시지가 필요합니다.'}), 400
        
        # 시스템 프롬프트 생성 (캠퍼스 데이터 포함)
        system_prompt = get_system_prompt()
        
        # GPT API 호출
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # 또는 "gpt-3.5-turbo"
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_message
                }
            ],
            temperature=0.7,
            max_tokens=800  # 더 긴 답변을 위해 토큰 수 증가
        )
        
        bot_response = response.choices[0].message.content
        
        # 응답 파싱 (제목, 설명, 추가 정보 추출)
        # 숫자 리스트 형식(1., 2., 3. 등) 제거
        cleaned_response = bot_response
        # "1. 제목:", "2. 설명:" 같은 패턴 제거
        cleaned_response = re.sub(r'^\d+\.\s*', '', cleaned_response, flags=re.MULTILINE)
        
        lines = cleaned_response.strip().split('\n')
        title = "안내"
        description = cleaned_response
        extraInfo = ""
        
        # "제목:", "설명:", "추가 정보:" 패턴으로 파싱 시도
        current_section = None
        title_lines = []
        description_lines = []
        extraInfo_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 섹션 헤더 확인
            if line.startswith('제목:'):
                current_section = 'title'
                title_text = line.replace('제목:', '').strip()
                if title_text:
                    title = title_text
                continue
            elif line.startswith('설명:'):
                current_section = 'description'
                desc_text = line.replace('설명:', '').strip()
                if desc_text:
                    description_lines.append(desc_text)
                continue
            elif line.startswith('추가 정보:'):
                current_section = 'extrainfo'
                extra_text = line.replace('추가 정보:', '').strip()
                if extra_text:
                    extraInfo_lines.append(extra_text)
                continue
            
            # 현재 섹션에 내용 추가
            if current_section == 'title' and not title_lines:
                title = line
            elif current_section == 'description':
                description_lines.append(line)
            elif current_section == 'extrainfo':
                extraInfo_lines.append(line)
        
        # 파싱된 내용이 있으면 사용
        if description_lines:
            description = '\n'.join(description_lines).strip()
        if extraInfo_lines:
            extraInfo = '\n'.join(extraInfo_lines).strip()
        
        # 파싱 실패 시 기존 로직 사용
        if title == "안내" and not any(keyword in cleaned_response for keyword in ['제목:', '설명:', '추가 정보:']):
            # 건물명 패턴 찾기 (예: "7호관", "도서관", "1호관 3층" 등)
            for i, line in enumerate(lines[:3]):
                line = line.strip()
                if any(keyword in line for keyword in ['호관', '도서관', '층']):
                    # ":" 또는 "-" 뒤의 내용 제거
                    if ':' in line:
                        title = line.split(':')[0].strip()
                    elif '-' in line and len(line.split('-')[0]) < 20:
                        title = line.split('-')[0].strip()
                    else:
                        # 첫 30자만 제목으로 사용
                        title = line[:30].strip()
                    break
            
            if title != "안내" and lines:
                description = '\n'.join(lines[1:]).strip() if len(lines) > 1 else cleaned_response
            else:
                description = cleaned_response
        
        # 추가 정보: 건물/시설 관련 상세 정보 추출 및 이미지 URL 찾기
        image_url = None
        matched_building = None
        if campus_data:
            user_lower = user_message.lower()
            
            # 1단계: 건물명으로 직접 매칭 시도
            for building in campus_data.get('campus_facilities', []):
                building_name = building.get('building_name', '')
                building_name_clean = building_name.replace(' (대학본부)', '').strip()
                
                # 건물명이 질문에 포함되어 있는지 확인 (다양한 패턴 체크)
                building_keywords = []
                if '호관' in building_name:
                    # "1호관", "2호관" 등 - 다양한 패턴으로 매칭
                    building_keywords.append(building_name_clean)  # "1호관 (대학본부)" -> "1호관"
                    building_keywords.append(building_name_clean.replace('호관', '').strip())  # "1"
                    # 숫자만 추출
                    numbers = re.findall(r'\d+', building_name_clean)
                    if numbers:
                        building_keywords.extend(numbers)  # "1", "2" 등
                else:
                    # "도서관" 등
                    building_keywords.append(building_name)
                    building_keywords.append(building_name.replace('도서관', '도서').strip())
                
                # 질문에서 건물명 찾기
                found = False
                for keyword in building_keywords:
                    if keyword and (keyword.lower() in user_lower or 
                                   any(kw in user_lower for kw in keyword.lower().split() if len(kw) > 1)):
                        found = True
                        break
                
                if found:
                    matched_building = building
                    break
            
            # 2단계: 건물명 매칭 실패 시 시설명으로 역추적
            if not matched_building:
                for building in campus_data.get('campus_facilities', []):
                    # 각 층의 시설 목록 확인
                    for floor_info in building.get('floors', []):
                        facilities = floor_info.get('facilities', [])
                        # 질문에 포함된 시설명 찾기
                        for facility in facilities:
                            # 시설명의 주요 키워드 추출 (예: "컴퓨터공학부사무실" -> "컴퓨터공학부", "컴퓨터")
                            facility_lower = facility.lower()
                            # 시설명이 질문에 포함되어 있는지 확인
                            if facility_lower in user_lower:
                                matched_building = building
                                break
                            # 부분 매칭 (예: "컴퓨터공학부" -> "컴퓨터", "공학부")
                            facility_keywords = facility_lower.replace('사무실', '').replace('실', '').split()
                            for keyword in facility_keywords:
                                if len(keyword) > 2 and keyword in user_lower:
                                    matched_building = building
                                    break
                        if matched_building:
                            break
                    if matched_building:
                        break
            
            # 매칭된 건물이 있으면 이미지 URL과 시설 정보 추출
            if matched_building:
                building_name = matched_building.get('building_name', '')
                # 이미지 URL 가져오기
                image_url = matched_building.get('image_url', None)
                
                # 시설 정보 추출
                facilities_list = []
                for floor_info in matched_building.get('floors', []):
                    floor = floor_info.get('floor', '')
                    facilities = floor_info.get('facilities', [])
                    if facilities:
                        facilities_list.append(f"{floor}: {', '.join(facilities)}")
                if facilities_list:
                    extraInfo = f"{building_name} 시설 정보:\n" + "\n".join(facilities_list[:5])  # 최대 5개 층만 표시
        
        return jsonify({
            'success': True,
            'title': title,
            'description': description,
            'extraInfo': extraInfo,
            'imageUrl': image_url,
            'fullResponse': bot_response
        })
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            'success': False,
            'error': '서버 오류가 발생했습니다.',
            'title': '오류 발생',
            'description': '죄송합니다. 일시적인 오류가 발생했습니다.',
            'extraInfo': '잠시 후 다시 시도해주세요.'
        }), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5001, debug=True)
