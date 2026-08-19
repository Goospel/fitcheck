"""D2 · 사진 품질 검증 — 해상도만 (PRD 5.2 · plan.md 6절)

⏸ 인물 감지 · 전신 여부 · 정면 판별 · 부적절 이미지 필터는 **의도적으로 자른 범위**다.
   각각 별도 비전 모델이 필요하고 6시간+짜리다 (plan.md 8절).

⚠️ **이 파일이 존재하는 진짜 이유는 EXIF다.** 폰으로 찍은 세로 사진은 픽셀을 눕혀
   저장하고 「90도 돌려서 봐라」는 태그를 따로 단다. 브라우저는 그 태그를 읽지만
   `Image.open(f).size` 는 안 읽는다 — 그대로 재면 **멀쩡한 512×768 사진이
   768×512 로 읽혀 거부된다**. 실측 기록은 docs/open-questions.md Q7.

의류 사진(B3)도 같은 함수를 부른다. 사람 사진 전용 판정을 여기 넣지 않는다.
"""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from core.errors import AppError

# PRD 확정값. 「조금 낮춰도 되겠지」로 조정하지 않는다 (CLAUDE.md 1절)
MIN_WIDTH = 512
MIN_HEIGHT = 768

# 생성 모델에 그대로 넘길 수 있는 것만. GIF 는 애니메이션·팔레트라 뺀다
ALLOWED_FORMATS = ("JPEG", "PNG", "WEBP")

# 재인코딩 품질. Pillow 기본값(75)은 눈에 띄게 뭉갠다 — 생성 모델에 넘길 원본이라 아깝다
_QUALITY = 92


def normalize_photo(raw: bytes) -> tuple[bytes, str]:
    """업로드된 사진을 저장 가능한 형태로 굽는다. → (바이트, 포맷)

    회전을 픽셀에 반영해서 **이후로는 아무도 EXIF 를 신경 쓰지 않아도 되게** 한다.
    한 번 통과한 결과를 다시 넣어도 통과한다 (재처리 경로가 막히지 않게).
    """
    try:
        image = Image.open(BytesIO(raw))
        image.load()
    except Image.DecompressionBombError:
        # 작은 파일이 수 GB 로 펼쳐지는 폭탄. 디코딩 전에 Pillow 가 끊어 준다
        raise AppError("PHOTO_UNREADABLE", "사진이 지나치게 큽니다. 다른 파일을 골라 주세요", 400)
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError):
        raise AppError("PHOTO_UNREADABLE", "사진을 읽을 수 없습니다. 다른 파일을 골라 주세요", 400)

    # ⚠️ exif_transpose 가 새 객체를 돌려주면서 format 이 None 이 된다. 먼저 챙긴다
    fmt = image.format
    if fmt not in ALLOWED_FORMATS:
        raise AppError("PHOTO_FORMAT", "JPG · PNG · WEBP 형식만 올릴 수 있습니다", 400)

    image = ImageOps.exif_transpose(image)   # ← 이 한 줄이 Q7 의 해결책 전부다

    # 돌린 **뒤에** 잰다. 돌리기 전 크기로 통과시키면 누운 사진이 새어 들어온다
    width, height = image.size
    if width < MIN_WIDTH or height < MIN_HEIGHT:
        raise AppError(
            "PHOTO_TOO_SMALL",
            f"사진이 너무 작습니다. 가로 {MIN_WIDTH} × 세로 {MIN_HEIGHT} 이상으로 올려 주세요"
            f" (지금 {width} × {height})",
            400,
        )

    # 다시 굽는 김에 EXIF 가 통째로 떨어진다. **덤이 아니라 지켜야 할 성질이다** —
    # 폰 사진에는 촬영 위치(GPS)가 들어 있고, 전신 사진과 같이 저장되면 그게 곧
    # 「이 사람이 어디 사는지」다. `exif=` 를 넘기지 않는 것이 그 처리다 (tests/test_photo.py)
    out = BytesIO()
    image.save(out, fmt, quality=_QUALITY)
    return out.getvalue(), fmt
