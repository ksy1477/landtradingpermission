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
    initRightTypeSync();
});

// 권리 유형 선택 시 관련 필드 자동 매핑
function initRightTypeSync() {
    const rightRadios = document.querySelectorAll('input[name="right_type"]');
    rightRadios.forEach(radio => {
        radio.addEventListener('change', function() {
            // (18) 정착물 권리 종류에 반영
            const fixture1RightType = document.getElementById('fixture1_right_type');
            if (fixture1RightType) {
                fixture1RightType.value = this.value;
            }
        });
    });
}

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
            // 전용면적
            const exclusiveArea = data.exclusive_area ? parseFloat(data.exclusive_area).toFixed(2) : '';

            // VWorld API에서 대지권 비율을 가져온 경우 (source: 'vworld')
            const isVWorldData = data.source === 'vworld';
            let landShare = '';  // 대지권 면적
            let landArea = '';   // 전체 대지면적

            if (isVWorldData && data.land_share) {
                // VWorld API에서 직접 대지권 비율 제공
                landShare = data.land_share;
                landArea = data.land_area || '';
            } else {
                // 건축물대장 API fallback
                landArea = data.land_area ? parseFloat(data.land_area).toFixed(2) : '';

                // 대지권 비율 추정 (전용면적/전체연면적 × 대지면적)
                if (exclusiveArea && data.total_area && landArea) {
                    const totalArea = parseFloat(data.total_area);
                    if (totalArea > 0) {
                        landShare = (parseFloat(exclusiveArea) / totalArea * parseFloat(landArea)).toFixed(4);
                    }
                }
            }

            // 데이터가 없는 경우 안내
            if (!landShare && !exclusiveArea) {
                alert(`${dong || ''}동 ${ho}호 전유부 데이터를 찾을 수 없습니다.\n\n대지권 비율은 등기부등본을 확인하여 직접 입력해주세요.\n(예: 35.9790/36645.30 형식)`);
            }

            // 면적 필드에 표시 (대지권면적/대지면적)
            const areaField = document.getElementById(`land${parcelNum}_area`);
            if (landShare && landArea) {
                areaField.value = `${landShare}/${landArea}`;
                if (isVWorldData) {
                    areaField.title = '대지권면적/대지면적 (VWorld API)';
                } else {
                    areaField.title = '대지권면적(추정)/대지면적 - 정확한 값은 등기부등본 확인 필요';
                }
            } else if (landShare) {
                areaField.value = landShare;
                areaField.title = '대지권면적';
            } else if (exclusiveArea) {
                areaField.value = exclusiveArea;
                areaField.title = '전용면적 - 대지권 비율은 등기부등본 확인 필요';
            } else if (landArea) {
                areaField.value = '';
                areaField.placeholder = `대지권비율 입력 (대지면적: ${landArea}㎡)`;
            }

            // 계약예정금액 면적에 대지권면적 반영
            if (landShare) {
                document.getElementById(`price${parcelNum}_area`).value = landShare;
            } else if (exclusiveArea) {
                document.getElementById(`price${parcelNum}_area`).value = exclusiveArea;
            }

            // 정착물 내용 (17번) - PRD 형식: "{동}동 {호}호 ({구조}, 전용면적 {면적}㎡)"
            const fixtureContent = document.getElementById(`fixture${parcelNum}_content`);
            if (fixtureContent) {
                const dongText = dong ? `${dong}동 ` : '';
                const hoText = ho ? `${ho}호` : '';
                const structureText = data.structure || '철근콘크리트구조';
                const areaText = exclusiveArea ? `전용면적 ${exclusiveArea}㎡` : '';

                let content = `${dongText}${hoText}`;
                if (structureText || areaText) {
                    content += ` (${structureText}`;
                    if (areaText) {
                        content += `, ${areaText}`;
                    }
                    content += ')';
                }
                fixtureContent.value = content.trim();
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

        // 용도지역 (용도지구 제외)
        if (usageInfo && !usageInfo.error) {
            const usageText = (usageInfo.usage_areas || []).join(', ');
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
    const areaInput = document.getElementById('land1_area');
    if (areaInput) {
        areaInput.addEventListener('input', function() {
            document.getElementById('price1_area').value = this.value;
            calculatePrices();
        });
    }

    // 30번 매매대금 입력 시 29번 자동 계산
    const totalInput = document.getElementById('price1_total');
    if (totalInput) {
        totalInput.addEventListener('input', function() {
            calculatePrices();
        });
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
    // price 테이블의 면적 (대지권 지분)
    const priceArea = parseFloat(document.getElementById('price1_area').value) || 0;
    // 토지 테이블의 면적 (지분/면적 형식일 수 있음)
    const landAreaStr = document.getElementById('land1_area').value;
    const area = priceArea || parseArea(landAreaStr);

    const unitPrice = parseFloat(document.getElementById('price1_unit').value) || 0;
    const landTotal = Math.round(area * unitPrice);

    // 27번: 토지 예정금액
    document.getElementById('price1_land_total').value = landTotal > 0 ? formatNumber(landTotal) : '';

    // 30번: 매매대금 (사용자 입력)
    const totalInput = parseNumber(document.getElementById('price1_total').value) || 0;

    // 29번: 정착물 예정금액 = 30번(매매대금) - 27번(토지예정금액)
    if (totalInput > 0) {
        const fixtureAmount = totalInput - landTotal;
        document.querySelector('[name="price1_fixture_amount"]').value = fixtureAmount > 0 ? formatNumber(fixtureAmount) : '';
    }
}

// 폼 초기화 시 처리
document.addEventListener('reset', function(e) {
    if (e.target.id === 'landPermitForm') {
        setTimeout(() => {
            initDateDefault();
            calculatePrices();
            // 고정값 복원
            document.getElementById('fixture1_type').value = '아파트';
            document.getElementById('fixture1_right_type').value = '소유권';
            document.getElementById('fixture1_right_content').value = '매매';
            document.getElementById('transfer1_type').value = '매매';
        }, 10);
    }
});

// PDF 다운로드 함수
async function downloadPDF() {
    showLoading(true);

    try {
        // 폼 데이터 수집
        const formData = collectFormData();

        const response = await fetch('/api/generate-pdf', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });

        if (!response.ok) {
            throw new Error('PDF 생성 실패');
        }

        // PDF 다운로드
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;

        // 파일명 생성: 토지거래계약허가신청서_{주소}_{날짜}.pdf
        const address = document.getElementById('land1_address').value || '신청서';
        const shortAddr = address.split(' ').slice(0, 2).join('');
        const today = new Date().toISOString().slice(0, 10).replace(/-/g, '');
        a.download = `토지거래계약허가신청서_${shortAddr}_${today}.pdf`;

        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);

    } catch (error) {
        console.error('PDF 다운로드 오류:', error);
        alert('PDF 생성 중 오류가 발생했습니다. 인쇄 기능을 이용해주세요.');
    } finally {
        showLoading(false);
    }
}

// 폼 데이터 수집
function collectFormData() {
    const form = document.getElementById('landPermitForm');
    const formData = {};

    // 모든 input 필드 수집
    form.querySelectorAll('input').forEach(input => {
        if (input.type === 'radio') {
            if (input.checked) {
                formData[input.name] = input.value;
            }
        } else if (input.type === 'checkbox') {
            if (input.checked) {
                formData[input.name] = input.value;
            }
        } else {
            formData[input.name || input.id] = input.value;
        }
    });

    return formData;
}
