import argparse
import json
import os
import re
import shutil
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import Page, sync_playwright

BASE_URL = 'https://jumpit.saramin.co.kr'

CATEGORIES = [
    '인공지능/머신러닝',
    '서버/백엔드 개발자',
    '프론트엔드 개발자',
    '웹 풀스택 개발자',
    '안드로이드 개발자',
    'iOS 개발자',
    '크로스플랫폼 앱개발자',
    '게임 클라이언트 개발자',
    '게임 서버 개발자',
    'DBA',
    '빅데이터 엔지니어',
    'devops/시스템 엔지니어',
    '정보보안 담당자',
    'QA 엔지니어',
    '개발 PM',
    'HW/임베디드',
    'SW/솔루션',
    '웹퍼블리셔',
    'VR/AR/3D',
    '블록체인',
    '기술지원',
]


def login(page: Page):
    """점핏 사이트에 로그인하는 함수"""
    # 환경변수에서 아이디와 비밀번호 가져오기
    saramin_id = os.getenv('SARAMIN_ID')
    saramin_password = os.getenv('SARAMIN_PASSWORD')
    
    if not saramin_id or not saramin_password:
        raise ValueError('SARAMIN_ID와 SARAMIN_PASSWORD 환경변수가 설정되어 있지 않습니다.')
    
    # 메인 페이지 접속
    page.goto(BASE_URL)
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)  # 페이지 렌더링 대기
    
    # 이미 로그인되어 있는지 확인 (로그인 폼이 없으면 이미 로그인된 상태)
    login_form = page.locator('input#id')
    if login_form.count() > 0:
        print('이미 로그인 페이지에 있습니다.')
    else:
        # "회원가입/로그인" 버튼 찾기 (여러 선택자 시도)
        login_button = None
        selectors = [
            'button.sc-8983ef67-3.eWtTxZ:has-text("회원가입/로그인")',  # 클래스명 포함
            'button:has-text("회원가입/로그인")',
            'button.sc-8983ef67-3:has-text("회원가입/로그인")',
            'button.eWtTxZ:has-text("회원가입/로그인")',
            'button:has-text("로그인")',
            'a:has-text("회원가입/로그인")',
            'a:has-text("로그인")',
        ]
        
        for selector in selectors:
            try:
                login_button = page.locator(selector).first
                if login_button.count() > 0:
                    # 버튼이 존재하면 보이지 않아도 force 클릭 시도
                    try:
                        login_button.wait_for(state='visible', timeout=3000)
                        print(f'로그인 버튼 찾음 (visible): {selector}')
                        login_button.click()
                        break
                    except Exception:
                        # 보이지 않아도 force 클릭 시도
                        print(f'로그인 버튼 찾음 (force click): {selector}')
                        login_button.click(force=True)
                        break
            except Exception as e:
                continue
        
        if login_button is None or login_button.count() == 0:
            # 로그인 버튼을 찾지 못한 경우, 이미 로그인되어 있을 수 있음
            print('로그인 버튼을 찾을 수 없습니다. 이미 로그인되어 있을 수 있습니다.')
            # 로그인 폼이 있는지 다시 확인
            page.wait_for_timeout(2000)
            login_form = page.locator('input#id')
            if login_form.count() == 0:
                print('로그인 폼이 없습니다. 이미 로그인된 상태로 진행합니다.')
                return
            else:
                raise Exception('로그인 버튼을 찾을 수 없습니다.')
        
        page.wait_for_timeout(2000)  # 모달/팝업이 열릴 시간 대기
    
    # 로그인 폼이 나타날 때까지 대기
    try:
        page.wait_for_selector('input#id', timeout=10000)
        page.wait_for_selector('input#password', timeout=10000)
    except Exception as e:
        print(f'로그인 폼을 찾을 수 없습니다: {e}')
        # 이미 로그인되어 있을 수 있음
        return
    
    # 아이디와 비밀번호 입력
    page.fill('input#id', saramin_id)
    page.fill('input#password', saramin_password)
    
    # 로그인 버튼 클릭 (여러 버튼이 있을 수 있으므로 첫 번째 버튼 선택)
    login_submit_button = None
    selectors = [
        'button.btn_login.BtnType.SizeML:has-text("로그인")',
        'button.BtnType.SizeML.btn_login:has-text("로그인")',
        'button:has-text("로그인")',
    ]
    
    for selector in selectors:
        buttons = page.locator(selector)
        if buttons.count() > 0:
            # 첫 번째 버튼 선택 (로그인 폼 내의 버튼)
            login_submit_button = buttons.first
            print(f'로그인 제출 버튼 찾음: {selector} (총 {buttons.count()}개 중 첫 번째 선택)')
            break
    
    if login_submit_button is None:
        raise Exception('로그인 제출 버튼을 찾을 수 없습니다.')
    
    login_submit_button.click()
    
    # 로그인 완료 대기 (공고 페이지로 리다이렉트되거나 로그인 성공 확인)
    page.wait_for_load_state('networkidle', timeout=15000)
    page.wait_for_timeout(2000)  # 추가 대기 시간
    
    print('로그인 완료')


def open_site(page: Page):
    # 먼저 로그인 수행
    login(page)
    
    # 로그인 후 공고조회 페이지로 이동
    page.goto(f'{BASE_URL}/positions?sort=popular')
    # 카테고리 버튼이 렌더링될 때까지 대기
    page.wait_for_selector('button[value="jobCategory"]')
    page.wait_for_timeout(1000)  # 추가 대기

    # 모달창이 뜨면 '오늘은 이대로 볼래요' 버튼 클릭 (최대 5초 대기)
    try:
        page.wait_for_selector('button:has-text("오늘은 이대로 볼래요")', timeout=5000)
        # force=True: 애니메이션 중 visibility 체크 우회
        page.locator('button:has-text("오늘은 이대로 볼래요")').first.click(force=True)
        page.wait_for_timeout(1000)
    except Exception:
        print('모달창이 없습니다.')


def click_category(page: Page, category: str = '인공지능/머신러닝'):
    """카테고리 버튼 클릭 및 필터링 확인"""
    if category not in CATEGORIES:
        print(f'경고: "{category}"는 유효한 카테고리입니다.')
        return
    
    print(f'카테고리 선택 중: {category}')
    
    # 여러 선택자 시도
    category_button = None
    selectors = [
        f'button[value="jobCategory"]:has-text("{category}")',
        f'button:has-text("{category}")',
        f'button[value="jobCategory"]',
    ]
    
    # 먼저 모든 카테고리 버튼 확인
    all_category_buttons = page.locator('button[value="jobCategory"]').all()
    print(f'발견된 카테고리 버튼 수: {len(all_category_buttons)}')
    
    # 텍스트로 카테고리 버튼 찾기
    for btn in all_category_buttons:
        try:
            btn_text = btn.inner_text().strip()
            print(f'  카테고리 버튼 텍스트: "{btn_text}"')
            if category in btn_text:
                category_button = btn
                print(f'  ✓ 매칭된 카테고리 버튼 찾음: "{btn_text}"')
                break
        except Exception:
            continue
    
    if category_button is None:
        # 선택자로 다시 시도
        for selector in selectors:
            try:
                buttons = page.locator(selector)
                if buttons.count() > 0:
                    # 텍스트로 필터링
                    for i in range(buttons.count()):
                        btn = buttons.nth(i)
                        try:
                            if category in btn.inner_text():
                                category_button = btn
                                break
                        except Exception:
                            continue
                    if category_button:
                        break
            except Exception:
                continue
    
    if category_button is None:
        raise Exception(f'카테고리 버튼을 찾을 수 없습니다: {category}')
    
    # 카테고리 버튼 클릭
    category_button.click()
    print(f'카테고리 버튼 클릭 완료: {category}')
    
    # 페이지가 업데이트될 때까지 대기
    page.wait_for_load_state('networkidle', timeout=10000)
    page.wait_for_timeout(2000)  # 추가 대기
    
    # 공고 카드가 로드될 때까지 대기
    try:
        page.wait_for_selector('a[target="_self"][href^="/position/"]', timeout=10000)
        print(f'카테고리 필터링 완료: {category}')
    except Exception as e:
        print(f'경고: 공고 카드를 찾을 수 없습니다: {e}')


def collect_jobs(page: Page, max_pages: int | None = None, max_count: int = 50) -> list:
    # 공고 카드에서 title, href 수집 (무한 스크롤 대응)
    # max_pages가 None이면 max_count를 채울 때까지 자동으로 페이지 스크롤
    jobs = []
    seen_hrefs = set()
    page_num = 0

    while True:
        # max_pages가 설정된 경우 페이지 수 제한
        if max_pages is not None and page_num >= max_pages:
            break

        cards = page.locator('a[target="_self"][href^="/position/"]')
        count = cards.count()

        for i in range(count):
            if len(jobs) >= max_count:
                return jobs
            card = cards.nth(i)
            title = card.get_attribute('title')
            href = card.get_attribute('href')
            if title and href and href not in seen_hrefs:
                seen_hrefs.add(href)
                jobs.append({
                    'no': len(jobs) + 1,
                    'title': title,
                    'job_info_url': f'{BASE_URL}{href}',
                    'href': href,
                })

        if len(jobs) >= max_count:
            break

        # 스크롤 다운으로 다음 공고 로드
        prev_count = count
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        page.wait_for_timeout(2000)
        new_count = page.locator('a[target="_self"][href^="/position/"]').count()
        if new_count == prev_count:
            break  # 더 이상 새 공고 없음

        page_num += 1

    return jobs


def parse_job_detail(page: Page, href: str) -> dict:
    # 세부 공고 페이지 접속
    page.goto(f'{BASE_URL}{href}')
    # 상세 정보 영역이 렌더링될 때까지 대기
    page.wait_for_selector('div.position_info')

    result = {}

    # 회사명 / 회사 링크
    company_link = page.locator('a.name')
    result['company_name'] = company_link.locator('span').first.inner_text().strip()
    company_href = company_link.get_attribute('href')
    result['company_url'] = f'{BASE_URL}{company_href}' if company_href else ''

    # 회사 소개 태그 (a.name 다음 ul의 li > a 텍스트, 이모지 제거)
    result['company_tags'] = [
        cleaned for t in page.locator('a.name ~ ul li a').all_inner_texts()
        if (cleaned := re.sub(r'[^\x00-\x7F가-힣ㄱ-ㅎㅏ-ㅣ\s]', '', t).strip())
    ]

    # 세부 요구내역 (경력 / 학력 / 마감일 / 근무지역)
    requirements = {}
    for key in ['경력', '학력', '마감일', '근무지역']:
        dl = page.locator(f'dl:has(dt:text-is("{key}"))')
        if dl.count() > 0:
            if key == '근무지역':
                # li 안의 첫 번째 텍스트 노드만 추출 (지도보기/주소복사 버튼 제외)
                address = dl.locator('dd li').first.evaluate(
                    'el => Array.from(el.childNodes).find(n => n.nodeType === 3).textContent.trim()'
                )
                requirements[key] = address
            else:
                requirements[key] = dl.locator('dd').first.inner_text().strip()
    result['requirements'] = requirements

    # 직무 상세 (기술스택 / 주요업무 / 자격요건 등)
    job_description = {}
    dl_elements = page.locator('div.position_info dl')
    for i in range(dl_elements.count()):
        dl = dl_elements.nth(i)
        key = dl.locator('dt').first.inner_text().strip()
        if key == '기술스택':
            stacks = dl.locator('dd div').all_inner_texts()
            value = ', '.join(s.strip() for s in stacks if s.strip())
        else:
            value = dl.locator('dd').first.inner_text().strip()
        job_description[key] = value
    result['job_description'] = job_description

    return result


def _scrape_company_sections(page: Page) -> dict:
    """현재 페이지(회사 페이지)에서 COMPANY_EMPLOYEE, SALARY, FINANCIAL 섹션만 스크래핑."""
    company_info = {
        '전체_직원수': '',
        '평균_연봉': '',
        '매출액': '',
        '영업이익': '',
    }
    try:
        # COMPANY_EMPLOYEE: 전체 직원수 (예: 16명)
        section_emp = page.locator('section#COMPANY_EMPLOYEE')
        if section_emp.count() > 0:
            strong_el = section_emp.locator('div.info strong').first
            if strong_el.count() > 0:
                company_info['전체_직원수'] = strong_el.inner_text().strip()
                if company_info['전체_직원수'].isdigit():
                    company_info['전체_직원수'] += '명'
            else:
                text = section_emp.locator('div.info').first.inner_text()
                m = re.search(r'(\d+)\s*명', text)
                company_info['전체_직원수'] = f"{m.group(1)}명" if m else (text.strip() or '')
    except Exception:
        pass
    try:
        # COMPANY_SALARY: 평균 연봉 (전체)
        # 구조: section#COMPANY_SALARY > ul > li > div (span:has-text("전체")) + strong.salary
        section_sal = page.locator('section#COMPANY_SALARY')
        if section_sal.count() > 0:
            # "전체" 텍스트가 있는 li 찾기
            all_lis = section_sal.locator('ul li').all()
            for li in all_lis:
                span_text = li.locator('span').all_inner_texts()
                if any('전체' in text for text in span_text):
                    # strong.salary 찾기
                    salary_strong = li.locator('strong.salary')
                    if salary_strong.count() > 0:
                        company_info['평균_연봉'] = salary_strong.first.inner_text().strip()
                        break
                    else:
                        # fallback: li 내의 strong 태그 찾기
                        strong_el = li.locator('strong').first
                        if strong_el.count() > 0:
                            company_info['평균_연봉'] = strong_el.inner_text().strip()
                            break
    except Exception as e:
        print(f'  평균 연봉 파싱 오류: {e}')
        pass
    try:
        # COMPANY_FINANCIAL: 매출액, 영업이익
        # 구조: section#COMPANY_FINANCIAL > ul > li > div (span:has-text("매출액"/"영업이익")) + strong
        section_fin = page.locator('section#COMPANY_FINANCIAL')
        if section_fin.count() > 0:
            all_lis = section_fin.locator('ul li').all()
            for li in all_lis:
                span_texts = li.locator('span').all_inner_texts()
                span_text = ' '.join(span_texts)
                
                # 매출액 파싱
                if '매출액' in span_text and not company_info['매출액']:
                    sales_strong = li.locator('strong').first
                    if sales_strong.count() > 0:
                        company_info['매출액'] = sales_strong.inner_text().strip()
                
                # 영업이익 파싱
                if '영업이익' in span_text and not company_info['영업이익']:
                    profit_strong = li.locator('strong.opProfit')
                    if profit_strong.count() > 0:
                        company_info['영업이익'] = profit_strong.first.inner_text().strip()
                    else:
                        # fallback: opProfit 클래스가 없으면 일반 strong 태그 사용
                        profit_strong = li.locator('strong').first
                        if profit_strong.count() > 0:
                            company_info['영업이익'] = profit_strong.inner_text().strip()
    except Exception as e:
        print(f'  재무 정보 파싱 오류: {e}')
        pass
    return company_info


def parse_company_info(page: Page, company_url: str) -> dict:
    """공고 상세 화면에서 회사 링크를 클릭해 회사 페이지로 이동 → 정보 수집 → 다시 공고 화면으로 복귀."""
    empty = {'전체_직원수': '', '평균_연봉': '', '매출액': '', '영업이익': ''}
    if not company_url or not company_url.startswith(BASE_URL):
        return empty
    try:
        # 회사 링크 클릭: 새 탭(target="_blank")이면 팝업에서 수집 후 닫고, 같은 탭이면 수집 후 go_back()
        with page.expect_popup(timeout=5000) as popup_info:
            page.locator('a.name').first.click()
        company_page = popup_info.value
        try:
            company_page.wait_for_load_state('networkidle', timeout=10000)
            company_page.wait_for_timeout(1500)
            company_info = _scrape_company_sections(company_page)
        finally:
            company_page.close()
        return company_info
    except Exception:
        # 같은 탭으로 이동한 경우: 이미 회사 페이지면 수집만, 아니면 goto 후 수집. 끝나면 공고 화면으로 뒤로 가기
        try:
            if '/company/' not in page.url:
                page.goto(company_url)
            page.wait_for_load_state('networkidle', timeout=10000)
            page.wait_for_timeout(1500)
            company_info = _scrape_company_sections(page)
            page.go_back()
            page.wait_for_load_state('networkidle', timeout=8000)
            return company_info
        except Exception as e:
            print(f'  회사 정보 수집 오류 ({company_url}): {e}')
            return empty


def save_job_to_json(job: dict, output_path: str):
    """단일 공고를 JSON 파일에 추가 (실시간 저장)"""
    # 기존 파일이 있으면 읽기, 없으면 빈 배열로 시작
    if os.path.exists(output_path):
        try:
            with open(output_path, 'r', encoding='utf-8') as f:
                results = json.load(f)
        except (json.JSONDecodeError, IOError):
            results = []
    else:
        results = []
    
    # 새 공고 추가
    results.append(job)
    
    # 파일에 저장
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description='점핏 채용공고 크롤러')
    parser.add_argument('--category', type=str, default='인공지능/머신러닝',
                        choices=CATEGORIES, help='크롤링할 카테고리')
    parser.add_argument('--max_pages', type=int, default=None,
                        help='최대 스크롤 페이지 수 (미설정 시 max_count 채울 때까지 자동 페이지 이동)')
    parser.add_argument('--max_count', type=int, default=50, help='최대 수집 건수')
    args = parser.parse_args()

    now_str = datetime.now().strftime('%Y%m%d_%H%M')
    output_path = f'data/crawling/jobs_{now_str}.json'
    
    # 기존 파일이 있으면 백업 (선택사항)
    if os.path.exists(output_path):
        backup_path = f'{output_path}.backup'
        print(f'기존 파일 백업: {backup_path}')
        shutil.copy2(output_path, backup_path)
        # 기존 파일 삭제하고 새로 시작할지, 아니면 이어서 진행할지 선택
        # 여기서는 새로 시작하도록 설정 (기존 파일 삭제)
        os.remove(output_path)
        print('기존 파일 삭제, 새로 시작합니다.')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # 크롬 창 띄움
        page = browser.new_page()

        # 1. 사이트 접속 및 모달 닫기
        open_site(page)

        # 2. 카테고리 클릭
        click_category(page, args.category)

        # 3. 공고 목록(title + href) 수집
        jobs = collect_jobs(page, max_pages=args.max_pages, max_count=args.max_count)
        print(f'수집된 공고 수: {len(jobs)}')

        # 4. 각 공고 세부 내용 파싱 후 실시간으로 JSON에 저장
        for i, job in enumerate(jobs):
            print(f'[{i+1}/{len(jobs)}] {job["title"]} 파싱 중...')
            job['job_category'] = args.category
            try:
                job.update(parse_job_detail(page, job['href']))
                # 회사 페이지 이동 후 company_info 수집 (직원수, 연봉, 재무)
                job['company_info'] = parse_company_info(page, job.get('company_url', ''))
            except Exception as e:
                print(f'  오류: {e}')
                job['company_info'] = {'전체_직원수': '', '평균_연봉': '', '매출액': '', '영업이익': ''}
            
            # 각 공고 파싱 완료 시 즉시 JSON 파일에 저장
            save_job_to_json(job, output_path)
            print(f'  ✓ 저장 완료: {output_path} ({i+1}/{len(jobs)})')

        browser.close()

    print(f'\n전체 저장 완료: {output_path} (총 {len(jobs)}건)')


if __name__ == '__main__':
    main()
