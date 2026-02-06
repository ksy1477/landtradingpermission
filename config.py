# 공공데이터포털 API 키 설정
# 환경변수에서 읽거나 기본값 사용
import os

# 주소정보 조회 API (https://www.data.go.kr/data/15057017/openapi.do)
ADDRESS_API_KEY = os.environ.get("ADDRESS_API_KEY", "U01TX0FVVEgyMDI2MDIwMjE4NDYxNTExNzUyOTI=")

# VWorld API (https://www.vworld.kr)
# 토지특성정보, 개별공시지가, 토지이용계획 통합
VWORLD_API_KEY = os.environ.get("VWORLD_API_KEY", "691E9519-0EEA-38AD-B8D3-2B2251E4AE47")

# 건축물대장정보 서비스 (https://apis.data.go.kr/1613000/BldRgstHubService)
BUILDING_API_KEY = os.environ.get("BUILDING_API_KEY", "793dc7affa8f824fc2370758f8c5e0db0f11c1a3c0985a32bebdcdd4bab80946")
