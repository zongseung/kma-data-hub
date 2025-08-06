# auth.py

from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from databases import create_user, get_user_by_username

# --- 설정값 ---
SECRET_KEY = "CHANGE_THIS_TO_RANDOM_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# --- 패스워드 해시 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# --- OAuth2 스킴 정의 ---
# 토큰 발급은 "/api/token" 엔드포인트에서 처리
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")

# --- 사용자 인증 & 토큰 생성 ---
def authenticate_user(username: str, password: str):
    """
    1) WeatherDownloader.get_cookie() 로 KMA 로그인 시도
    2) 성공 시 로컬 DB에 없으면 자동 가입
    3) 사용자 정보 반환 ({"username": username})
    """
    from weather_downloader import WeatherDownloader

    wd = WeatherDownloader()
    try:
        wd.get_cookie(login_id=username, password=password)
    except Exception:
        return None

    # 자동 가입
    if not get_user_by_username(username):
        hashed = get_password_hash(password)
        create_user(username, hashed)

    return {"username": username}

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- 현재 사용자 조회 의존성 ---
async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = get_user_by_username(username)
    if not user:
        raise credentials_exception
    return user