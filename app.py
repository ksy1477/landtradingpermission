from flask import Flask, render_template, jsonify, request
import requests
import config

app = Flask(__name__)

# VWorld API 기본 URL
VWORLD_BASE_URL = 'https://api.vworld.kr/req/data'


@app.route('/')
def index():
    """메인 페이지 렌더링"""
    return render_template('index.html')


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

        # 응답 구조 파싱
        if 'landUses' in data:
            items = data.get('landUses', {}).get('landUse', [])
            if not isinstance(items, list):
                items = [items]
            for item in items:
                usage_name = item.get('prposAreaDstrcNm', '')
                code_name = item.get('prposAreaDstrcCodeNm', '') or item.get('cnflcAtNm', '')

                if usage_name:
                    if '용도지구' in code_name or '지구' in usage_name:
                        if usage_name not in result['usage_districts']:
                            result['usage_districts'].append(usage_name)
                    elif '용도지역' in code_name or '지역' in usage_name:
                        if usage_name not in result['usage_areas']:
                            result['usage_areas'].append(usage_name)
                    else:
                        if usage_name not in result['usage_areas']:
                            result['usage_areas'].append(usage_name)
        elif 'landUseAttrVOList' in data:
            items = data.get('landUseAttrVOList', [])
            if not isinstance(items, list):
                items = [items]
            for item in items:
                usage_name = item.get('prposAreaDstrcNm', '') or item.get('uname', '')
                code_name = item.get('prposAreaDstrcCodeNm', '') or item.get('cnflcAtNm', '')

                if usage_name:
                    if '용도지구' in code_name or '지구' in usage_name:
                        if usage_name not in result['usage_districts']:
                            result['usage_districts'].append(usage_name)
                    else:
                        if usage_name not in result['usage_areas']:
                            result['usage_areas'].append(usage_name)
        elif 'response' in data:
            resp = data.get('response', {})
            if resp.get('status') == 'OK':
                items = resp.get('result', {}).get('items', [])
                if not isinstance(items, list):
                    items = [items]
                for item in items:
                    usage_name = item.get('prposAreaDstrcNm', '')
                    code_name = item.get('prposAreaDstrcCodeNm', '')

                    if usage_name:
                        if '용도지구' in code_name:
                            if usage_name not in result['usage_districts']:
                                result['usage_districts'].append(usage_name)
                        else:
                            if usage_name not in result['usage_areas']:
                                result['usage_areas'].append(usage_name)
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
    """건축물대장 전유부 조회 (동/호수별 대지권 지분)"""
    pnu = request.args.get('pnu', '')
    dong = request.args.get('dong', '')
    ho = request.args.get('ho', '')

    if not pnu or len(pnu) < 19:
        return jsonify({'error': 'PNU 코드가 필요합니다.'})

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

        # 동 정보가 있으면 추가
        if dong:
            params['dongNm'] = dong

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

            # 호수로 필터링
            for item in items:
                unit_dong = item.get('dongNm', '')
                unit_ho = item.get('hoNm', '')

                # 전유부 정보만 (exposPubuseGbCdNm이 '전유'인 것)
                gb_nm = item.get('exposPubuseGbCdNm', '')

                unit_info = {
                    'dong': unit_dong,
                    'ho': unit_ho,
                    'area': item.get('area', ''),  # 면적
                    'gb': gb_nm,  # 전유/공용 구분
                    'main_atch_gb': item.get('mainAtchGbCdNm', ''),  # 주/부속 구분
                    'purps': item.get('purpsCdNm', ''),  # 용도
                    'land_ratio_shr_numrtr': item.get('splotNmplcAr', ''),  # 대지권비율 분자 (대지권면적)
                }
                result['units'].append(unit_info)

                # 요청한 동/호에 해당하는 전유부 찾기
                if ho and unit_ho == ho and (not dong or unit_dong == dong):
                    if '전유' in gb_nm:
                        result['exclusive_area'] = item.get('area', '')  # 전유면적
                        result['land_share'] = item.get('splotNmplcAr', '')  # 대지권면적

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


if __name__ == '__main__':
    app.run(debug=True, port=5000)
