from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import os
import json
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
    base_prompt = """당신은 동양미래대학교 캠퍼스 안내 챗봇입니다. 사용자가 캠퍼스 내 위치, 시설, 건물 등에 대해 질문하면 친절하고 정확하게 답변해주세요.

답변 시 다음 형식을 따라주세요:
1. 제목: 건물명 또는 시설명 (예: "7호관 3층", "도서관 4층")
2. 설명: 주요 정보를 간결하게 설명
3. 추가 정보: 층별 시설 목록이나 상세 안내

중요 사항:
- 반드시 제공된 JSON 데이터에 있는 정보만 사용하세요
- 건물명은 정확히 일치시켜주세요 (예: "1호관", "2호관", "도서관")
- 층수는 JSON 데이터에 명시된 형식 그대로 사용하세요 (예: "1F", "2F", "B1F")
- 시설명도 JSON 데이터에 있는 정확한 이름을 사용하세요
- JSON 데이터에 없는 정보는 추측하지 말고 "해당 정보를 찾을 수 없습니다"라고 답변하세요
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
        # GPT 응답에서 건물명이나 시설명을 추출하여 제목으로 사용
        lines = bot_response.strip().split('\n')
        title = "안내"
        description = bot_response
        extraInfo = ""
        
        # 첫 줄이나 두 번째 줄에서 건물명/시설명 추출 시도
        for i, line in enumerate(lines[:3]):
            line = line.strip()
            # 건물명 패턴 찾기 (예: "7호관", "도서관", "1호관 3층" 등)
            if any(keyword in line for keyword in ['호관', '도서관', '호관', '층']):
                # ":" 또는 "-" 뒤의 내용 제거
                if ':' in line:
                    title = line.split(':')[0].strip()
                elif '-' in line and len(line.split('-')[0]) < 20:
                    title = line.split('-')[0].strip()
                else:
                    # 첫 30자만 제목으로 사용
                    title = line[:30].strip()
                break
        
        # 설명은 전체 응답을 사용하되, 제목이 포함된 첫 줄은 제외
        if title != "안내" and lines:
            # 제목이 첫 줄에 있으면 나머지를 설명으로
            description = '\n'.join(lines[1:]).strip() if len(lines) > 1 else bot_response
        else:
            description = bot_response
        
        # 추가 정보: 건물/시설 관련 상세 정보 추출
        # JSON 데이터에서 관련 정보 찾기
        if campus_data:
            user_lower = user_message.lower()
            for building in campus_data.get('campus_facilities', []):
                building_name = building.get('building_name', '')
                # 건물명이 질문에 포함되어 있는지 확인
                if any(keyword in user_lower for keyword in building_name.lower().split()):
                    facilities_list = []
                    for floor_info in building.get('floors', []):
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
