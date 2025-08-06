import asyncio
import msgpack
import websockets

# WebSocket 엔드포인트 (msgpack 인코딩 지정)
WS_URI = "wss://mainnet.zklighter.elliot.ai/stream?encoding=msgpack"

# 커스텀 헤더를 (name, value) 튜플 리스트로 정의
ADDITIONAL_HEADERS = [
    ("Pragma", "no-cache"),
    ("Cache-Control", "no-cache"),
    (
        "User-Agent",
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/137.0.0.0 Safari/537.36"
        ),
    ),
    ("Origin", "https://app.lighter.xyz"),
    ("Accept-Encoding", "gzip, deflate, br, zstd"),
    ("Accept-Language", "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"),
    ("Sec-WebSocket-Extensions", "permessage-deflate; client_max_window_bits"),
]

# 구독할 채널 목록
CHANNELS = ["public_market_data/27", "market_stats/all", "height"]


async def stream_and_decode():
    """
    최신 websockets API에 맞춰 additional_headers 인자를 사용합니다.
    """
    # connect 함수 시그니처에 맞춰 additional_headers 전달
    async with websockets.connect(
        WS_URI,
        additional_headers=ADDITIONAL_HEADERS,
        compression="deflate",  # permessage-deflate 활성화
        open_timeout=10,  # 연결 타임아웃
        ping_interval=20,  # ping 간격
        ping_timeout=20,  # ping 응답 타임아웃
    ) as websocket:
        print(f"Connected to {WS_URI}")

        # 다중 채널 구독 요청 전송
        for channel in CHANNELS:
            subscription = {"type": "subscribe", "channel": channel}
            packed = msgpack.packb(subscription, use_bin_type=True)
            await websocket.send(packed)
            print(f"Sent subscription request: {subscription}")

        try:
            async for raw_msg in websocket:
                # raw_msg: msgpack-encoded 바이너리 데이터
                data = msgpack.unpackb(raw_msg, raw=False)
                print(data)
        except websockets.ConnectionClosed as e:
            print(f"WebSocket connection closed: {e}")


if __name__ == "__main__":
    asyncio.run(stream_and_decode())
