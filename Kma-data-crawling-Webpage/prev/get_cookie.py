import requests


def get_cookie():
    login_url = "https://data.kma.go.kr/login/loginAjax.do"
    session = requests.Session()
    response = session.post(
        login_url,
        data={
            "loginId": "shdbtjd8@gmail.com",  # 여기에 KMA 계정 ID 입력
            "passwordNo": "yuseong0745%",  # 여기에 KMA 계정 비밀번호 입력
        },
    )
    if response.status_code == 200:
        cookies = session.cookies.get_dict()
        cookie_str = "; ".join([f"{key}={value}" for key, value in cookies.items()])
        return cookie_str
    else:
        raise Exception("Failed to retrieve cookies from KMA login page.")


if __name__ == "__main__":
    try:
        cookie = get_cookie()
        print("Successfully retrieved cookie:")
        print(cookie)
    except Exception as e:
        print(f"Error: {e}")
