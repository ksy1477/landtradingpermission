import requests
import config
import re

pnu = "1130510100113530000"  # SK북한산시티 미아동 1353
dong = "128"
ho = "1503"

def normalize(s):
    if not s:
        return ''
    nums = re.findall(r'\d+', str(s))
    return nums[0] if nums else str(s).strip()

dong_normalized = normalize(dong)
ho_normalized = normalize(ho)

print(f"=== 검색: {dong}동 {ho}호 ===\n")

print("=== VWorld API (대지권 비율) ===")
url = 'https://api.vworld.kr/ned/data/buldHoCoList'
for page in range(1, 10):
    params = {
        'key': config.VWORLD_API_KEY,
        'pnu': pnu,
        'format': 'json',
        'numOfRows': 1000,
        'pageNo': page
    }
    resp = requests.get(url, params=params, timeout=15)
    data = resp.json()

    if 'ldaregVOList' in data:
        items = data['ldaregVOList'].get('ldaregVOList', [])
        if not items:
            break
        for item in items:
            item_dong = normalize(item.get('buldDongNm', ''))
            item_ho = normalize(item.get('buldHoNm', ''))
            if item_dong == dong_normalized and item_ho == ho_normalized:
                print(f"FOUND! 동:{item.get('buldDongNm')}, 호:{item.get('buldHoNm')}, 대지권:{item.get('ldaQotaRate')}")
                break
        else:
            continue
        break
    else:
        break
else:
    print("VWorld에서 해당 동/호수를 찾지 못함")

print("\n=== Building API (전용면적) ===")
sigungu_cd = pnu[0:5]
bjdong_cd = pnu[5:10]
bun = pnu[11:15]
ji = pnu[15:19]

url2 = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo'

# 동/호수 형식 시도
dong_variants = [f"{dong_normalized}동", dong_normalized]
ho_variants = [ho_normalized, f"{ho_normalized}호"]

for dv in dong_variants:
    for hv in ho_variants:
        params2 = {
            'serviceKey': config.BUILDING_API_KEY,
            'sigunguCd': sigungu_cd,
            'bjdongCd': bjdong_cd,
            'bun': bun,
            'ji': ji,
            'dongNm': dv,
            'hoNm': hv,
            'numOfRows': 10,
            'pageNo': 1,
            '_type': 'json'
        }
        resp2 = requests.get(url2, params=params2, timeout=15)
        data2 = resp2.json()

        if 'response' in data2:
            items = data2['response']['body']['items'].get('item', [])
            if items:
                if not isinstance(items, list):
                    items = [items]
                for it in items:
                    if it.get('exposPubuseGbCdNm') == '전유':
                        print(f"FOUND! dongNm={dv}, hoNm={hv}")
                        print(f"  동:{it.get('dongNm')}, 호:{it.get('hoNm')}, 면적:{it.get('area')}㎡, 구조:{it.get('strctCdNm')}")
                        break
                else:
                    continue
                break
        else:
            continue
        break
    else:
        continue
    break
else:
    print("Building API에서 해당 동/호수를 찾지 못함")
