from flask import Flask, render_template, jsonify, request, send_file
import requests
import config
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

app = Flask(__name__)

# VWorld API 기본 URL
VWORLD_BASE_URL = 'https://api.vworld.kr/req/data'


@app.route('/')
def index():
    """메인 페이지 렌더링"""
    return render_template('index.html')


@app.route('/api/debug')
def debug_info():
    """환경변수 및 API 연결 상태 확인"""
    import os
    result = {
        'env_vars': {
            'ADDRESS_API_KEY': 'SET' if config.ADDRESS_API_KEY else 'NOT SET',
            'VWORLD_API_KEY': 'SET' if config.VWORLD_API_KEY else 'NOT SET',
            'BUILDING_API_KEY': 'SET' if config.BUILDING_API_KEY else 'NOT SET',
        },
        'api_tests': {}
    }

    # VWorld API 테스트
    try:
        test_url = 'https://api.vworld.kr/ned/data/ladfrlList'
        test_params = {
            'key': config.VWORLD_API_KEY,
            'pnu': '1168010600107060013',  # 테스트용 PNU
            'format': 'json',
            'numOfRows': 1,
            'pageNo': 1
        }
        test_resp = requests.get(test_url, params=test_params, timeout=10)
        result['api_tests']['vworld'] = {
            'status_code': test_resp.status_code,
            'response': test_resp.json() if test_resp.status_code == 200 else test_resp.text[:500]
        }
    except Exception as e:
        result['api_tests']['vworld'] = {'error': str(e)}

    return jsonify(result)


@app.route('/api/address/jibun')
def search_jibun():
    """지번주소로 토지정보 검색 (도로명주소 API 활용)"""
    address = request.args.get('address', '')
    if not address:
        return jsonify({'error': '주소가 필요합니다.'})

    try:
        # 행정안전부 도로명주소 API
        url = 'https://business.juso.go.kr/addrlink/addrLinkApi.do'
        params = {
            'confmKey': config.ADDRESS_API_KEY,
            'currentPage': 1,
            'countPerPage': 10,
            'keyword': address,
            'resultType': 'json'
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        results = []
        if 'results' in data and 'juso' in data['results']:
            for juso in data['results']['juso']:
                # PNU 코드 생성: 법정동코드(10자리) + 대지/산(1자리) + 본번(4자리) + 부번(4자리)
                bjd_code = juso.get('admCd', '')
                mt = '2' if '산' in juso.get('jibunAddr', '') else '1'

                # 지번 파싱
                lnbr_mnnm = juso.get('lnbrMnnm', '0').zfill(4)
                lnbr_slno = juso.get('lnbrSlno', '0').zfill(4)

                pnu = f"{bjd_code}{mt}{lnbr_mnnm}{lnbr_slno}"

                results.append({
                    'road_address': juso.get('roadAddr', ''),
                    'jibun_address': juso.get('jibunAddr', ''),
                    'bjd_code': bjd_code,
                    'pnu': pnu,
                    'sido': juso.get('siNm', ''),
                    'sigungu': juso.get('sggNm', ''),
                    'dong': juso.get('emdNm', ''),
                    'jibun': f"{juso.get('lnbrMnnm', '')}-{juso.get('lnbrSlno', '')}" if juso.get('lnbrSlno', '0') != '0' else juso.get('lnbrMnnm', '')
                })

        return jsonify({'results': results})
    except Exception as e:
        return jsonify({'error': str(e), 'results': []})


@app.route('/api/land/info')
def get_land_info():
    """토지임야 정보 조회 (VWorld ladfrlList API)"""
    pnu = request.args.get('pnu', '')
    if not pnu:
        return jsonify({'error': 'PNU 코드가 필요합니다.'})

    try:
        # VWorld 토지임야목록 조회 API
        url = 'https://api.vworld.kr/ned/data/ladfrlList'
        params = {
            'key': config.VWORLD_API_KEY,
            'pnu': pnu,
            'format': 'json',
            'numOfRows': 1,
            'pageNo': 1
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        result = {}

        # 응답 구조 파싱
        if 'ladfrlVOList' in data:
            # ladfrlVOList 형식
            items = data.get('ladfrlVOList', {}).get('ladfrlVOList', [])
            if not items:
                items = data.get('ladfrlVOList', [])
            if items:
                item = items[0] if isinstance(items, list) else items
                jimok_code = item.get('lndcgrCode', '') or item.get('jimok', '')
                result = {
                    'jibun': item.get('lnbrMnnm', '') + ('-' + item.get('lnbrSlno', '') if item.get('lnbrSlno', '0') != '0' else ''),
                    'jimok': jimok_code,
                    'jimok_name': get_jimok_name(jimok_code),
                    'area': item.get('lndpclAr', '') or item.get('area', ''),
                    'pnu': item.get('pnu', pnu)
                }
        elif 'landFrls' in data:
            # landFrls 형식
            items = data.get('landFrls', {}).get('landFrl', [])
            if items:
                item = items[0] if isinstance(items, list) else items
                jimok_code = item.get('lndcgrCode', '') or item.get('lndcgrCodeNm', '')
                result = {
                    'jibun': item.get('mnnmSlno', ''),
                    'jimok': jimok_code,
                    'jimok_name': get_jimok_name(jimok_code) if jimok_code.isdigit() or len(jimok_code) <= 2 else jimok_code,
                    'area': item.get('lndpclAr', ''),
                    'pnu': item.get('pnu', pnu)
                }
        elif 'response' in data:
            # response 형식
            resp = data.get('response', {})
            if resp.get('status') == 'OK':
                result_data = resp.get('result', {})
                items = result_data.get('items', []) or result_data.get('ladfrlVOList', [])
                if items:
                    item = items[0] if isinstance(items, list) else items
                    jimok_code = item.get('lndcgrCode', '') or item.get('lndcgrCodeNm', '')
                    result = {
                        'jibun': item.get('mnnmSlno', '') or f"{item.get('lnbrMnnm', '')}-{item.get('lnbrSlno', '')}",
                        'jimok': jimok_code,
                        'jimok_name': get_jimok_name(jimok_code),
                        'area': item.get('lndpclAr', ''),
                        'pnu': item.get('pnu', pnu)
                    }
            else:
                error_msg = resp.get('error', {}).get('text', '조회 실패')
                result = {'error': error_msg, 'raw': data}
        else:
            # 알 수 없는 형식 - 디버깅용
            result = {'error': '응답 형식 확인 필요', 'raw_response': data}

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/land/price')
def get_land_price():
    """개별공시지가 조회 (VWorld API - getIndvdLandPriceAttr)"""
    pnu = request.args.get('pnu', '')
    if not pnu:
        return jsonify({'error': 'PNU 코드가 필요합니다.'})

    try:
        # VWorld 개별공시지가 API
        url = 'https://api.vworld.kr/ned/data/getIndvdLandPriceAttr'
        params = {
            'key': config.VWORLD_API_KEY,
            'pnu': pnu,
            'stdrYear': '2024',
            'format': 'json',
            'numOfRows': 1,
            'pageNo': 1
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        result = {}
        # 응답 구조 확인 및 파싱
        if 'indvdLandPrices' in data:
            # field 배열 또는 indvdLandPrice 배열 확인
            items = data.get('indvdLandPrices', {}).get('field', [])
            if not items:
                items = data.get('indvdLandPrices', {}).get('indvdLandPrice', [])
            if items:
                item = items[0] if isinstance(items, list) else items
                result = {
                    'price': item.get('pblntfPclnd', ''),
                    'year': item.get('stdrYear', '2024'),
                    'pnu': item.get('pnu', pnu)
                }
        elif 'response' in data:
            # 다른 응답 형식 처리
            resp = data.get('response', {})
            if resp.get('status') == 'OK':
                result_data = resp.get('result', {})
                if 'featureCollection' in result_data:
                    features = result_data.get('featureCollection', {}).get('features', [])
                    if features:
                        props = features[0].get('properties', {})
                        result = {
                            'price': props.get('pblntfPclnd', ''),
                            'year': props.get('stdrYear', '2024'),
                            'pnu': props.get('pnu', pnu)
                        }
                else:
                    # 직접 결과가 있는 경우
                    result = {
                        'price': result_data.get('pblntfPclnd', ''),
                        'year': result_data.get('stdrYear', '2024'),
                        'pnu': pnu
                    }
            else:
                error_msg = resp.get('error', {}).get('text', '조회 실패')
                result = {'error': error_msg}
        else:
            # 원본 응답 반환 (디버깅용)
            result = {'raw_response': data, 'error': '응답 형식 확인 필요'}

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/land/usage')
def get_land_usage():
    """토지이용규제정보 조회 (VWorld getLandUseAttr API)"""
    pnu = request.args.get('pnu', '')
    if not pnu:
        return jsonify({'error': 'PNU 코드가 필요합니다.'})

    try:
        # VWorld 토지이용규제정보 속성조회 API
        url = 'https://api.vworld.kr/ned/data/getLandUseAttr'
        params = {
            'key': config.VWORLD_API_KEY,
            'pnu': pnu,
            'format': 'json',
            'numOfRows': 100,
            'pageNo': 1
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        result = {'usage_areas': [], 'usage_districts': []}

        # 용도지역 키워드 (주요 용도지역)
        area_keywords = ['주거지역', '상업지역', '공업지역', '녹지지역', '관리지역', '농림지역', '자연환경보전지역', '도시지역']
        # 용도지구 키워드
        district_keywords = ['지구', '구역', '권역']

        def classify_usage(name, cnflc_at):
            """용도지역/지구 분류 - 포함(1)된 것만"""
            if cnflc_at != '1':  # 포함된 것만 (저촉, 접함 제외)
                return None, None

            # 용도지역 판단
            for keyword in area_keywords:
                if keyword in name:
                    return 'area', name
            # 용도지구 판단
            for keyword in district_keywords:
                if keyword in name:
                    return 'district', name
            return 'other', name

        # 응답 구조 파싱 - landUses.field 형식 (실제 API 응답)
        if 'landUses' in data:
            # field 배열 또는 landUse 배열 확인
            items = data.get('landUses', {}).get('field', [])
            if not items:
                items = data.get('landUses', {}).get('landUse', [])
            if not isinstance(items, list):
                items = [items] if items else []

            for item in items:
                # prposAreaDstrcCodeNm에 용도지역명이 있음
                usage_name = item.get('prposAreaDstrcCodeNm', '') or item.get('prposAreaDstrcNm', '')
                cnflc_at = item.get('cnflcAt', '')  # 1: 포함, 2: 저촉, 3: 접함

                if usage_name:
                    category, name = classify_usage(usage_name, cnflc_at)
                    if category == 'area':
                        if name not in result['usage_areas']:
                            result['usage_areas'].append(name)
                    elif category == 'district':
                        if name not in result['usage_districts']:
                            result['usage_districts'].append(name)

        elif 'landUseAttrVOList' in data:
            items = data.get('landUseAttrVOList', [])
            if not isinstance(items, list):
                items = [items]
            for item in items:
                usage_name = item.get('prposAreaDstrcCodeNm', '') or item.get('prposAreaDstrcNm', '') or item.get('uname', '')
                cnflc_at = item.get('cnflcAt', '1')

                if usage_name:
                    category, name = classify_usage(usage_name, cnflc_at)
                    if category == 'area':
                        if name not in result['usage_areas']:
                            result['usage_areas'].append(name)
                    elif category == 'district':
                        if name not in result['usage_districts']:
                            result['usage_districts'].append(name)

        elif 'response' in data:
            resp = data.get('response', {})
            if resp.get('status') == 'OK':
                items = resp.get('result', {}).get('items', [])
                if not isinstance(items, list):
                    items = [items]
                for item in items:
                    usage_name = item.get('prposAreaDstrcCodeNm', '') or item.get('prposAreaDstrcNm', '')
                    cnflc_at = item.get('cnflcAt', '1')

                    if usage_name:
                        category, name = classify_usage(usage_name, cnflc_at)
                        if category == 'area':
                            if name not in result['usage_areas']:
                                result['usage_areas'].append(name)
                        elif category == 'district':
                            if name not in result['usage_districts']:
                                result['usage_districts'].append(name)
            else:
                result['error'] = resp.get('error', {}).get('text', '조회 실패')
        else:
            result['error'] = '응답 형식 확인 필요'
            result['raw_response'] = data

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/building/info')
def get_building_info():
    """건축물대장 정보 조회 (공공데이터포털 API)"""
    pnu = request.args.get('pnu', '')
    if not pnu or len(pnu) < 19:
        return jsonify({'error': 'PNU 코드가 필요합니다.'})

    try:
        # PNU에서 코드 추출
        # PNU: 시도(2) + 시군구(3) + 읍면동(3) + 리(2) + 산여부(1) + 본번(4) + 부번(4)
        sigungu_cd = pnu[0:5]  # 시군구코드 (5자리)
        bjdong_cd = pnu[5:10]  # 법정동코드 (5자리)
        bun = pnu[11:15]       # 본번 (4자리)
        ji = pnu[15:19]        # 부번 (4자리)

        # 건축물대장 표제부 조회
        url = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo'
        params = {
            'serviceKey': config.BUILDING_API_KEY,
            'sigunguCd': sigungu_cd,
            'bjdongCd': bjdong_cd,
            'bun': bun,
            'ji': ji,
            'numOfRows': 10,
            'pageNo': 1,
            '_type': 'json'
        }

        response = requests.get(url, params=params, timeout=10)
        data = response.json()

        result = {'buildings': []}

        # 응답 파싱
        if 'response' in data:
            body = data.get('response', {}).get('body', {})
            items = body.get('items', {}).get('item', [])

            if not isinstance(items, list):
                items = [items] if items else []

            for item in items:
                building = {
                    'name': item.get('bldNm', ''),  # 건물명 (아파트 단지명)
                    'dong': item.get('dongNm', ''),  # 동명
                    'structure': item.get('strctCdNm', ''),  # 구조코드명 (철근콘크리트구조 등)
                    'main_purpose': item.get('mainPurpsCdNm', ''),  # 주용도
                    'total_area': item.get('totArea', ''),  # 연면적
                    'ground_floor': item.get('grndFlrCnt', ''),  # 지상층수
                    'underground_floor': item.get('ugrndFlrCnt', ''),  # 지하층수
                    'use_apr_day': item.get('useAprDay', ''),  # 사용승인일
                    'plat_area': item.get('platArea', ''),  # 대지면적
                }
                result['buildings'].append(building)

            # 대표 건물 정보 (첫 번째)
            if result['buildings']:
                result['main_building'] = result['buildings'][0]
        else:
            result['error'] = '응답 형식 확인 필요'
            result['raw_response'] = data

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/building/unit')
def get_building_unit():
    """건축물대장 전유부 조회 (동/호수별 대지권 지분) - VWorld API 우선 사용"""
    pnu = request.args.get('pnu', '')
    dong = request.args.get('dong', '')
    ho = request.args.get('ho', '')

    # 디버그 로그
    print(f"[DEBUG] /api/building/unit called: pnu={pnu}, dong={dong}, ho={ho}")

    if not pnu or len(pnu) < 19:
        return jsonify({'error': 'PNU 코드가 필요합니다.'})

    # 숫자만 추출하는 정규화 함수
    import re
    def normalize(s):
        if not s:
            return ''
        nums = re.findall(r'\d+', str(s))
        return nums[0] if nums else str(s).strip()

    dong_normalized = normalize(dong)
    ho_normalized = normalize(ho)

    # 1. VWorld 건물 호 조회 API로 대지권 비율 조회 (우선)
    # 페이지네이션 지원 - 모든 페이지 검색
    try:
        vworld_url = 'https://api.vworld.kr/ned/data/buldHoCoList'
        page_no = 1
        max_pages = 5  # 최대 5페이지까지 검색

        while page_no <= max_pages:
            vworld_params = {
                'key': config.VWORLD_API_KEY,
                'pnu': pnu,
                'format': 'json',
                'numOfRows': 1000,
                'pageNo': page_no
            }
            vworld_response = requests.get(vworld_url, params=vworld_params, timeout=15)
            vworld_data = vworld_response.json()

            # VWorld 응답에서 대지권 비율 찾기
            if 'ldaregVOList' in vworld_data:
                vo_list = vworld_data.get('ldaregVOList', {})
                items = vo_list.get('ldaregVOList', [])
                total_count = int(vo_list.get('totalCount', 0))

                if not isinstance(items, list):
                    items = [items] if items else []

                for item in items:
                    item_dong = normalize(item.get('buldDongNm', ''))
                    item_ho = normalize(item.get('buldHoNm', ''))

                    # 동/호 매칭
                    dong_match = (not dong_normalized) or (dong_normalized == item_dong)
                    ho_match = ho_normalized and (ho_normalized == item_ho)

                    if dong_match and ho_match:
                        lda_quota_rate = item.get('ldaQotaRate', '')  # 대지권비율 (예: "22.25/41222.9")
                        if lda_quota_rate:
                            parts = lda_quota_rate.split('/')
                            land_share = parts[0] if len(parts) > 0 else ''
                            land_area = parts[1] if len(parts) > 1 else ''

                            # 건축물대장에서 전용면적, 구조 추가 조회
                            exclusive_area = None
                            structure = None
                            try:
                                sigungu_cd = pnu[0:5]
                                bjdong_cd = pnu[5:10]
                                bun = pnu[11:15]
                                ji = pnu[15:19]

                                # 표제부에서 구조 조회
                                title_url = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo'
                                title_params = {
                                    'serviceKey': config.BUILDING_API_KEY,
                                    'sigunguCd': sigungu_cd,
                                    'bjdongCd': bjdong_cd,
                                    'bun': bun,
                                    'ji': ji,
                                    'numOfRows': 1,
                                    'pageNo': 1,
                                    '_type': 'json'
                                }
                                title_resp = requests.get(title_url, params=title_params, timeout=10)
                                title_data = title_resp.json()
                                if 'response' in title_data:
                                    title_items = title_data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                                    if title_items:
                                        title_item = title_items[0] if isinstance(title_items, list) else title_items
                                        structure = title_item.get('strctCdNm', '')

                                # 전유공용면적에서 전용면적 조회 (동/호수 필터 사용)
                                area_url = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo'

                                # 동 이름 형식 시도: "103동", "103" 등
                                dong_variants = [f"{dong_normalized}동", dong_normalized, dong] if dong_normalized else ['']
                                # 호수 형식 시도: "904", "904호" 등
                                ho_variants = [ho_normalized, f"{ho_normalized}호", ho] if ho_normalized else ['']

                                found_area = False
                                for dong_variant in dong_variants:
                                    if found_area:
                                        break
                                    for ho_variant in ho_variants:
                                        if found_area:
                                            break
                                        area_params = {
                                            'serviceKey': config.BUILDING_API_KEY,
                                            'sigunguCd': sigungu_cd,
                                            'bjdongCd': bjdong_cd,
                                            'bun': bun,
                                            'ji': ji,
                                            'numOfRows': 100,
                                            'pageNo': 1,
                                            '_type': 'json'
                                        }
                                        # 동/호수 필터 추가
                                        if dong_variant:
                                            area_params['dongNm'] = dong_variant
                                        if ho_variant:
                                            area_params['hoNm'] = ho_variant

                                        area_resp = requests.get(area_url, params=area_params, timeout=15)
                                        area_data = area_resp.json()

                                        if 'response' in area_data:
                                            area_items = area_data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
                                            if not isinstance(area_items, list):
                                                area_items = [area_items] if area_items else []

                                            if area_items:
                                                # 전유 면적 중 가장 큰 것 (전용면적)
                                                max_area = 0
                                                for area_item in area_items:
                                                    # 전유(専有) 면적만 선택
                                                    gb = area_item.get('exposPubuseGbCdNm', '')
                                                    if '전유' in gb:
                                                        area_val = float(area_item.get('area', 0) or 0)
                                                        if area_val > max_area:
                                                            max_area = area_val
                                                if max_area > 0:
                                                    exclusive_area = max_area
                                                    found_area = True
                            except Exception as ex:
                                print(f"건축물대장 추가 조회 오류: {ex}")

                            return jsonify({
                                'building_name': item.get('buldNm', ''),
                                'dong': item.get('buldDongNm', ''),
                                'ho': item.get('buldHoNm', ''),
                                'floor': item.get('buldFloorNm', ''),
                                'land_share': land_share,  # 대지권 면적
                                'land_area': land_area,    # 전체 대지면적
                                'land_quota_rate': lda_quota_rate,  # 원본 비율
                                'exclusive_area': exclusive_area,  # 전용면적
                                'structure': structure,  # 구조
                                'source': 'vworld'
                            })

                # 더 이상 페이지가 없으면 종료
                if len(items) == 0 or page_no * 1000 >= total_count:
                    break
                page_no += 1
            else:
                break

    except Exception as e:
        print(f"VWorld API 오류: {e}")

    # 2. VWorld에서 못 찾으면 기존 건축물대장 API 사용

    try:
        # PNU에서 코드 추출
        sigungu_cd = pnu[0:5]
        bjdong_cd = pnu[5:10]
        bun = pnu[11:15]
        ji = pnu[15:19]

        # 건축물대장 전유공용면적 조회
        url = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo'
        params = {
            'serviceKey': config.BUILDING_API_KEY,
            'sigunguCd': sigungu_cd,
            'bjdongCd': bjdong_cd,
            'bun': bun,
            'ji': ji,
            'numOfRows': 1000,
            'pageNo': 1,
            '_type': 'json'
        }

        # 동 파라미터는 전달하지 않음 (정확한 매칭 필요하므로 코드에서 필터링)
        # 전체 데이터를 가져온 후 필터링

        response = requests.get(url, params=params, timeout=15)
        data = response.json()

        result = {
            'units': [],
            'land_area': None,
            'land_share': None,
            'exclusive_area': None
        }

        if 'response' in data:
            body = data.get('response', {}).get('body', {})
            items = body.get('items', {}).get('item', [])

            if not isinstance(items, list):
                items = [items] if items else []

            # 동/호 정규화 함수 (숫자만 추출)
            import re

            def normalize_dong(d):
                if not d:
                    return ''
                # 숫자만 추출
                nums = re.findall(r'\d+', str(d))
                return nums[0] if nums else d.strip()

            def normalize_ho(h):
                if not h:
                    return ''
                # 숫자만 추출
                nums = re.findall(r'\d+', str(h))
                return nums[0] if nums else h.strip()

            dong_normalized = normalize_dong(dong)
            ho_normalized = normalize_ho(ho)

            # 매칭된 전유부 데이터 수집
            matched_units = []

            for item in items:
                unit_dong = item.get('dongNm', '')
                unit_ho = item.get('hoNm', '')
                gb_nm = item.get('exposPubuseGbCdNm', '')
                area = item.get('area', '')
                main_atch = item.get('mainAtchGbCdNm', '')

                unit_info = {
                    'dong': unit_dong,
                    'ho': unit_ho,
                    'area': area,
                    'gb': gb_nm,
                    'main_atch_gb': main_atch,
                    'purps': item.get('purpsCdNm', ''),
                }
                result['units'].append(unit_info)

                # 동/호 매칭 (부분 매칭 허용)
                unit_dong_normalized = normalize_dong(unit_dong)
                unit_ho_normalized = normalize_ho(unit_ho)

                dong_match = (not dong_normalized) or (dong_normalized in unit_dong_normalized) or (unit_dong_normalized in dong_normalized)
                ho_match = ho_normalized and (ho_normalized == unit_ho_normalized)

                if dong_match and ho_match:
                    matched_units.append({
                        'area': float(area) if area else 0,
                        'gb': gb_nm,
                        'main_atch': main_atch
                    })

            # 매칭된 전유부 중 가장 큰 면적을 전용면적으로
            if matched_units:
                max_area = max(u['area'] for u in matched_units)
                result['exclusive_area'] = max_area

            # 대지권 비율은 등기부등본에서만 확인 가능 (API 미제공)
            # 전용면적 / 전체연면적 비율로 대지권면적 추정 (참고용)
            result['land_share'] = None  # 등기부등본 확인 필요

            # 표제부에서 대지면적 조회
            title_url = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo'
            title_params = {
                'serviceKey': config.BUILDING_API_KEY,
                'sigunguCd': sigungu_cd,
                'bjdongCd': bjdong_cd,
                'bun': bun,
                'ji': ji,
                'numOfRows': 1,
                'pageNo': 1,
                '_type': 'json'
            }
            title_response = requests.get(title_url, params=title_params, timeout=10)
            title_data = title_response.json()

            if 'response' in title_data:
                title_body = title_data.get('response', {}).get('body', {})
                title_items = title_body.get('items', {}).get('item', [])
                if title_items:
                    title_item = title_items[0] if isinstance(title_items, list) else title_items
                    result['land_area'] = title_item.get('platArea', '')  # 대지면적
                    result['building_name'] = title_item.get('bldNm', '')  # 건물명
                    result['structure'] = title_item.get('strctCdNm', '')  # 구조
                    result['total_area'] = title_item.get('totArea', '')  # 연면적
                    result['ground_floor'] = title_item.get('grndFlrCnt', '')  # 지상층
                    result['underground_floor'] = title_item.get('ugrndFlrCnt', '')  # 지하층

        else:
            result['error'] = '응답 형식 확인 필요'
            result['raw_response'] = data

        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)})


@app.route('/api/land/all')
def get_land_all():
    """토지 정보 통합 조회 (토지특성 + 공시지가 + 이용계획)"""
    pnu = request.args.get('pnu', '')
    if not pnu:
        return jsonify({'error': 'PNU 코드가 필요합니다.'})

    result = {
        'pnu': pnu,
        'info': {},
        'price': {},
        'usage': {'usage_areas': [], 'usage_districts': []}
    }

    # 토지임야 정보 (ladfrlList API)
    try:
        land_url = 'https://api.vworld.kr/ned/data/ladfrlList'
        params = {
            'key': config.VWORLD_API_KEY,
            'pnu': pnu,
            'format': 'json',
            'numOfRows': 1,
            'pageNo': 1
        }
        response = requests.get(land_url, params=params, timeout=10)
        data = response.json()

        if 'ladfrlVOList' in data:
            items = data.get('ladfrlVOList', {}).get('ladfrlVOList', [])
            if not items:
                items = data.get('ladfrlVOList', [])
            if items:
                item = items[0] if isinstance(items, list) else items
                jimok_code = item.get('lndcgrCode', '') or item.get('jimok', '')
                result['info'] = {
                    'jibun': item.get('lnbrMnnm', '') + ('-' + item.get('lnbrSlno', '') if item.get('lnbrSlno', '0') != '0' else ''),
                    'jimok': jimok_code,
                    'jimok_name': get_jimok_name(jimok_code),
                    'area': item.get('lndpclAr', '') or item.get('area', '')
                }
        elif 'landFrls' in data:
            items = data.get('landFrls', {}).get('landFrl', [])
            if items:
                item = items[0] if isinstance(items, list) else items
                jimok_code = item.get('lndcgrCode', '') or item.get('lndcgrCodeNm', '')
                result['info'] = {
                    'jibun': item.get('mnnmSlno', ''),
                    'jimok': jimok_code,
                    'jimok_name': get_jimok_name(jimok_code) if jimok_code.isdigit() or len(jimok_code) <= 2 else jimok_code,
                    'area': item.get('lndpclAr', '')
                }
    except Exception as e:
        result['info']['error'] = str(e)

    # 개별공시지가 (getIndvdLandPriceAttr API)
    try:
        price_url = 'https://api.vworld.kr/ned/data/getIndvdLandPriceAttr'
        params = {
            'key': config.VWORLD_API_KEY,
            'pnu': pnu,
            'stdrYear': '2024',
            'format': 'json',
            'numOfRows': 1,
            'pageNo': 1
        }
        response = requests.get(price_url, params=params, timeout=10)
        data = response.json()

        if 'indvdLandPrices' in data:
            items = data.get('indvdLandPrices', {}).get('indvdLandPrice', [])
            if items:
                item = items[0] if isinstance(items, list) else items
                result['price'] = {
                    'price': item.get('pblntfPclnd', ''),
                    'year': item.get('stdrYear', '2024')
                }
        elif 'response' in data and data.get('response', {}).get('status') == 'OK':
            result_data = data.get('response', {}).get('result', {})
            result['price'] = {
                'price': result_data.get('pblntfPclnd', ''),
                'year': result_data.get('stdrYear', '2024')
            }
    except Exception as e:
        result['price']['error'] = str(e)

    # 토지이용규제정보 (getLandUseAttr API)
    try:
        usage_url = 'https://api.vworld.kr/ned/data/getLandUseAttr'
        params = {
            'key': config.VWORLD_API_KEY,
            'pnu': pnu,
            'format': 'json',
            'numOfRows': 100,
            'pageNo': 1
        }
        response = requests.get(usage_url, params=params, timeout=10)
        data = response.json()

        if 'landUses' in data:
            items = data.get('landUses', {}).get('landUse', [])
            if not isinstance(items, list):
                items = [items]
            for item in items:
                usage_name = item.get('prposAreaDstrcNm', '')
                code_name = item.get('prposAreaDstrcCodeNm', '') or item.get('cnflcAtNm', '')
                if usage_name:
                    if '용도지구' in code_name or '지구' in usage_name:
                        if usage_name not in result['usage']['usage_districts']:
                            result['usage']['usage_districts'].append(usage_name)
                    else:
                        if usage_name not in result['usage']['usage_areas']:
                            result['usage']['usage_areas'].append(usage_name)
        elif 'landUseAttrVOList' in data:
            items = data.get('landUseAttrVOList', [])
            if not isinstance(items, list):
                items = [items]
            for item in items:
                usage_name = item.get('prposAreaDstrcNm', '') or item.get('uname', '')
                code_name = item.get('prposAreaDstrcCodeNm', '') or item.get('cnflcAtNm', '')
                if usage_name:
                    if '용도지구' in code_name or '지구' in usage_name:
                        if usage_name not in result['usage']['usage_districts']:
                            result['usage']['usage_districts'].append(usage_name)
                    else:
                        if usage_name not in result['usage']['usage_areas']:
                            result['usage']['usage_areas'].append(usage_name)
    except Exception as e:
        result['usage']['error'] = str(e)

    return jsonify(result)


def get_jimok_name(code):
    """지목 코드를 명칭으로 변환"""
    jimok_codes = {
        '01': '전', '02': '답', '03': '과수원', '04': '목장용지',
        '05': '임야', '06': '광천지', '07': '염전', '08': '대',
        '09': '공장용지', '10': '학교용지', '11': '주차장', '12': '주유소용지',
        '13': '창고용지', '14': '도로', '15': '철도용지', '16': '제방',
        '17': '하천', '18': '구거', '19': '유지', '20': '양어장',
        '21': '수도용지', '22': '공원', '23': '체육용지', '24': '유원지',
        '25': '종교용지', '26': '사적지', '27': '묘지', '28': '잡종지',
        # 한글 코드도 지원
        '전': '전', '답': '답', '과': '과수원', '목': '목장용지',
        '임': '임야', '광': '광천지', '염': '염전', '대': '대',
        '장': '공장용지', '학': '학교용지', '차': '주차장', '주': '주유소용지',
        '창': '창고용지', '도': '도로', '철': '철도용지', '제': '제방',
        '천': '하천', '구': '구거', '유': '유지', '양': '양어장',
        '수': '수도용지', '공': '공원', '체': '체육용지', '원': '유원지',
        '종': '종교용지', '사': '사적지', '묘': '묘지', '잡': '잡종지'
    }
    return jimok_codes.get(code, code)


@app.route('/api/generate-pdf', methods=['POST'])
def generate_pdf():
    """폼 데이터를 받아 PDF 생성"""
    try:
        data = request.get_json()

        # PDF 생성
        buffer = BytesIO()
        p = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # 한글 폰트 등록 (시스템 폰트 사용)
        try:
            # Windows 맑은고딕
            font_path = "C:/Windows/Fonts/malgun.ttf"
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont('MalgunGothic', font_path))
                font_name = 'MalgunGothic'
            else:
                font_name = 'Helvetica'
        except:
            font_name = 'Helvetica'

        # 페이지 설정
        margin_left = 15 * mm
        margin_top = height - 15 * mm
        line_height = 5 * mm

        # 제목
        p.setFont(font_name, 16)
        p.drawCentredString(width / 2, margin_top, "토지거래계약 허가 신청서")

        # 양식 헤더
        p.setFont(font_name, 8)
        p.drawString(margin_left, margin_top + 8 * mm, "■ 부동산 거래신고 등에 관한 법률 시행규칙 [별지 제9호서식]")

        y = margin_top - 15 * mm
        p.setFont(font_name, 9)

        # 매도인 정보
        p.drawString(margin_left, y, "【매도인】")
        y -= line_height
        p.drawString(margin_left + 10 * mm, y, f"①성명: {data.get('seller_name', '')}")
        p.drawString(margin_left + 70 * mm, y, f"②주민등록번호: {data.get('seller_ssn', '')}")
        y -= line_height
        p.drawString(margin_left + 10 * mm, y, f"③주소: {data.get('seller_address', '')}")
        p.drawString(margin_left + 100 * mm, y, f"전화: {data.get('seller_phone', '')}")

        # 매수인 정보
        y -= line_height * 2
        p.drawString(margin_left, y, "【매수인】")
        y -= line_height
        p.drawString(margin_left + 10 * mm, y, f"④성명: {data.get('buyer_name', '')}")
        p.drawString(margin_left + 70 * mm, y, f"⑤주민등록번호: {data.get('buyer_ssn', '')}")
        y -= line_height
        p.drawString(margin_left + 10 * mm, y, f"⑥주소: {data.get('buyer_address', '')}")
        p.drawString(margin_left + 100 * mm, y, f"전화: {data.get('buyer_phone', '')}")

        # 허가신청하는 권리
        y -= line_height * 2
        right_type = data.get('right_type', '소유권')
        p.drawString(margin_left, y, f"⑦허가신청하는 권리: {right_type}")

        # 토지에 관한 사항
        y -= line_height * 2
        p.setFont(font_name, 10)
        p.drawString(margin_left, y, "【토지에 관한 사항】")
        p.setFont(font_name, 9)
        y -= line_height

        p.drawString(margin_left + 5 * mm, y, f"⑧소재지: {data.get('land1_address', '')}")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"⑨지번: {data.get('land1_jibun', '')}")
        p.drawString(margin_left + 50 * mm, y, f"⑩법정지목: {data.get('land1_jimok_legal', '')}")
        p.drawString(margin_left + 90 * mm, y, f"⑪현실지목: {data.get('land1_jimok_actual', '')}")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"⑫면적(지분): {data.get('land1_area', '')}")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"⑬용도지역·지구: {data.get('land1_usage', '')}")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"⑭이용현황: {data.get('land1_current_use', '')}")

        # 권리설정현황
        y -= line_height * 2
        p.drawString(margin_left, y, f"⑮권리설정현황: {data.get('right_status', '')}")

        # 토지의 정착물에 관한 사항
        y -= line_height * 2
        p.setFont(font_name, 10)
        p.drawString(margin_left, y, "【토지의 정착물에 관한 사항】")
        p.setFont(font_name, 9)
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"⑯종류: {data.get('fixture1_type', '아파트')}")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"⑰정착물의 내용: {data.get('fixture1_content', '')}")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"⑱권리 종류: {data.get('fixture1_right_type', right_type)}")
        p.drawString(margin_left + 60 * mm, y, f"⑲권리 내용: {data.get('fixture1_right_content', '매매')}")

        # 이전 또는 설정하는 권리의 내용
        y -= line_height * 2
        p.setFont(font_name, 10)
        p.drawString(margin_left, y, "【이전 또는 설정하는 권리의 내용에 관한 사항】")
        p.setFont(font_name, 9)
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"⑳소유권의 이전 또는 설정의 형태: {data.get('transfer1_type', '매매')}")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"㉑존속기간: {data.get('transfer1_duration', '')}")
        p.drawString(margin_left + 60 * mm, y, f"㉒지대(연액): {data.get('transfer1_rent', '')}")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"㉓특기사항: {data.get('transfer1_note', '')}")

        # 계약예정금액에 관한 사항
        y -= line_height * 2
        p.setFont(font_name, 10)
        p.drawString(margin_left, y, "【계약예정금액에 관한 사항】")
        p.setFont(font_name, 9)
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"㉔지목(현실): {data.get('price1_jimok', '')}")
        p.drawString(margin_left + 50 * mm, y, f"㉕면적(㎡): {data.get('price1_area', '')}")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"㉖단가(원/㎡): {data.get('price1_unit', '')}")
        p.drawString(margin_left + 50 * mm, y, f"㉗토지 예정금액: {data.get('price1_land_total', '')}원")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"㉘정착물 종류: {data.get('price1_fixture_type', '')}")
        p.drawString(margin_left + 50 * mm, y, f"㉙정착물 예정금액: {data.get('price1_fixture_amount', '')}원")
        y -= line_height
        p.drawString(margin_left + 5 * mm, y, f"㉚예정금액 합계: {data.get('price1_total', '')}원")

        # 합계
        y -= line_height * 2
        p.drawString(margin_left + 5 * mm, y, f"【합계】 면적: {data.get('total_area', '')}㎡")
        p.drawString(margin_left + 60 * mm, y, f"토지금액: {data.get('total_land_amount', '')}원")
        y -= line_height
        p.drawString(margin_left + 60 * mm, y, f"정착물금액: {data.get('total_fixture_amount', '')}원")
        p.drawString(margin_left + 110 * mm, y, f"총액: {data.get('grand_total', '')}원")

        # 법률 문구
        y -= line_height * 3
        p.setFont(font_name, 8)
        p.drawString(margin_left, y, "「부동산 거래신고 등에 관한 법률」 제11조제1항, 같은 법 시행령 제9조제1항 및")
        y -= line_height
        p.drawString(margin_left, y, "같은 법 시행규칙 제9조에 따라 위와 같이 허가를 신청합니다.")

        # 날짜 및 서명
        y -= line_height * 2
        p.setFont(font_name, 10)
        app_year = data.get('app_year', '')
        app_month = data.get('app_month', '')
        app_day = data.get('app_day', '')
        p.drawCentredString(width / 2, y, f"{app_year}년 {app_month}월 {app_day}일")

        y -= line_height * 2
        p.drawString(width - 80 * mm, y, f"매도인: {data.get('seller_sign', '')} (서명 또는 인)")
        y -= line_height
        p.drawString(width - 80 * mm, y, f"매수인: {data.get('buyer_sign', '')} (서명 또는 인)")

        y -= line_height * 2
        p.setFont(font_name, 12)
        p.drawString(margin_left, y, "시장·군수·구청장 귀하")

        # PDF 완료
        p.showPage()
        p.save()

        buffer.seek(0)

        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='토지거래계약허가신청서.pdf'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(debug=True, port=5000)
