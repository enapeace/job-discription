import argparse
import json
import re

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


def open_site(page: Page):
    # https://jumpit.saramin.co.kr/positions?sort=popular 접속
    page.goto(f'{BASE_URL}/positions?sort=popular')
    # 카테고리 버튼이 렌더링될 때까지 대기
    page.wait_for_selector('button[value="jobCategory"]')

    # 모달창이 뜨면 '오늘은 이대로 볼래요' 버튼 클릭 (최대 5초 대기)
    try:
        page.wait_for_selector('button:has-text("오늘은 이대로 볼래요")', timeout=5000)
        # force=True: 애니메이션 중 visibility 체크 우회
        page.locator('button:has-text("오늘은 이대로 볼래요")').first.click(force=True)
    except Exception:
        print('모달창이 없습니다.')


def click_category(page: Page, category: str = '인공지능/머신러닝'):
    # 카테고리 버튼 클릭 (기본값: 인공지능/머신러닝)
    if category in CATEGORIES:
        page.locator(f'button[value="jobCategory"]:has-text("{category}")').click()
        # 공고 카드가 로드될 때까지 대기
        page.wait_for_selector('a[target="_self"][href^="/position/"]')


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
        section_sal = page.locator('section#COMPANY_SALARY')
        if section_sal.count() > 0:
            dd = section_sal.locator('dd').first
            company_info['평균_연봉'] = dd.inner_text().strip() if dd.count() > 0 else section_sal.locator('div.info').first.inner_text().strip()
    except Exception:
        pass
    try:
        section_fin = page.locator('section#COMPANY_FINANCIAL')
        if section_fin.count() > 0:
            for key in ['매출액', '영업이익']:
                dl = section_fin.locator(f'dl:has(dt:text-is("{key}"))')
                if dl.count() > 0:
                    company_info[key] = dl.locator('dd').first.inner_text().strip()
    except Exception:
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


def main():
    parser = argparse.ArgumentParser(description='점핏 채용공고 크롤러')
    parser.add_argument('--category', type=str, default='인공지능/머신러닝',
                        choices=CATEGORIES, help='크롤링할 카테고리')
    parser.add_argument('--max_pages', type=int, default=None,
                        help='최대 스크롤 페이지 수 (미설정 시 max_count 채울 때까지 자동 페이지 이동)')
    parser.add_argument('--max_count', type=int, default=50, help='최대 수집 건수')
    args = parser.parse_args()

    results = []

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

        # 4. 각 공고 세부 내용 파싱 후 병합
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
            results.append(job)

        browser.close()

    # 5. JSON 저장
    output_path = f'jobs_{args.category.replace("/", "_")}.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f'저장 완료: {output_path}')


if __name__ == '__main__':
    main()
