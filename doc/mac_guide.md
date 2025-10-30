
# macOS 환경 실행 가이드

이 문서는 macOS 환경에서 유튜브 영상 텍스트 추출기 프로젝트를 설치하고 실행하기 위한 가이드입니다.

---

## 1. 필수 프로그램 설치

프로젝트를 실행하기 위해 다음 프로그램들을 설치합니다. macOS에서는 [Homebrew](https://brew.sh/index_ko)를 사용하면 매우 쉽게 설치할 수 있습니다.

### 1.1. Homebrew

- **설명:** macOS용 패키지 관리자입니다. 앞으로 설치할 모든 프로그램을 Homebrew를 통해 설치합니다.
- **설치 방법:**
    1.  터미널(Terminal)을 엽니다.
    2.  아래 명령어를 복사하여 붙여넣고 실행합니다. 설치 과정에서 비밀번호를 요구할 수 있습니다.
        ```bash
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        ```
    3. 설치가 완료되면, 터미널에 표시되는 안내에 따라 `brew` 명령어를 PATH에 추가하는 작업을 수행해야 할 수 있습니다.

### 1.2. Python

- **설명:** macOS에 기본적으로 설치된 Python 대신, 최신 버전을 Homebrew로 설치하여 사용합니다. (버전 3.8 이상 권장)
- **설치 방법:**
    ```bash
    brew install python
    ```

### 1.3. Git

- **설명:** 프로젝트 코드를 다운로드하고 관리하기 위해 Git이 필요합니다. (Xcode Command Line Tools와 함께 이미 설치되어 있을 수 있습니다.)
- **설치 방법:**
    ```bash
    brew install git
    ```

### 1.4. FFmpeg

- **설명:** 유튜브 영상에서 음성을 추출하는 데 사용되는 **매우 중요한** 프로그램입니다.
- **설치 방법:**
    ```bash
    brew install ffmpeg
    ```

---

## 2. 프로젝트 설정 및 실행

필수 프로그램이 모두 설치되었다면, 다음 단계에 따라 프로젝트를 설정하고 실행합니다.

1.  **프로젝트 복제 (Clone):**
    *   터미널에서, 프로젝트를 저장하고 싶은 폴더로 이동한 후 다음 명령어를 실행합니다.
    ```bash
    git clone https://github.com/koreats/youtubelister.git
    ```

2.  **폴더 이동:**
    *   다운로드된 프로젝트 폴더로 이동합니다.
    ```bash
    cd youtubelister
    ```

3.  **가상환경 생성 및 활성화:**
    *   독립된 파이썬 환경을 만들기 위해 가상환경을 생성하고 활성화합니다.
    ```bash
    # 가상환경 생성 (python3 사용)
    python3 -m venv venv

    # 가상환경 활성화 (macOS)
    source venv/bin/activate
    ```
    *   성공적으로 활성화되면, 터미널의 프롬프트 맨 앞에 `(venv)`가 표시됩니다.

4.  **필요 라이브러리 설치:**
    *   프로젝트 실행에 필요한 모든 파이썬 라이브러리를 아래 명령어 하나로 설치합니다.
    ```bash
    python3 -m pip install -r requirements.txt
    ```

5.  **애플리케이션 실행:**
    *   모든 설치가 완료되었습니다. 다음 명령어로 웹 서버를 시작합니다.
    ```bash
    python3 app.py
    ```
    *   터미널에 "Running on http://127.0.0.1:8080" 메시지가 나타나면 성공입니다.

6.  **애플리케이션 접속:**
    *   웹 브라우저를 열고 주소창에 `http://127.0.0.1:8080` 을 입력하여 접속합니다.

