import requests
import config

pnu = "1168010600107060013"

print("=== VWorld API ===")
url = 'https://api.vworld.kr/ned/data/buldHoCoList'
params = {
    'key': config.VWORLD_API_KEY,
    'pnu': pnu,
    'format': 'json',
    'numOfRows': 10,
    'pageNo': 1
}
resp = requests.get(url, params=params, timeout=15)
print(resp.text[:1000])

print("\n=== Building API ===")
sigungu_cd = pnu[0:5]
bjdong_cd = pnu[5:10]
bun = pnu[11:15]
ji = pnu[15:19]
print(f"codes: {sigungu_cd}, {bjdong_cd}, {bun}, {ji}")

url2 = 'https://apis.data.go.kr/1613000/BldRgstHubService/getBrExposPubuseAreaInfo'
params2 = {
    'serviceKey': config.BUILDING_API_KEY,
    'sigunguCd': sigungu_cd,
    'bjdongCd': bjdong_cd,
    'bun': bun,
    'ji': ji,
    'numOfRows': 5,
    'pageNo': 1,
    '_type': 'json'
}
resp2 = requests.get(url2, params=params2, timeout=15)
print(resp2.text[:1500])
