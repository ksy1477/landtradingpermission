/**
 * 토지거래계약 허가 신청서 자동완성 JavaScript
 */

// Debounce 함수
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 숫자 포맷팅 (천단위 콤마)
function formatNumber(num) {
    if (!num) return '';
    return Number(num).toLocaleString('ko-KR');
}

// 숫자에서 콤마 제거
function parseNumber(str) {
    if (!str) return 0;
    return Number(str.toString().replace(/,/g, ''));
}

// DOM 로드 완료 시 초기화
document.addEventListener('DOMContentLoaded', function() {
    initAddressSearch();
    initUnitSearch();
    initDateDefault();
    initCalculations();
});

// 오늘 날짜 기본값 설정
function initDateDefault() {
    const today = new Date();
    document.getElementById('app_year').value = today.getFullYear();
    document.getElementById('app_month').value = String(today.getMonth() + 1).padStart(2, '0');
    document.getElementById('app_day').value = String(today.getDate()).padStart(2, '0');
}

// 동/호수 조회 초기화
function initUnitSearch() {
    document.querySelectorAll('.btn-search-unit').forEach(btn => {
        btn.addEventListener('click', async function() {
            const parcelNum = this.dataset.parcel;
            const pnu = document.getElementById(`land${parcelNum}_pnu`).value;
            const dong = document.getElementById(`land${parcelNum}_dong`).value;
            const ho = document.getElementById(`land${parcelNum}_ho`).value;

            if (!pnu) {
                alert('먼저 주소를 검색해주세요.');
                return;
            }
            if (!ho) {
                alert('호수를 입력해주세요.');
                return;
            }

            await fetchUnitInfo(parcelNum, pnu, dong, ho);
        });
    });
}

// 전유부 정보 조회
async function fetchUnitInfo(parcelNum, pnu, dong, ho) {
    showLoading(true);

    try {
        let url = `/api/building/unit?pnu=${pnu}&ho=${ho}`;
        if (dong) {
            url += `&dong=${encodeURIComponent(dong)}`;
        }

        const data = await fetchAPI(url);

        if (data && !data.error) {
            // 대지권 지분 / 대지면적 형식으로 면적 표시
            if (data.land_share && data.land_area) {
                const landShare = parseFloat(data.land_share).toFixed(4);
                const landArea = parseFloat(data.land_area).toFixed(2);
                document.getElementById(`land${parcelNum}_area`).value = `${landShare}/${landArea}`;

                // 계약예정금액 면적에도 반영 (대지권 지분만)
                document.getElementById(`price${parcelNum}_area`).value = landShare;
            }

            // 건물명 (정착물 종류)
            if (data.building_name) {
                const fixtureType = document.querySelector(`[name="fixture${parcelNum}_type"]`);
                if (fixtureType) {
                    fixtureType.value = data.building_name;
                }
            }

            // 구조 (정착물 내용)
            if (data.structure) {
                const fixtureContent = document.querySelector(`[name="fixture${parcelNum}_content"]`);
                if (fixtureContent) {
                    let content = data.structure;
                    if (data.ground_floor) {
                        content += `, 지상 ${data.ground_floor}층`;
                    }
                    if (data.underground_floor && data.underground_floor !== '0') {
                        content += `, 지하 ${data.underground_floor}층`;
                    }
                    if (data.exclusive_area) {
                        content += `, 전용 ${parseFloat(data.exclusive_area).toFixed(2)}㎡`;
                    }
                    fixtureContent.value = content;
                }
            }

            // 금액 계산
            calculatePrices();
        } else {
            alert('전유부 정보를 찾을 수 없습니다. 동/호수를 확인해주세요.');
        }

    } catch (error) {
        console.error('전유부 조회 오류:', error);
        alert('조회 중 오류가 발생했습니다.');
    } finally {
        showLoading(false);
    }
}

// 주소 검색 초기화
function initAddressSearch() {
    // 검색 버튼 클릭 이벤트
    document.querySelectorAll('.btn-search').forEach(btn => {
        btn.addEventListener('click', function() {
            const parcelNum = this.dataset.parcel;
            const addressInput = document.getElementById(`land${parcelNum}_address`);
            searchAddress(addressInput.value, parcelNum);
        });
    });

    // 주소 입력 필드 이벤트
    document.querySelectorAll('.address-input').forEach(input => {
        const parcelNum = input.id.replace('land', '').replace('_address', '');

        // 입력 시 자동 검색 (debounce)
        input.addEventListener('input', debounce(function() {
            if (this.value.length >= 2) {
                searchAddress(this.value, parcelNum);
            } else {
                hideAddressResults(parcelNum);
            }
        }, 300));

        // Enter 키
        input.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                searchAddress(this.value, parcelNum);
            }
        });

        // 포커스 아웃
        input.addEventListener('blur', function() {
            setTimeout(() => hideAddressResults(parcelNum), 200);
        });
    });
}

// 주소 검색 API 호출
async function searchAddress(keyword, parcelNum) {
    if (!keyword || keyword.length < 2) {
        hideAddressResults(parcelNum);
        return;
    }

    try {
        const response = await fetch(`/api/address/jibun?address=${encodeURIComponent(keyword)}`);
        const data = await response.json();

        if (data.error) {
            showAddressResults(parcelNum, [], data.error);
            return;
        }

        showAddressResults(parcelNum, data.results || []);
    } catch (error) {
        console.error('주소 검색 오류:', error);
        showAddressResults(parcelNum, [], '검색 중 오류가 발생했습니다.');
    }
}

// 주소 검색 결과 표시
function showAddressResults(parcelNum, results, errorMsg) {
    const resultsDiv = document.getElementById(`land${parcelNum}_results`);
    resultsDiv.innerHTML = '';

    if (errorMsg) {
        resultsDiv.innerHTML = `<div class="address-no-results">${errorMsg}</div>`;
        resultsDiv.classList.add('active');
        return;
    }

    if (results.length === 0) {
        resultsDiv.innerHTML = '<div class="address-no-results">검색 결과가 없습니다.</div>';
        resultsDiv.classList.add('active');
        return;
    }

    results.forEach(item => {
        const div = document.createElement('div');
        div.className = 'address-item';
        div.innerHTML = `
            <div class="road">${item.road_address || item.jibun_address}</div>
            <div class="jibun">[지번] ${item.jibun_address || ''}</div>
        `;
        div.addEventListener('click', () => selectAddress(parcelNum, item));
        resultsDiv.appendChild(div);
    });

    resultsDiv.classList.add('active');
}

// 주소 검색 결과 숨김
function hideAddressResults(parcelNum) {
    const resultsDiv = document.getElementById(`land${parcelNum}_results`);
    if (resultsDiv) {
        resultsDiv.classList.remove('active');
    }
}

// 주소 선택 시 처리
async function selectAddress(parcelNum, addressData) {
    // 주소 필드 채우기
    document.getElementById(`land${parcelNum}_address`).value = addressData.jibun_address || addressData.road_address;
    document.getElementById(`land${parcelNum}_pnu`).value = addressData.pnu || '';
    document.getElementById(`land${parcelNum}_jibun`).value = addressData.jibun || '';

    hideAddressResults(parcelNum);

    // PNU가 있으면 토지 정보 조회
    if (addressData.pnu) {
        await fetchLandInfo(parcelNum, addressData.pnu);
    }
}

// 토지 정보 조회 (주소 검색 시)
async function fetchLandInfo(parcelNum, pnu) {
    showLoading(true);

    try {
        // 토지 관련 API만 호출 (건축물은 동/호수 조회 시)
        const [landInfo, priceInfo, usageInfo] = await Promise.all([
            fetchAPI(`/api/land/info?pnu=${pnu}`),
            fetchAPI(`/api/land/price?pnu=${pnu}`),
            fetchAPI(`/api/land/usage?pnu=${pnu}`)
        ]);

        // 토지 기본 정보 (지목)
        if (landInfo && !landInfo.error) {
            if (landInfo.jimok_name) {
                document.getElementById(`land${parcelNum}_jimok_legal`).value = landInfo.jimok_name;
                document.getElementById(`price${parcelNum}_jimok`).value = landInfo.jimok_name;
            }
            // 토지 면적은 일단 표시 (동/호수 조회 시 대지권으로 변경됨)
            if (landInfo.area) {
                document.getElementById(`land${parcelNum}_area`).value = landInfo.area;
            }
        }

        // 공시지가
        if (priceInfo && !priceInfo.error && priceInfo.price) {
            document.getElementById(`price${parcelNum}_unit`).value = priceInfo.price;
        }

        // 용도지역
        if (usageInfo && !usageInfo.error) {
            const usageText = [
                ...(usageInfo.usage_areas || []),
                ...(usageInfo.usage_districts || [])
            ].join(', ');
            document.getElementById(`land${parcelNum}_usage`).value = usageText;
        }

        // 금액 계산
        calculatePrices();

    } catch (error) {
        console.error('토지 정보 조회 오류:', error);
    } finally {
        showLoading(false);
    }
}

// API 호출 헬퍼
async function fetchAPI(url) {
    try {
        const response = await fetch(url);
        return await response.json();
    } catch (error) {
        console.error('API 호출 오류:', error);
        return { error: error.message };
    }
}

// 로딩 표시
function showLoading(show) {
    const overlay = document.getElementById('loadingOverlay');
    if (overlay) {
        overlay.style.display = show ? 'flex' : 'none';
    }
}

// 계산 초기화
function initCalculations() {
    // 면적 입력 변경 시 계산
    for (let i = 1; i <= 3; i++) {
        const areaInput = document.getElementById(`land${i}_area`);
        if (areaInput) {
            areaInput.addEventListener('input', function() {
                document.getElementById(`price${i}_area`).value = this.value;
                calculatePrices();
            });
        }
    }
}

// 면적에서 대지권 지분 추출 (지분/면적 형식 또는 숫자)
function parseArea(areaStr) {
    if (!areaStr) return 0;
    const str = areaStr.toString();
    // "지분/면적" 형식인 경우 지분만 추출
    if (str.includes('/')) {
        const parts = str.split('/');
        return parseFloat(parts[0]) || 0;
    }
    return parseFloat(str) || 0;
}

// 금액 계산
function calculatePrices() {
    let totalArea = 0;
    let totalLandAmount = 0;
    let totalFixtureAmount = 0;

    for (let i = 1; i <= 3; i++) {
        // price 테이블의 면적 (대지권 지분)
        const priceArea = parseFloat(document.getElementById(`price${i}_area`).value) || 0;
        // 토지 테이블의 면적 (지분/면적 형식일 수 있음)
        const landAreaStr = document.getElementById(`land${i}_area`).value;
        const area = priceArea || parseArea(landAreaStr);

        const unitPrice = parseFloat(document.getElementById(`price${i}_unit`).value) || 0;
        const landTotal = Math.round(area * unitPrice);

        // 토지 예정금액
        document.getElementById(`price${i}_land_total`).value = landTotal > 0 ? formatNumber(landTotal) : '';

        // 정착물 금액
        const fixtureAmount = parseNumber(document.querySelector(`[name="price${i}_fixture_amount"]`)?.value) || 0;

        // 예정금액합계
        const rowTotal = landTotal + fixtureAmount;
        document.getElementById(`price${i}_total`).value = rowTotal > 0 ? formatNumber(rowTotal) : '';

        totalArea += area;
        totalLandAmount += landTotal;
        totalFixtureAmount += fixtureAmount;
    }

    // 합계
    document.getElementById('total_area').value = totalArea > 0 ? totalArea.toFixed(4) : '';
    document.getElementById('total_land_amount').value = totalLandAmount > 0 ? formatNumber(totalLandAmount) : '';
    document.getElementById('total_fixture_amount').value = totalFixtureAmount > 0 ? formatNumber(totalFixtureAmount) : '';
    document.getElementById('grand_total').value = (totalLandAmount + totalFixtureAmount) > 0 ? formatNumber(totalLandAmount + totalFixtureAmount) : '';
}

// 폼 초기화 시 처리
document.addEventListener('reset', function(e) {
    if (e.target.id === 'landPermitForm') {
        setTimeout(() => {
            initDateDefault();
            calculatePrices();
        }, 10);
    }
});
